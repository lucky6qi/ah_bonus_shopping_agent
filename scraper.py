"""Improved scraper with caching and lightweight requests"""
import json
import time
import os
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import requests


class AHBonusScraper:
    """Improved scraper with caching and lightweight requests"""
    
    def __init__(self, config, session_manager=None):
        """
        Initialize scraper
        
        Args:
            config: Config object
            session_manager: Optional SessionManager instance (for sharing browser session)
        """
        self.config = config
        self.driver = None
        self.session_manager = session_manager  # 可以共享SessionManager
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
    def _load_cache(self) -> Optional[List[Dict[str, Any]]]:
        """Load products from cache if valid"""
        if not os.path.exists(self.config.products_cache_file):
            return None
        
        try:
            with open(self.config.products_cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Check if cache has timestamp
            if isinstance(cache_data, dict) and 'timestamp' in cache_data:
                cache_time = datetime.fromisoformat(cache_data['timestamp'])
                expiry_time = cache_time + timedelta(hours=self.config.cache_expiry_hours)
                
                if datetime.now() < expiry_time:
                    print(f"✅ Using cached products (cached at {cache_time.strftime('%Y-%m-%d %H:%M:%S')})")
                    return cache_data.get('products', [])
                else:
                    print(f"ℹ️ Cache expired (expired at {expiry_time.strftime('%Y-%m-%d %H:%M:%S')})")
                    return None
            else:
                # Old format without timestamp, treat as expired
                return None
                
        except Exception as e:
            print(f"⚠️ Error loading cache: {e}")
            return None
    
    def _save_bonus_products(self, products: List[Dict[str, Any]]):
        """
        Save bonus products to JSON file - 每次完全刷新（删除旧文件，创建新文件）
        """
        try:
            bonus_products = [p for p in products if p.get("source") == "bonus"]
            if bonus_products:
                bonus_file = "bonus_products.json"
                
                # 删除旧文件（如果存在）
                if os.path.exists(bonus_file):
                    os.remove(bonus_file)
                    print(f"🗑️  已删除旧的 {bonus_file}")
                
                # 创建新文件
                bonus_data = {
                    "timestamp": datetime.now().isoformat(),
                    "products": bonus_products
                }
                with open(bonus_file, 'w', encoding='utf-8') as f:
                    json.dump(bonus_data, f, ensure_ascii=False, indent=2)
                print(f"✅ bonus数据已保存到 {bonus_file} ({len(bonus_products)} 个产品)")
        except Exception as e:
            print(f"⚠️ 保存bonus数据失败: {e}")
    
    def _save_eerder_gekocht_products(self, products: List[Dict[str, Any]]):
        """
        Save eerder-gekocht products to JSON file - 增量更新（只追加新的、不同的产品）
        """
        try:
            eerder_products = [p for p in products if p.get("source") == "eerder-gekocht"]
            if not eerder_products:
                return
            
            eerder_file = self.config.eerder_gekocht_file
            
            # 加载现有数据
            existing_products = []
            if os.path.exists(eerder_file):
                try:
                    with open(eerder_file, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                        if isinstance(existing_data, dict) and 'products' in existing_data:
                            existing_products = existing_data['products']
                        elif isinstance(existing_data, list):
                            existing_products = existing_data
                except Exception as e:
                    print(f"⚠️ 加载现有eerder-gekocht数据失败: {e}")
                    existing_products = []
            
            # 创建现有产品的唯一标识集合（使用 title + product_url 作为唯一标识）
            existing_keys = set()
            for p in existing_products:
                title = p.get('title', '').lower().strip()
                url = p.get('product_url', '') or ''
                key = f"{title}|{url}"
                existing_keys.add(key)
            
            # 找出新产品（不在现有数据中的）
            new_products = []
            for p in eerder_products:
                title = p.get('title', '').lower().strip()
                url = p.get('product_url', '') or ''
                key = f"{title}|{url}"
                if key not in existing_keys:
                    new_products.append(p)
                    existing_keys.add(key)  # 避免重复添加
            
            # 合并数据：现有产品 + 新产品
            all_products = existing_products + new_products
            
            if new_products:
                print(f"📦 发现 {len(new_products)} 个新的eerder-gekocht产品，追加到数据库")
            else:
                print(f"ℹ️  没有新的eerder-gekocht产品需要添加")
            
            # 保存更新后的数据
            eerder_data = {
                "timestamp": datetime.now().isoformat(),
                "products": all_products
            }
            with open(eerder_file, 'w', encoding='utf-8') as f:
                json.dump(eerder_data, f, ensure_ascii=False, indent=2)
            print(f"✅ eerder-gekocht数据已保存到 {eerder_file} (总计 {len(all_products)} 个产品，本次新增 {len(new_products)} 个)")
        except Exception as e:
            print(f"⚠️ 保存eerder-gekocht数据失败: {e}")
    
    def _save_cache(self, products: List[Dict[str, Any]]):
        """
        Save products to cache with timestamp
        Only save bonus products to cache, eerder-gekocht products are saved separately
        """
        try:
            # Only save bonus products to cache (eerder-gekocht are saved separately)
            bonus_products = [p for p in products if p.get("source") == "bonus"]
            cache_data = {
                'timestamp': datetime.now().isoformat(),
                'products': bonus_products
            }
            with open(self.config.products_cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            print(f"✅ Bonus products cached to {self.config.products_cache_file} ({len(bonus_products)} 个产品)")
        except Exception as e:
            print(f"⚠️ Error saving cache: {e}")
    
    def delete_cache(self):
        """Delete cache file completely"""
        if os.path.exists(self.config.products_cache_file):
            try:
                os.remove(self.config.products_cache_file)
                print(f"🗑️  Deleted cache file: {self.config.products_cache_file}")
            except Exception as e:
                print(f"⚠️ Error deleting cache file: {e}")
    
    def _try_lightweight_scrape(self) -> Optional[List[Dict[str, Any]]]:
        """Try to scrape using lightweight requests + BeautifulSoup"""
        print("🔍 Attempting lightweight scrape (requests + BeautifulSoup)...")
        
        try:
            response = self.session.get(
                self.config.ah_bonus_url,
                timeout=self.config.request_timeout
            )
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for product data in various possible formats
            products = []
            
            # Method 1: Look for JSON-LD or script tags with product data
            scripts = soup.find_all('script', type='application/json')
            for script in scripts:
                try:
                    data = json.loads(script.string)
                    # Try to extract product data from JSON structure
                    if isinstance(data, dict) and 'products' in data:
                        products = data['products']
                        break
                except:
                    continue
            
            # Method 2: Look for product cards in HTML
            if not products:
                product_cards = soup.find_all(attrs={'data-testhook': 'promotion-card'})
                if not product_cards:
                    # Try alternative selectors
                    product_cards = soup.find_all('div', class_=lambda x: x and 'promotion' in x.lower())
                
                for card in product_cards[:self.config.max_products]:
                    try:
                        product = self._extract_product_from_html(card)
                        if product:
                            products.append(product)
                    except:
                        continue
            
            if products:
                print(f"✅ Lightweight scrape successful: found {len(products)} products")
                return products
            else:
                print("ℹ️ Lightweight scrape found no products (page may be dynamically loaded)")
                return None
                
        except Exception as e:
            print(f"ℹ️ Lightweight scrape failed: {e}")
            print("   Falling back to Selenium...")
            return None
    
    def _extract_product_from_html(self, element) -> Optional[Dict[str, Any]]:
        """Extract product information from HTML element"""
        try:
            # Extract title
            title_elem = element.find(attrs={'data-testhook': 'promotion-card-title'})
            if not title_elem:
                title_elem = element.find('h1') or element.find('h2') or element.find('h3') or element.find('h4')
            
            title = title_elem.get_text(strip=True) if title_elem else ""
            if not title:
                return None
            
            # Extract price
            price_info = self._extract_price_from_html(element)
            
            # Extract description
            desc_elem = element.find(attrs={'data-testhook': 'card-description'})
            description = desc_elem.get_text(strip=True) if desc_elem else title
            
            # Extract image URL
            img_elem = element.find('img')
            image_url = ""
            if img_elem:
                image_url = img_elem.get('src') or img_elem.get('data-src') or ""
            
            # Extract product URL - 优先查找包含 /producten/ 的链接
            product_url = ""
            link_elems = element.find_all('a', href=True)
            for link_elem in link_elems:
                href = link_elem.get('href', '')
                if href and "/producten/" in href:
                    product_url = href
                    break
            
            # 如果没有找到，使用第一个链接
            if not product_url and link_elems:
                product_url = link_elems[0].get('href', '')
            
            if product_url and not product_url.startswith("http"):
                product_url = self.config.ah_base_url + product_url
            
            # Extract promotion quantity (e.g., "2 voor 3.99" -> quantity = 2)
            promotion_quantity = 1
            try:
                import re
                # 尝试多个选择器来找到promotion quantity
                shield_elem = None
                shield_selectors = [
                    {'data-testid': 'product-shield'},
                    {'class': lambda x: x and 'shield' in str(x).lower()},
                    {'class': lambda x: x and 'promotion' in str(x).lower()}
                ]
                
                for selector in shield_selectors:
                    try:
                        shield_elem = element.find(attrs=selector)
                        if shield_elem:
                            break
                    except:
                        continue
                
                shield_text = ""
                if shield_elem:
                    # 尝试找到shield_text元素
                    shield_text_elem = shield_elem.find(class_='shield_text__kNeiW')
                    if shield_text_elem:
                        shield_text = shield_text_elem.get_text(strip=True)
                    else:
                        shield_text = shield_elem.get_text(strip=True)
                
                # 如果没找到shield，尝试从整个element的文本中提取
                if not shield_text:
                    shield_text = element.get_text(strip=True)
                
                # 尝试多种正则表达式模式来匹配
                # 优先匹配开头的数字（第一个数字最重要）
                # 注意：第一个数字是关键，表示需要购买的数量
                patterns = [
                    r'^(\d+)[eE]\s*halve',      # "2E halve prijse" 或 "2e halve prijs" 或 "2Ehalve" - 开头数字+E+halve（E后可能有空格）
                    r'^(\d+)\s+voor',           # "2 voor 2.29" 或 "3 voor 5.00" - 开头数字+空格+voor
                    r'^(\d+)voor',              # "2voor" 或 "3voor" - 开头数字+voor（无空格）
                    r'^(\d+)\s+voor\s+\d+',    # "2 voor 2.29" - 确保匹配"数字 voor 价格"格式
                    r'(\d+)\s+voor',            # "2 voor" 或 "3 voor" - 任意位置的数字+voor（备用）
                    r'^(\d+)x',                 # "2x" 或 "3x" - 开头的数字+x
                    r'^(\d+)\s*x',              # "2 x" 或 "3 x" - 开头的数字+空格+x
                    r'(\d+)x',                  # "2x" 或 "3x" - 任意位置的数字+x（备用）
                    r'(\d+)\s*x',               # "2 x" 或 "3 x" - 任意位置的数字+空格+x（备用）
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, shield_text, re.IGNORECASE)
                    if match:
                        promotion_quantity = int(match.group(1))
                        if promotion_quantity > 1:  # 只接受大于1的值
                            break
            except Exception as e:
                # 如果提取失败，保持默认值1
                pass
            
            return {
                "title": title,
                "price": price_info.get("formatted_price", "Unknown"),
                "current_price": price_info.get("current_price", ""),
                "original_price": price_info.get("original_price", ""),
                "discount": price_info.get("discount_percent", 0),
                "description": description,
                "image_url": image_url,
                "product_url": product_url,  # 保存 product_url
                "promotion_quantity": promotion_quantity,  # e.g., 2 for "2 voor 3.99"
                "source": "bonus"  # 标记来源为 bonus
            }
        except:
            return None
    
    def _extract_price_from_html(self, element) -> Dict[str, Any]:
        """Extract price information from HTML element"""
        price_info = {
            "current_price": "",
            "original_price": "",
            "formatted_price": "",
            "discount_percent": 0
        }
        
        try:
            price_elem = element.find(attrs={'data-testhook': 'price'})
            if price_elem:
                current_price = price_elem.get('data-testpricenow')
                original_price = price_elem.get('data-testpricewas')
                
                if current_price:
                    price_info["current_price"] = f"€{current_price}"
                if original_price:
                    price_info["original_price"] = f"€{original_price}"
                
                if current_price and original_price:
                    try:
                        current_float = float(current_price)
                        original_float = float(original_price)
                        discount = round(((original_float - current_float) / original_float) * 100)
                        price_info["discount_percent"] = discount
                        price_info["formatted_price"] = (
                            f"€{current_price} (was €{original_price}, discount {discount}%)"
                        )
                    except:
                        price_info["formatted_price"] = f"€{current_price} (was €{original_price})"
                elif current_price:
                    price_info["formatted_price"] = f"€{current_price}"
                else:
                    price_text = price_elem.get_text(strip=True)
                    if price_text:
                        price_info["formatted_price"] = price_text
        except:
            pass
        
        return price_info
    
    def _setup_driver(self):
        """Setup Chrome driver (legacy method, without SessionManager)"""
        if self.driver:
            return
            
        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        # 不resize窗口，保持默认大小
    
    def _scroll_to_load_all_products(self, max_scrolls: int = 10, scroll_delay: float = 1.5):
        """
        滚动到页面3/4位置多次以加载所有产品（处理动态加载）
        每次滚动到页面的3/4位置，触发内容加载，然后继续滚动
        
        Args:
            max_scrolls: 最大滚动次数
            scroll_delay: 每次滚动后的等待时间（秒）
        """
        product_selectors = [
            "[data-testhook='promotion-card']",
            "[data-testhook='product-card']",
            "[data-testid='product-card']",
        ]
        
        print("   📜 滚动到页面3/4位置加载产品...")
        
        last_count = 0
        scroll_attempts = 0
        no_change_count = 0  # 连续没有变化的次数
        max_no_change = 3  # 连续3次没有变化就停止
        
        while scroll_attempts < max_scrolls:
            # 获取当前产品数量
            current_count = 0
            for selector in product_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        current_count = len(elements)
                        break
                except:
                    continue
            
            # 如果产品数量没有变化
            if current_count == last_count:
                no_change_count += 1
                if no_change_count >= max_no_change:
                    print(f"   ✅ 产品数量稳定（共 {current_count} 个），停止滚动")
                    break
            else:
                no_change_count = 0  # 重置计数器
                if scroll_attempts > 0:
                    print(f"   📦 已加载 {current_count} 个产品（+{current_count - last_count}）...")
            
            # 获取当前页面高度
            document_height = self.driver.execute_script("return document.body.scrollHeight;")
            scroll_position = self.driver.execute_script("return window.pageYOffset;")
            
            # 滚动到页面的3/4位置（而不是直接到底部）
            target_scroll = int(document_height * 0.75)
            
            # 如果已经超过3/4位置，就滚动到底部
            if scroll_position >= target_scroll:
                # 滚动到底部
                self.driver.execute_script("window.scrollTo({top: document.body.scrollHeight, behavior: 'auto'});")
            else:
                # 滚动到3/4位置
                self.driver.execute_script(f"window.scrollTo({{top: {target_scroll}, behavior: 'auto'}});")
            
            # 等待内容加载
            time.sleep(scroll_delay)
            
            last_count = current_count
            scroll_attempts += 1
            
            # 每2次滚动显示一次进度
            if scroll_attempts % 2 == 0:
                print(f"   ⏳ 滚动中... ({scroll_attempts}/{max_scrolls})，当前 {current_count} 个产品")
        
        # 最后再确认一次滚动到底部，确保所有内容都加载
        print("   📜 最后滚动到底部确保所有内容加载...")
        self.driver.execute_script("window.scrollTo({top: document.body.scrollHeight, behavior: 'auto'});")
        time.sleep(scroll_delay)
        
        # 再次检查产品数量
        final_count = 0
        for selector in product_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    final_count = len(elements)
                    break
            except:
                continue
        
        print(f"✅ 滚动完成，共加载 {final_count} 个产品")
    
    def _setup_driver_with_session(self):
        """Setup Chrome driver using SessionManager (for sharing browser session)"""
        if self.driver:
            try:
                # 检查driver是否仍然有效
                self.driver.current_url
                return
            except:
                # driver已失效，需要重新创建
                self.driver = None
        
        # 如果有SessionManager，使用它创建driver（可以共享cookies和登录状态）
        if self.session_manager:
            print("🚀 正在启动浏览器（使用SessionManager）...")
            self.driver = self.session_manager.create_driver(headless=False)
        else:
            # 没有SessionManager，使用传统方法
            self._setup_driver()
    
    def scrape_bonus_products(self, use_cache: bool = True, 
                             prefer_lightweight: bool = True,
                             use_selenium: bool = True,
                             wait_for_login: bool = True) -> List[Dict[str, Any]]:
        """
        Scrape bonus products only (eerder-gekocht scraping is separated)
        
        Args:
            use_cache: Whether to use cache if available
            prefer_lightweight: Whether to try lightweight method first
            use_selenium: Whether to use Selenium (default: True, opens browser and waits for login)
            wait_for_login: Whether to wait for user login before scraping (default: True)
        
        Returns:
            List of bonus product dictionaries
        """
        # Step 1: Check cache - if present, skip scraping
        if use_cache:
            cached_products = self._load_cache()
            if cached_products:
                print(f"✅ Using {len(cached_products)} cached bonus products (skipping scrape)")
                return cached_products
        
        print("🔍 Starting to scrape AH.nl/bonus page...")
        
        # Step 2: Try lightweight method first (faster, no browser needed)
        if prefer_lightweight:
            products = self._try_lightweight_scrape()
            if products:
                # 保存bonus数据到JSON文件
                self._save_bonus_products(products)
                self._save_cache(products)
                return products
        
        # Step 3: Use Selenium (opens browser and waits for login)
        if use_selenium:
            print("🌐 Using Selenium (will open browser and wait for login)...")
            return self._scrape_with_selenium(wait_for_login=wait_for_login)
        else:
            print("⚠️ Lightweight scrape failed and Selenium is disabled")
            print("   To enable Selenium scraping, set use_selenium=True")
            print("   Or ensure cache is available (products_cache.json)")
            return []
    
    def _scrape_with_selenium(self, wait_for_login: bool = True) -> List[Dict[str, Any]]:
        """Scrape using Selenium (original method, improved)"""
        # 检查是否已有driver，避免重复创建
        if not self.driver:
            self._setup_driver_with_session()
        
        try:
            # 如果需要等待登录，先确保用户已登录（除非是自动模式）
            if wait_for_login is None:
                wait_for_login = not self.config.auto_mode
            
            if wait_for_login and self.session_manager and not self.config.auto_mode:
                print("\n🔐 检查登录状态...")
                if not self.session_manager.check_login_status(self.driver, self.config.ah_base_url):
                    print("⚠️ 未登录，等待用户登录...")
                    self.session_manager.wait_for_manual_login(self.driver, timeout=300)
            elif self.config.auto_mode:
                print("\n🤖 自动模式：跳过登录等待，使用已保存的cookies")
            
            # Visit bonus page
            print(f"🌐 Visiting: {self.config.ah_bonus_url}")
            self.driver.get(self.config.ah_bonus_url)
            time.sleep(3)  # Wait for page to load
            
            # Accept cookies with multiple strategies (quick check, don't wait too long)
            print("🍪 Looking for cookie consent dialog...")
            cookie_accepted = False
            
            # Strategy 1: Try multiple selectors for Accept button (short timeout to avoid blocking)
            accept_selectors = [
                # By data-testid (most reliable - matches current AH.nl structure)
                "//button[@data-testid='accept-cookies']",
                # By text content (most common)
                "//button[contains(text(), 'Accepteren')]",
                "//button[contains(text(), 'Accept')]",
            ]
            
            for selector in accept_selectors:
                try:
                    # 使用很短的超时时间，避免卡住
                    cookie_button = WebDriverWait(self.driver, 1).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    # Scroll button into view if needed
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", cookie_button)
                    time.sleep(0.5)
                    cookie_button.click()
                    print("✅ Cookies accepted")
                    cookie_accepted = True
                    time.sleep(1)  # Wait for dialog to close
                    break
                except:
                    continue
            
            # Strategy 2: Quick check for dialog (don't wait long)
            if not cookie_accepted:
                try:
                    # Quick check for cookie dialog (no wait)
                    dialog = self.driver.find_element(By.XPATH, 
                        "//dialog[@data-testid='cookie-popup'] | //div[@data-testid='cookie-popup']")
                    if dialog.is_displayed():
                        accept_button = dialog.find_element(By.XPATH, 
                            ".//button[@data-testid='accept-cookies']")
                        if accept_button:
                            accept_button.click()
                            print("✅ Cookies accepted (found in dialog)")
                            cookie_accepted = True
                            time.sleep(1)
                except:
                    pass
            
            if not cookie_accepted:
                print("⚠️ Cookie banner not found - continuing anyway (不会卡住)")
            
            # Short wait to ensure page is ready
            time.sleep(1)
            
            # 只抓取bonus页面和eerder-gekocht页面，不滚动加载所有产品
            print("📦 抓取bonus页面产品...")
            products = []
            
            # 抓取bonus页面（当前页面）
            product_elements = self.driver.find_elements(By.CSS_SELECTOR, 
                "[data-testhook='promotion-card']")
            
            print(f"📦 从bonus页面提取 {len(product_elements)} 个产品信息...")
            
            failed_extractions = 0
            for i, element in enumerate(product_elements):
                try:
                    # Extract title with multiple fallback strategies
                    title = ""
                    try:
                        title_elem = element.find_element(By.CSS_SELECTOR, 
                            "[data-testhook='promotion-card-title']")
                        title = title_elem.text.strip()
                    except:
                        # Try alternative selectors
                        title_selectors = [
                            "[data-testhook='promotion-card-title']",
                            "[data-testhook*='title']",
                            "[data-testhook*='name']",
                            "h1", "h2", "h3", "h4", "h5",
                            "a[href*='/producten/']",
                            "[class*='title']",
                            "[class*='name']",
                            ".promotion-card-title_root__YObeO",
                            "[class*='promotion-card-title']",
                        ]
                        for selector in title_selectors:
                            try:
                                title_elem = element.find_element(By.CSS_SELECTOR, selector)
                                title = title_elem.text.strip()
                                if title and len(title) > 2:  # Ensure title is meaningful
                                    break
                            except:
                                continue
                    
                    # If still no title, try getting text from the element itself
                    if not title:
                        try:
                            title = element.text.strip().split('\n')[0].strip()
                            if len(title) < 2 or len(title) > 200:  # Sanity check
                                title = ""
                        except:
                            pass
                    
                    if not title:
                        failed_extractions += 1
                        if failed_extractions <= 3:  # Only show first 3 failures for debugging
                            try:
                                element_html = element.get_attribute('outerHTML')[:200]
                                print(f"   ⚠️  Failed to extract title from element {i+1}: {element_html}...")
                            except:
                                pass
                        continue
                    
                    # Extract price
                    price_info = self._extract_price_selenium(element)
                    
                    # Extract description
                    description = ""
                    try:
                        desc_elem = element.find_element(By.CSS_SELECTOR, 
                            "[data-testhook='card-description']")
                        description = desc_elem.text.strip()
                    except:
                        pass
                    
                    # Extract image URL
                    image_url = ""
                    try:
                        img_elem = element.find_element(By.TAG_NAME, "img")
                        image_url = (img_elem.get_attribute("src") or 
                                   img_elem.get_attribute("data-src") or "")
                    except:
                        pass
                    
                    # Extract product URL - 优先查找包含 /producten/ 的链接（最可靠）
                    product_url = ""
                    try:
                        # 方法1: 查找所有链接，优先选择包含 /producten/ 的链接
                        link_elems = element.find_elements(By.TAG_NAME, "a")
                        for link_elem in link_elems:
                            href = link_elem.get_attribute("href")
                            if href and "/producten/" in href:
                                product_url = href
                                break
                        
                        # 方法2: 如果没有找到，使用第一个链接
                        if not product_url and link_elems:
                            product_url = link_elems[0].get_attribute("href")
                        
                        # 方法3: 从 element 本身获取 href（如果 element 是链接）
                        if not product_url:
                            product_url = element.get_attribute("href")
                        
                        # 方法4: 查找 data-testhook="product-card" 的链接
                        if not product_url:
                            try:
                                link_elem = element.find_element(By.CSS_SELECTOR, "a[data-testhook='product-card']")
                                product_url = link_elem.get_attribute("href")
                            except:
                                pass
                        
                        # 确保 URL 是完整的（如果不是以 http 开头，添加 base URL）
                        if product_url and not product_url.startswith("http"):
                            product_url = self.config.ah_base_url + product_url
                    except Exception as e:
                        # 静默失败，继续处理
                        pass
                    
                    # Extract promotion quantity (e.g., "2 voor 3.99" -> quantity = 2)
                    promotion_quantity = 1
                    try:
                        # 尝试多个选择器来找到promotion quantity
                        shield_selectors = [
                            "[data-testid='product-shield'] .shield_text__kNeiW",
                            ".shield_text__kNeiW",
                            "[data-testid='product-shield']",
                            "[class*='shield']",
                            "[class*='promotion']"
                        ]
                        
                        shield_text = ""
                        for selector in shield_selectors:
                            try:
                                shield_elem = element.find_element(By.CSS_SELECTOR, selector)
                                shield_text = shield_elem.text.strip()
                                if shield_text:
                                    break
                            except:
                                continue
                        
                        # 如果没找到shield，尝试从整个element的文本中提取
                        if not shield_text:
                            try:
                                shield_text = element.text.strip()
                            except:
                                pass
                        
                        # 尝试多种正则表达式模式来匹配
                        # 优先匹配开头的数字（第一个数字最重要）
                        # 注意：第一个数字是关键，表示需要购买的数量
                        patterns = [
                            r'^(\d+)[eE]\s*halve',      # "2E halve prijse" 或 "2e halve prijs" 或 "2Ehalve" - 开头数字+E+halve（E后可能有空格）
                            r'^(\d+)\s+voor',           # "2 voor 2.29" 或 "3 voor 5.00" - 开头数字+空格+voor
                            r'^(\d+)voor',              # "2voor" 或 "3voor" - 开头数字+voor（无空格）
                            r'^(\d+)\s+voor\s+\d+',     # "2 voor 2.29" - 确保匹配"数字 voor 价格"格式
                            r'(\d+)\s+voor',            # "2 voor" 或 "3 voor" - 任意位置的数字+voor（备用）
                            r'^(\d+)x',                 # "2x" 或 "3x" - 开头的数字+x
                            r'^(\d+)\s*x',              # "2 x" 或 "3 x" - 开头的数字+空格+x
                            r'(\d+)x',                  # "2x" 或 "3x" - 任意位置的数字+x（备用）
                            r'(\d+)\s*x',               # "2 x" 或 "3 x" - 任意位置的数字+空格+x（备用）
                        ]
                        
                        for pattern in patterns:
                            match = re.search(pattern, shield_text, re.IGNORECASE)
                            if match:
                                promotion_quantity = int(match.group(1))
                                if promotion_quantity > 1:  # 只接受大于1的值
                                    break
                    except Exception as e:
                        # 如果提取失败，保持默认值1
                        pass
                    
                    product = {
                        "title": title,
                        "price": price_info.get("formatted_price", "Unknown"),
                        "current_price": price_info.get("current_price", ""),
                        "original_price": price_info.get("original_price", ""),
                        "discount": price_info.get("discount_percent", 0),
                        "description": description or title,
                        "image_url": image_url,
                        "product_url": product_url,  # 保存 product_url
                        "promotion_quantity": promotion_quantity,  # e.g., 2 for "2 voor 3.99"
                        "source": "bonus"  # 标记来源为 bonus
                    }
                    
                    products.append(product)
                    
                except Exception as e:
                    continue
            
            bonus_count = len(products)
            print(f"✅ 从bonus页面抓取了 {bonus_count} 个产品")
            
            # 保存bonus数据到JSON文件
            if bonus_count > 0:
                self._save_bonus_products(products)
            
            # Note: eerder-gekocht scraping is now separated to previous_buy_scraper_main.py
            # Only return bonus products
            print(f"\n✅ 抓取了 {bonus_count} 个bonus产品")
            self._save_cache(products)
            return products
            
        except Exception as e:
            print(f"❌ Scraping failed: {e}")
            return []
        finally:
            # 不关闭driver，保持浏览器窗口打开，以便后续使用
            # driver会在CartAutomation中继续使用，或者保持打开供用户查看
            print("💡 浏览器窗口保持打开，供后续使用或查看")
            # 永远不关闭浏览器窗口，让用户手动关闭
    
    def get_driver(self):
        """获取当前的driver实例（用于传递给CartAutomation）"""
        return self.driver
    
    def _extract_price_selenium(self, element) -> Dict[str, Any]:
        """Extract price information from Selenium element"""
        price_info = {
            "current_price": "",
            "original_price": "",
            "formatted_price": "",
            "discount_percent": 0
        }
        
        try:
            price_elem = element.find_element(By.CSS_SELECTOR, "[data-testhook='price']")
            current_price = price_elem.get_attribute("data-testpricenow")
            original_price = price_elem.get_attribute("data-testpricewas")
            
            if current_price:
                price_info["current_price"] = f"€{current_price}"
            if original_price:
                price_info["original_price"] = f"€{original_price}"
                
            # Calculate discount if available
            if current_price and original_price:
                try:
                    curr = float(current_price)
                    orig = float(original_price)
                    discount = ((orig - curr) / orig) * 100
                    price_info["discount_percent"] = round(discount)
                except:
                    pass
                    
            # Format price for display
            if current_price:
                price_info["formatted_price"] = f"€{current_price}"
            else:
                # Fallback: try to extract from text
                try:
                    price_text = element.find_element(By.CSS_SELECTOR, "[data-testid='price-amount']").text
                    price_info["formatted_price"] = price_text
                except:
                    price_info["formatted_price"] = "Unknown"
                    
        except:
            # If price extraction fails, set formatted price to Unknown
            price_info["formatted_price"] = "Unknown"
            
        return price_info
    
    def summarize_products(self, products: List[Dict[str, Any]]) -> str:
        """Summarize all discount products"""
        if not products:
            return "No discount products found"
        
        summary = f"📊 AH.nl Discount Products Summary\n"
        summary += f"=" * 50 + "\n"
        summary += f"Total products: {len(products)}\n\n"
        
        # Categorize by discount
        high_discount = [p for p in products if p.get("discount", 0) >= 30]
        medium_discount = [p for p in products if 10 <= p.get("discount", 0) < 30]
        low_discount = [p for p in products if 0 < p.get("discount", 0) < 10]
        
        summary += f"High discount (≥30%): {len(high_discount)} products\n"
        summary += f"Medium discount (10-29%): {len(medium_discount)} products\n"
        summary += f"Low discount (<10%): {len(low_discount)} products\n\n"
        
        # Show top 10 high discount products
        summary += "🔥 Top 10 High Discount Products:\n"
        sorted_products = sorted(products, key=lambda x: x.get("discount", 0), reverse=True)
        for i, product in enumerate(sorted_products[:10], 1):
            summary += f"  {i}. {product['title']} - {product['price']}\n"
        
        return summary

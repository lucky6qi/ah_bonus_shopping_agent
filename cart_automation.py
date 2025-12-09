"""Elegant cart automation module"""
import time
import re
import json
import os
from pathlib import Path
from difflib import SequenceMatcher
from typing import List, Dict, Any, Optional, Callable
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from dataclasses import dataclass
from session_manager import SessionManager


@dataclass
class CartResult:
    """Cart operation result"""
    success: bool
    added_count: int
    failed_count: int
    failed_products: List[str]
    message: str


class CartAutomation:
    """Cart automation class - elegant and simple interface"""
    
    def __init__(self, base_url: str = "https://www.ah.nl", 
                 headless: bool = False,
                 user_data_dir: Optional[str] = None,
                 login_timeout: int = 300,
                 driver: Optional[webdriver.Chrome] = None,
                 session_manager: Optional[SessionManager] = None,
                 eerder_gekocht_file: Optional[str] = None):
        """
        Initialize cart automation
        
        Args:
            base_url: AH website base URL
            headless: Whether to use headless mode (False for user viewing and interaction)
            user_data_dir: Chrome用户数据目录路径，None则使用默认路径
            login_timeout: 登录超时时间（秒）
            driver: 可选的已有driver实例（用于复用scraper的浏览器窗口）
            session_manager: 可选的SessionManager实例（用于共享session）
            eerder_gekocht_file: eerder-gekocht数据文件路径
        """
        self.base_url = base_url
        self.headless = headless
        self.driver: Optional[webdriver.Chrome] = driver  # 可以使用已有的driver
        
        # 初始化SessionManager来管理cookies和登录状态
        if session_manager:
            self.session_manager = session_manager
        else:
            self.session_manager = SessionManager(user_data_dir=user_data_dir)
        self.login_timeout = login_timeout
        
        # 标记cookies是否已检查（避免重复检查）
        self._cookies_checked = False
        
        # eerder-gekocht数据库文件路径
        self.eerder_gekocht_file = eerder_gekocht_file or "eerder_gekocht_products.json"
        self._eerder_gekocht_cache: Optional[List[Dict[str, Any]]] = None
        
        # 如果已有driver，不需要再创建
        # 不在初始化时创建driver，延迟到真正需要时再创建
        # self._setup_driver()
    
    def _load_eerder_gekocht(self) -> List[Dict[str, Any]]:
        """加载 eerder-gekocht 数据库"""
        if self._eerder_gekocht_cache is not None:
            return self._eerder_gekocht_cache
        
        self._eerder_gekocht_cache = []
        try:
            if os.path.exists(self.eerder_gekocht_file):
                with open(self.eerder_gekocht_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict) and 'products' in data:
                        self._eerder_gekocht_cache = data['products']
                    elif isinstance(data, list):
                        self._eerder_gekocht_cache = data
        except Exception as e:
            print(f"⚠️ 加载 eerder-gekocht 数据失败: {e}")
        
        return self._eerder_gekocht_cache
    
    def _find_product_in_all_sources(self, product_title: str, 
                                     available_products: Optional[List[Dict[str, Any]]] = None,
                                     threshold: float = 0.5) -> Optional[Dict[str, Any]]:
        """
        在所有可用产品源（bonus + eerder-gekocht）中查找最匹配的产品
        
        Args:
            product_title: 要查找的产品名称（可能是中文或荷兰语）
            available_products: 可用的产品列表（通常包含 bonus 产品）
            threshold: 相似度阈值（0-1），默认0.5（降低阈值以提高匹配率）
            
        Returns:
            匹配的产品字典，如果没有找到则返回 None
        """
        # 收集所有产品源
        all_products = []
        
        # 1. 优先添加 bonus 产品（如果提供）- 通常有 product_url
        if available_products:
            all_products.extend(available_products)
        
        # 2. 添加 eerder-gekocht 产品
        eerder_products = self._load_eerder_gekocht()
        if eerder_products:
            all_products.extend(eerder_products)
        
        if not all_products:
            return None
        
        # 标准化搜索词（转小写，去除多余空格）
        search_title = product_title.lower().strip()
        # 提取关键词（去除常见词如 "ah", "x2", "1l" 等）
        search_keywords = [kw for kw in search_title.split() 
                          if kw not in ['ah', 'x2', 'x1', 'x3', 'x4', '1l', '2l', '500g', '300g'] 
                          and len(kw) > 2]
        
        best_match = None
        best_score = 0.0
        best_has_url = False
        
        for product in all_products:
            product_name = product.get('title', '').lower().strip()
            if not product_name:
                continue
            
            has_url = bool(product.get('product_url'))
            
            # 计算相似度
            # 1. 完全匹配（最高优先级）
            if product_name == search_title:
                return product
            
            # 2. 关键词匹配（提高优先级）
            keyword_matches = sum(1 for kw in search_keywords if kw in product_name)
            keyword_score = keyword_matches / len(search_keywords) if search_keywords else 0
            
            # 3. 包含匹配
            contains_match = search_title in product_name or product_name in search_title
            
            # 4. 模糊匹配
            fuzzy_score = SequenceMatcher(None, search_title, product_name).ratio()
            
            # 综合评分：关键词匹配权重更高，有 URL 的产品优先
            if keyword_score > 0:
                score = keyword_score * 0.6 + fuzzy_score * 0.4
            elif contains_match:
                score = fuzzy_score * 1.2  # 包含匹配加分
            else:
                score = fuzzy_score
            
            # 优先选择有 URL 的产品
            if has_url and not best_has_url:
                # 如果有 URL 的产品，即使分数稍低也优先选择
                if score >= threshold * 0.8:  # 降低阈值要求
                    best_score = score
                    best_match = product
                    best_has_url = True
            elif has_url == best_has_url:
                # 如果都有 URL 或都没有 URL，选择分数更高的
                if score > best_score:
                    best_score = score
                    best_match = product
                    best_has_url = has_url
            elif not has_url and best_has_url:
                # 如果当前没有 URL 但之前找到的有 URL，跳过
                continue
        
        # 如果相似度超过阈值，返回最佳匹配
        if best_score >= threshold and best_match:
            return best_match
        
        return None
    
    def _find_product_in_eerder_gekocht(self, product_title: str, threshold: float = 0.6) -> Optional[Dict[str, Any]]:
        """
        在 eerder-gekocht 数据库中查找最匹配的产品（保留向后兼容）
        
        Args:
            product_title: 要查找的产品名称（可能是中文或荷兰语）
            threshold: 相似度阈值（0-1），默认0.6
            
        Returns:
            匹配的产品字典，如果没有找到则返回 None
        """
        return self._find_product_in_all_sources(product_title, available_products=None, threshold=threshold)
    
    def _setup_driver(self):
        """Setup Chrome driver using SessionManager"""
        # 如果driver已存在，直接返回
        if self.driver:
            try:
                # 检查driver是否仍然有效
                self.driver.current_url
                return
            except:
                # driver已失效，需要重新创建
                self.driver = None
        
        # 使用SessionManager创建driver，会自动使用用户数据目录保存cookies
        print("🚀 正在启动浏览器...")
        self.driver = self.session_manager.create_driver(headless=self.headless)
    
    def _accept_cookies(self, silent: bool = False):
        """
        Accept cookies (only check once, don't spam)
        
        Args:
            silent: If True, don't print messages
        """
        if not silent:
            print("🍪 Looking for cookie consent dialog...")
        
        # Quick check with short timeout to avoid blocking
        accept_selectors = [
            "//button[@data-testid='accept-cookies']",
            "//button[contains(text(), 'Accepteren')]",
        ]
        
        for selector in accept_selectors:
            try:
                cookie_button = WebDriverWait(self.driver, 1).until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                self.driver.execute_script("arguments[0].click();", cookie_button)
                if not silent:
                    print("✅ Cookies accepted")
                time.sleep(0.3)
                return True
            except:
                continue
        
        # Quick check for dialog
        try:
            dialog = self.driver.find_element(By.XPATH, 
                "//dialog[@data-testid='cookie-popup'] | //div[@data-testid='cookie-popup']")
            if dialog.is_displayed():
                accept_button = dialog.find_element(By.XPATH, 
                    ".//button[@data-testid='accept-cookies']")
                if accept_button:
                    self.driver.execute_script("arguments[0].click();", accept_button)
                    if not silent:
                        print("✅ Cookies accepted")
                    time.sleep(0.3)
                    return True
        except:
            pass
        
        # Don't print warning if silent mode
        if not silent:
            print("⚠️ Cookie banner not found - continuing anyway")
        return False
    
    def _ensure_logged_in(self) -> bool:
        """Ensure user is logged in (if not logged in, wait for manual login)"""
        # 使用SessionManager来检查和管理登录状态
        return self.session_manager.ensure_logged_in(
            driver=self.driver,
            base_url=self.base_url,
            auto_wait=True
        )
    
    def _find_product_by_url(self, product_url: str) -> bool:
        """Access product page via product URL"""
        try:
            if not product_url.startswith("http"):
                product_url = self.base_url + product_url
            self.driver.get(product_url)
            time.sleep(0.1)
            # Don't check cookies here - already checked at the beginning
            return True
        except Exception:
            # Don't print error details to avoid spam
            return False
    
    def _find_product_in_current_page(self, product_title: str) -> bool:
        """
        在当前页面查找产品（如果已经在产品列表页面）
        
        Args:
            product_title: 产品标题
            
        Returns:
            True如果找到并点击了产品，False如果没找到
        """
        try:
            # 检查当前页面是否是产品列表页面
            current_url = self.driver.current_url
            if '/producten/' not in current_url and '/bonus/' not in current_url:
                return False
            
            # 查找所有产品卡片
            product_cards = self.driver.find_elements(By.CSS_SELECTOR,
                "[data-testid='product-card'], [data-testhook='product-card'], .product-card")
            
            if not product_cards:
                return False
            
            # 将产品标题转换为小写便于比较
            title_lower = product_title.lower()
            
            # 遍历产品卡片，查找匹配的产品
            for card in product_cards:
                try:
                    # 尝试获取产品标题
                    title_elem = None
                    title_selectors = [
                        "[data-testid='product-title']",
                        "[data-testhook='product-title']",
                        ".product-title",
                        "h2, h3, h4",
                    ]
                    
                    for selector in title_selectors:
                        try:
                            title_elem = card.find_element(By.CSS_SELECTOR, selector)
                            if title_elem and title_elem.text.strip():
                                break
                        except:
                            continue
                    
                    if not title_elem:
                        continue
                    
                    card_title = title_elem.text.strip().lower()
                    
                    # 检查是否匹配（完全匹配或部分匹配）
                    if title_lower == card_title or title_lower in card_title or card_title in title_lower:
                        # 找到匹配的产品，点击进入详情页
                        # 先尝试找到链接
                        link_elem = None
                        try:
                            link_elem = card.find_element(By.CSS_SELECTOR, "a[href*='/producten/']")
                        except:
                            # 如果没有链接，直接点击卡片
                            pass
                        
                        if link_elem:
                            self.driver.execute_script("arguments[0].click();", link_elem)
                        else:
                            self.driver.execute_script("arguments[0].click();", card)
                        
                        time.sleep(1.5)
                        return True
                except:
                    continue
            
            return False
        except Exception:
            return False
    
    def _find_product_by_search(self, product_title: str) -> bool:
        """Find product by search"""
        try:
            # 首先尝试在当前页面查找产品（如果已经在产品列表页面）
            if self._find_product_in_current_page(product_title):
                return True
            
            # 尝试在当前页面直接查找搜索框（不需要回到主页）
            # 大多数页面都有搜索框，包括商品详情页
            search_selectors = [
                "[data-testhook='search-input']",
                "input[placeholder*='Zoeken']",
                "input[type='search']",
                "#navigation-search-input",
            ]
            
            search_box = None
            for selector in search_selectors:
                try:
                    # 快速检查当前页面是否有搜索框
                    search_box = WebDriverWait(self.driver, 1).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    # Check if element is visible and enabled
                    if not search_box.is_displayed() or not search_box.is_enabled():
                        continue
                    break
                except:
                    continue
            
            # 如果当前页面没有搜索框，才回到主页
            if not search_box:
                current_url = self.driver.current_url
                if '/mijnlijst' not in current_url:  # 购物车页面通常也有搜索框，但为了保险起见
                    self.driver.get(self.base_url)
                    time.sleep(1)
                    
                    # 重新查找搜索框
                    for selector in search_selectors:
                        try:
                            search_box = WebDriverWait(self.driver, 2).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                            )
                            if not search_box.is_displayed() or not search_box.is_enabled():
                                continue
                            break
                        except:
                            continue
            
            if not search_box:
                return False
            
            # Use JavaScript to interact with search box (more reliable)
            try:
                # Clear and set value via JavaScript
                self.driver.execute_script("arguments[0].value = '';", search_box)
                self.driver.execute_script("arguments[0].value = arguments[1];", search_box, product_title)
                
                # Trigger events
                self.driver.execute_script("""
                    arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                    arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                    arguments[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
                """, search_box)
                
                # Try pressing Enter
                from selenium.webdriver.common.keys import Keys
                try:
                    search_box.send_keys(Keys.RETURN)
                except:
                    # If that fails, try clicking submit button or form
                    try:
                        form = search_box.find_element(By.XPATH, "./ancestor::form")
                        form.submit()
                    except:
                        pass
                
                time.sleep(2)  # Wait for search results
            except Exception:
                # If JavaScript fails, try normal method as fallback
                try:
                    search_box.clear()
                    search_box.send_keys(product_title)
                    search_box.send_keys(Keys.RETURN)
                    time.sleep(2)  # Wait for search results
                except:
                    return False
            
            # Click first search result
            first_result_selectors = [
                "[data-testid='product-card']",
                "[data-testhook='product-card']",
                ".product-card",
                "a[href*='/producten/']",
            ]
            
            for selector in first_result_selectors:
                try:
                    # Wait for results
                    first_result = WebDriverWait(self.driver, 3).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    # Use JavaScript click (more reliable)
                    self.driver.execute_script("arguments[0].click();", first_result)
                    time.sleep(1.5)
                    return True
                except:
                    continue
            
            return False
        except Exception:
            # Don't print full error stack, just return False
            return False
    
    def _close_notification_popup(self):
        """Close notification popup if present"""
        try:
            # Look for the close button with data-testid
            close_button = WebDriverWait(self.driver, 2).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 
                    "button[data-testid='notification-tooltip-close']"))
            )
            if close_button.is_displayed():
                close_button.click()
                time.sleep(0.1)
                print("   ✅ Closed notification popup")
                return True
        except:
            pass
        
        # Try alternative selectors
        try:
            close_selectors = [
                "button[aria-label='Sluiten']",
                "button.close",
                ".notification-tooltip button",
                "[class*='close'] button"
            ]
            for selector in close_selectors:
                try:
                    close_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if close_button.is_displayed():
                        close_button.click()
                        time.sleep(0.5)
                        return True
                except:
                    continue
        except:
            pass
        
        return False
    
    def _add_to_cart(self, quantity: int = 1) -> bool:
        """
        Add product to cart on current product page
        
        Args:
            quantity: Number of items to add (default: 1)
        """
        # Close any notification popup first
        # self._close_notification_popup()
        # # Wait a bit for page to stabilize
        # time.sleep(0.1)
        
        # Step 1: Try to find and click "+" buttons directly first (skip "Kies" button)
        # Priority: Direct "+" buttons ONLY - avoid "Kies" button
        plus_button_clicked = False
        
        # Wait a bit longer for page to fully load before searching for buttons
        time.sleep(0.1)
        
        # Strategy 1: Try XPath with comprehensive patterns for "+" buttons
        try:
            variant_xpaths = [
                "//button[contains(text(), '+ Los')]",  # + Los
                "//button[contains(text(), '+ 6 Stuks')]",  # + 6 Stuks
                "//button[contains(text(), '+ 2 Stuks')]",  # + 2 Stuks
                "//button[contains(text(), '+ 3 Stuks')]",  # + 3 Stuks
                "//button[contains(text(), '+ 4 Stuks')]",  # + 4 Stuks
                "//button[contains(text(), '+ 5 Stuks')]",  # + 5 Stuks
                "//button[contains(text(), '+') and contains(text(), 'Los')]",  # Any + Los variant
                "//button[contains(text(), '+') and contains(text(), 'Stuks')]",  # Any + X Stuks variant
                "//button[starts-with(text(), '+')]",  # Any button starting with +
                "//button[contains(@aria-label, '+') and not(contains(@aria-label, 'Kies'))]",  # aria-label with +
                "//button[contains(@aria-label, 'toevoegen')]",  # Add to cart buttons
            ]
            
            for xpath in variant_xpaths:
                try:
                    variant_button = WebDriverWait(self.driver, 0.1).until(
                        EC.element_to_be_clickable((By.XPATH, xpath))
                    )
                    btn_text = variant_button.text.strip()
                    aria_label = variant_button.get_attribute("aria-label") or ""
                    
                    # Strict check: must have "+" and must NOT have "Kies"
                    has_plus = "+" in btn_text or "+" in aria_label or "Los" in btn_text or "Stuks" in btn_text
                    has_kies = "Kies" in btn_text or "Kies" in aria_label or "eenheid" in aria_label
                    
                    if has_plus and not has_kies:
                        print(f"   🔘 找到 '+' 按钮: text='{btn_text}', aria-label='{aria_label}'")
                        # Scroll to button first
                        self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", variant_button)
                        time.sleep(0.1)
                        self.driver.execute_script("arguments[0].click();", variant_button)
                        plus_button_clicked = True
                        print(f"   ✅ 已点击 '+' 按钮: {btn_text}")
                        time.sleep(0.1)
                        # self._close_notification_popup()
                        return True  # Successfully added, return immediately
                except TimeoutException:
                    continue
                except Exception as e:
                    continue
        except Exception as e:
            pass
        
        # Strategy 2: Search all buttons for "+" buttons (excluding "Kies")
        if not plus_button_clicked:
            try:
                for attempt in range(8):  # Increased attempts
                    all_buttons = self.driver.find_elements(By.TAG_NAME, "button")
                    
                    for btn in all_buttons:
                        try:
                            if btn.is_displayed() and btn.is_enabled():
                                btn_text = btn.text.strip()
                                btn_aria = btn.get_attribute("aria-label") or ""
                                
                                # Strict check: must have "+" and must NOT have "Kies"
                                has_plus = ("+" in btn_text or "Los" in btn_text or "Stuks" in btn_text or 
                                           "+" in btn_aria or "toevoegen" in btn_aria.lower())
                                has_kies = ("Kies" in btn_text or "Kies" in btn_aria or "eenheid" in btn_aria)
                                
                                if has_plus and not has_kies:
                                    print(f"   🔘 找到 '+' 按钮: text='{btn_text}', aria-label='{btn_aria}'")
                                    # Scroll to button first
                                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", btn)
                                    time.sleep(0.2)
                                    self.driver.execute_script("arguments[0].click();", btn)
                                    plus_button_clicked = True
                                    print(f"   ✅ 已点击 '+' 按钮: {btn_text}")
                                    time.sleep(0.3)
                                    self._close_notification_popup()
                                    return True  # Successfully added, return immediately
                        except:
                            continue
                    
                    if plus_button_clicked:
                        break
                    
                    # Wait before next attempt
                    if attempt < 7:
                        time.sleep(0.1)  # 100ms between attempts
            except Exception as e:
                print(f"   ⚠️  搜索 '+' 按钮时出错: {e}")
        
        # Strategy 3: Try CSS selectors for "+" buttons
        if not plus_button_clicked:
            try:
                plus_selectors = [
                    "button[data-testid='product-plus']",
                    "button[data-testhook='add-to-cart-button']",
                    "button[aria-label*='toevoegen']",
                    "button[aria-label*='Toevoegen']",
                ]
                
                for selector in plus_selectors:
                    try:
                        buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        for btn in buttons:
                            if btn.is_displayed() and btn.is_enabled():
                                btn_text = btn.text.strip()
                                btn_aria = btn.get_attribute("aria-label") or ""
                                
                                # Skip Kies buttons
                                if "Kies" not in btn_text and "Kies" not in btn_aria and "eenheid" not in btn_aria:
                                    print(f"   🔘 找到 '+' 按钮 (CSS): text='{btn_text}', aria-label='{btn_aria}'")
                                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", btn)
                                    time.sleep(0.2)
                                    self.driver.execute_script("arguments[0].click();", btn)
                                    plus_button_clicked = True
                                    print(f"   ✅ 已点击 '+' 按钮: {btn_text}")
                                    time.sleep(0.3)
                                    self._close_notification_popup()
                                    return True  # Successfully added, return immediately
                    except:
                        continue
            except Exception as e:
                pass
        
        # Only try "Kies" button as LAST RESORT if no "+" button was found
        # This should rarely happen - we prioritize "+" buttons above all else
        if not plus_button_clicked:
            print(f"   ⚠️  警告: 未找到 '+' 按钮，最后尝试一次搜索...")
            # Final attempt: wait a bit more and search again for "+" buttons
            time.sleep(0.5)
            try:
                all_buttons = self.driver.find_elements(By.TAG_NAME, "button")
                for btn in all_buttons:
                    try:
                        if btn.is_displayed() and btn.is_enabled():
                            btn_text = btn.text.strip()
                            btn_aria = btn.get_attribute("aria-label") or ""
                            # Must have "+" and must NOT have "Kies"
                            if ("+" in btn_text or "Los" in btn_text or "Stuks" in btn_text) and \
                               "Kies" not in btn_text and "Kies" not in btn_aria and "eenheid" not in btn_aria:
                                print(f"   🔘 最后尝试找到 '+' 按钮: text='{btn_text}', aria-label='{btn_aria}'")
                                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", btn)
                                time.sleep(0.2)
                                self.driver.execute_script("arguments[0].click();", btn)
                                plus_button_clicked = True
                                print(f"   ✅ 已点击 '+' 按钮: {btn_text}")
                                time.sleep(0.3)
                                self._close_notification_popup()
                                return True  # Successfully added
                    except:
                        continue
            except:
                pass
            
            # Only proceed with Kies if still no "+" button found
            if not plus_button_clicked:
                print(f"   ⚠️  警告: 仍然未找到 '+' 按钮，将尝试 'Kies' 按钮作为最后手段...")
                try:
                    # Try multiple selectors to find Kies button based on screenshot analysis
                    kies_button = None
                    kies_selectors = [
                        "button[data-testid^='product-control-wbtc-']",  # Matches product-control-wbtc-0, product-control-wbtc-1, etc.
                        "button[data-testid='product-control-wbtc-variant']",
                        "button[aria-label*='Kies']",
                        "button[aria-label*='eenheid']",
                    ]
                    
                    for selector in kies_selectors:
                        try:
                            buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                            for btn in buttons:
                                if btn.is_displayed():
                                    btn_text = btn.text.strip()
                                    aria_label = btn.get_attribute("aria-label") or ""
                                    # Check if this is a Kies button
                                    if "Kies" in btn_text or "Kies" in aria_label or "eenheid" in aria_label:
                                        kies_button = btn
                                        print(f"   🔍 找到 'Kies' 按钮: text='{btn_text}', aria-label='{aria_label}', selector='{selector}'")
                                        break
                            if kies_button:
                                break
                        except Exception as e:
                            continue
                    
                    if kies_button:
                        try:
                            # Check button state before clicking
                            is_enabled = kies_button.is_enabled()
                            is_displayed = kies_button.is_displayed()
                            aria_disabled = kies_button.get_attribute("aria-disabled")
                            kies_text = kies_button.text.strip()
                            aria_label = kies_button.get_attribute("aria-label") or ""
                            
                            print(f"   🔘 未找到 '+' 按钮，尝试点击 'Kies' 按钮...")
                            print(f"   📊 按钮状态: enabled={is_enabled}, displayed={is_displayed}, aria-disabled={aria_disabled}")
                            print(f"   📊 按钮信息: text='{kies_text}', aria-label='{aria_label}'")
                            
                            # Take screenshot before clicking for debugging
                            try:
                                screenshot_path = os.path.join(os.getcwd(), "uploads", f"kies_button_before_{int(time.time())}.png")
                                os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
                                kies_button.screenshot(screenshot_path)
                                print(f"   📸 已保存按钮截图: {screenshot_path}")
                            except Exception as e:
                                print(f"   ⚠️  截图保存失败: {e}")
                            
                            # Scroll to button first
                            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", kies_button)
                            time.sleep(0.3)
                            
                            # Wait for button to be clickable
                            WebDriverWait(self.driver, 3).until(
                                EC.element_to_be_clickable(kies_button)
                            )
                            
                            # Click the button
                            self.driver.execute_script("arguments[0].click();", kies_button)
                            print(f"   ✅ 已点击 'Kies' 按钮")
                            time.sleep(0.5)  # Wait for variant buttons to appear
                            
                            # Take screenshot after clicking
                            try:
                                screenshot_path = os.path.join(os.getcwd(), "uploads", f"kies_button_after_{int(time.time())}.png")
                                self.driver.save_screenshot(screenshot_path)
                                print(f"   📸 已保存页面截图: {screenshot_path}")
                            except Exception as e:
                                print(f"   ⚠️  截图保存失败: {e}")
                            
                            # After clicking "Kies", try to find "+" buttons again
                            try:
                                variant_xpaths = [
                                    "//button[contains(text(), '+ Los')]",
                                    "//button[contains(text(), '+ 6 Stuks')]",
                                    "//button[contains(text(), '+ 2 Stuks')]",
                                    "//button[contains(text(), '+') and contains(text(), 'Los')]",
                                    "//button[contains(text(), '+') and contains(text(), 'Stuks')]",
                                    "//button[starts-with(text(), '+')]",
                                ]
                                
                                for xpath in variant_xpaths:
                                    try:
                                        variant_button = WebDriverWait(self.driver, 2).until(
                                            EC.element_to_be_clickable((By.XPATH, xpath))
                                        )
                                        btn_text = variant_button.text.strip()
                                        if "Kies" not in btn_text and ("+" in btn_text or "Los" in btn_text or "Stuks" in btn_text):
                                            print(f"   🔘 点击 'Kies' 后找到 '+' 按钮: {btn_text}")
                                            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", variant_button)
                                            time.sleep(0.2)
                                            self.driver.execute_script("arguments[0].click();", variant_button)
                                            plus_button_clicked = True
                                            print(f"   ✅ 已点击 '+' 按钮: {btn_text}")
                                            break
                                    except TimeoutException:
                                        continue
                                    except Exception as e:
                                        print(f"   ⚠️  查找 '+' 按钮时出错: {e}")
                                        continue
                                
                                if not plus_button_clicked:
                                    print(f"   ⚠️  点击 'Kies' 后仍未找到 '+' 按钮")
                            except Exception as e:
                                print(f"   ⚠️  查找 '+' 按钮失败: {e}")
                        except Exception as e:
                            print(f"   ⚠️  点击 'Kies' 按钮失败: {e}")
                            import traceback
                            print(f"   📋 错误详情: {traceback.format_exc()}")
                    else:
                        print(f"   ⚠️  未找到 'Kies' 按钮")
                except Exception as e:
                    print(f"   ⚠️  查找 'Kies' 按钮时出错: {e}")
                    import traceback
                    print(f"   📋 错误详情: {traceback.format_exc()}")
        
        # Step 2: Find the product card container to scope our search
        # This ensures we only click buttons within the current product card, not all products on the page
        product_card = None
        product_card_selectors = [
            "[data-testid='product-card']",
            "[data-testhook='product-card']",
            ".product-card",
            "article[data-testid='product-card']",
            "main article",  # Fallback for product detail page
        ]
        
        for selector in product_card_selectors:
            try:
                cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
                # Prefer the first visible card, or if on product detail page, use main content
                if cards:
                    for card in cards:
                        if card.is_displayed():
                            product_card = card
                            break
                    if product_card:
                        break
            except:
                continue
        
        # Step 3: Try to use quantity input if available (more reliable for multiple quantities)
        if quantity > 1 and product_card:
            try:
                # Look for quantity input within the product card
                quantity_input = product_card.find_element(By.CSS_SELECTOR, 
                    "input[data-testid='product-quantity-input'], input[name='quantity']")
                if quantity_input.is_displayed():
                    # Set quantity directly via input
                    self.driver.execute_script("arguments[0].value = arguments[1];", quantity_input, str(quantity))
                    self.driver.execute_script("""
                        arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                        arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                    """, quantity_input)
                    time.sleep(0.5)
                    
                    # Then click the plus button or submit
                    try:
                        plus_button = product_card.find_element(By.CSS_SELECTOR, 
                            "button[data-testid='product-plus']")
                        if plus_button.is_displayed():
                            self.driver.execute_script("arguments[0].click();", plus_button)
                            time.sleep(1.0)
                            self._close_notification_popup()
                            print(f"   ✅ 使用数量输入框添加 {quantity} 个商品")
                            return True
                    except:
                        pass
            except:
                pass
        
        # Step 4: Find and click the add button (scoped to product card if available)
        # Strategy 1: Find button by data-testid="product-plus" within product card
        add_button = None
        try:
            if product_card:
                # Search within product card only
                add_button = product_card.find_element(By.CSS_SELECTOR, 
                    "button[data-testid='product-plus']")
            else:
                # Fallback: search entire page, but prefer first visible one
                buttons = self.driver.find_elements(By.CSS_SELECTOR, 
                    "button[data-testid='product-plus']")
                for btn in buttons:
                    if btn.is_displayed():
                        add_button = btn
                        break
            
            if add_button:
                # Check if button is enabled
                aria_disabled = add_button.get_attribute("aria-disabled")
                if aria_disabled == "true":
                    print(f"   ⚠️  按钮被禁用 (aria-disabled=true)，等待...")
                    # Wait for button to become enabled
                    try:
                        if product_card:
                            WebDriverWait(self.driver, 5).until(
                                lambda d: product_card.find_element(By.CSS_SELECTOR, 
                                    "button[data-testid='product-plus']").get_attribute("aria-disabled") != "true"
                            )
                            add_button = product_card.find_element(By.CSS_SELECTOR, 
                                "button[data-testid='product-plus']")
                        else:
                            WebDriverWait(self.driver, 5).until(
                                lambda d: d.find_element(By.CSS_SELECTOR, 
                                    "button[data-testid='product-plus']").get_attribute("aria-disabled") != "true"
                            )
                            add_button = self.driver.find_element(By.CSS_SELECTOR, 
                                "button[data-testid='product-plus']")
                    except:
                        pass  # If wait fails, continue with original button
                
                if add_button.is_displayed() and add_button.is_enabled():
                    # Scroll to button
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", add_button)
                    time.sleep(0.3)
                    
                    # Remove any overlays that might block the button
                    try:
                        overlays = self.driver.find_elements(By.CSS_SELECTOR, 
                            ".offcanvas_root__JxF2-, [class*='offcanvas'], [class*='overlay']")
                        for overlay in overlays:
                            if overlay.is_displayed():
                                self.driver.execute_script("arguments[0].style.display = 'none';", overlay)
                    except:
                        pass
                    
                    # Click multiple times if quantity > 1, with wait between clicks
                    clicked_count = 0
                    for qty in range(quantity):
                        try:
                            # Check if button still exists and is visible
                            if not add_button.is_displayed():
                                # Button disappeared, try to find it again
                                if product_card:
                                    try:
                                        add_button = product_card.find_element(By.CSS_SELECTOR, 
                                            "button[data-testid='product-plus']")
                                    except:
                                        break
                                else:
                                    try:
                                        buttons = self.driver.find_elements(By.CSS_SELECTOR, 
                                            "button[data-testid='product-plus']")
                                        for btn in buttons:
                                            if btn.is_displayed():
                                                add_button = btn
                                                break
                                    except:
                                        break
                            
                            # Try clicking
                            try:
                                add_button.click()
                                clicked_count += 1
                            except:
                                try:
                                    self.driver.execute_script("arguments[0].click();", add_button)
                                    clicked_count += 1
                                except:
                                    break
                            
                            # Wait between clicks
                            if qty < quantity - 1:
                                time.sleep(0.5)  # Wait for button to potentially reappear
                                
                        except Exception as e:
                            if qty == 0:
                                print(f"   ⚠️  点击失败: {e}")
                            break
                    
                    if clicked_count > 0:
                        time.sleep(0.1)  # Wait for cart update
                        self._close_notification_popup()
                        if clicked_count == quantity:
                            return True
                        else:
                            print(f"   ⚠️  只成功添加了 {clicked_count}/{quantity} 个")
                            return clicked_count > 0
        except Exception as e:
            pass
        
        # Strategy 2: Find button by SVG use href="#svg_plus" within product card
        try:
            if product_card:
                xpath = ".//button[.//use[@href='#svg_plus']]"
                add_button = product_card.find_element(By.XPATH, xpath)
            else:
                xpath = "//button[.//use[@href='#svg_plus']]"
                buttons = self.driver.find_elements(By.XPATH, xpath)
                add_button = None
                for btn in buttons:
                    if btn.is_displayed():
                        add_button = btn
                        break
            
            if add_button:
                aria_disabled = add_button.get_attribute("aria-disabled")
                if aria_disabled != "true" and add_button.is_displayed() and add_button.is_enabled():
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", add_button)
                    time.sleep(0.1)
                    try:
                        add_button.click()
                    except:
                        self.driver.execute_script("arguments[0].click();", add_button)
                    time.sleep(0.1)
                    self._close_notification_popup()
                    return True
        except:
            pass
        
        # Strategy 3: Fallback to other selectors (scoped to product card)
        add_button_selectors = [
            ".//button[.//svg[contains(@class, 'plus-button_icon__cSPiv')]]",
            ".//button[.//svg[contains(@class, 'svg--svg_plus')]]",
            "button[aria-label*='toevoegen']",
            "button[aria-label*='Product toevoegen']",
            "[data-testhook='add-to-cart-button']",
        ]
        
        for selector in add_button_selectors:
            try:
                if product_card:
                    add_button = product_card.find_element(By.XPATH if selector.startswith(".//") else By.CSS_SELECTOR, selector)
                else:
                    if selector.startswith(".//"):
                        xpath = selector.replace(".//", "//")
                        buttons = self.driver.find_elements(By.XPATH, xpath)
                        add_button = None
                        for btn in buttons:
                            if btn.is_displayed():
                                add_button = btn
                                break
                    else:
                        buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        add_button = None
                        for btn in buttons:
                            if btn.is_displayed():
                                add_button = btn
                                break
                
                if add_button:
                    aria_disabled = add_button.get_attribute("aria-disabled")
                    if aria_disabled != "true" and add_button.is_displayed() and add_button.is_enabled():
                        self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", add_button)
                        time.sleep(0.3)
                        try:
                            add_button.click()
                        except:
                            self.driver.execute_script("arguments[0].click();", add_button)
                        time.sleep(1.0)
                        self._close_notification_popup()
                        return True
            except:
                continue
        
        return False
    
    def add_products(self, products: List[Dict[str, Any]], 
                    progress_callback: Optional[Callable[[str, bool], None]] = None,
                    force_add: bool = False,
                    available_products: Optional[List[Dict[str, Any]]] = None) -> CartResult:
        """
        Batch add products to cart - main interface
        
        Args:
            products: Product list, each product should contain 'title' and optional 'product_url'
            progress_callback: Progress callback function callback(product_title, success)
            force_add: If True, skip the "cart not empty" check and add products anyway
        
        Returns:
            CartResult: Operation result
        """
        if not self.driver:
            self._setup_driver()
        
        # Visit homepage and accept cookies (only once)
        print("🌐 Visiting AH.nl...")
        self.driver.get(self.base_url)
        time.sleep(2)
        
        # Accept cookies only once at the beginning
        self._accept_cookies(silent=False)
        
        # Ensure logged in
        self._ensure_logged_in()
        
        # Mark cookies as checked to avoid checking again
        self._cookies_checked = True
        
        # 先检查购物车总金额，如果为0则跳过购物车内容检查
        cart_total = self.get_cart_total_amount()
        cart_items = []
        cart_not_empty = False
        
        if cart_total > 0.0:
            # 只有购物车不为空时才获取购物车内容
            print("\n🔍 检查购物车内容...")
            cart_items = self._get_cart_items()
            
            # 额外检查：通过价格元素判断购物车是否为空
            try:
                current_url = self.driver.current_url
                if '/mijnlijst' not in current_url:
                    self.view_cart()
                    time.sleep(2)
                
                # 检查是否有价格元素（说明购物车不为空）
                price_elements = self.driver.find_elements(By.CSS_SELECTOR,
                    ".price-Eu_FGd, .priceWrapper-DO7YYj, [class*='price-Eu']")
                has_price = len(price_elements) > 0
                
                if cart_items:
                    print(f"   📦 购物车中已有 {len(cart_items)} 种商品")
                    cart_not_empty = True
                elif has_price:
                    print(f"   📦 购物车不为空（检测到价格信息，但无法提取商品名称）")
                    # 如果检测到价格但没找到商品名称，标记购物车不为空
                    cart_items = ["__cart_not_empty__"]  # 使用特殊标记
                    cart_not_empty = True
                else:
                    print("   📦 购物车为空")
            except Exception as e:
                print(f"   ⚠️ 检查购物车状态时出错: {e}")
                if cart_items:
                    print(f"   📦 购物车中已有 {len(cart_items)} 种商品")
                    cart_not_empty = True
        else:
            print("\n💰 购物车为空（€0.00），跳过购物车内容检查")
            cart_not_empty = False  # 购物车为空，可以添加商品
        
        # 如果购物车不为空且不是强制添加，跳过添加步骤
        if cart_not_empty and not force_add:
            print(f"\n⏭️  购物车中已有商品，跳过添加步骤")
            print(f"   如需添加新商品，请先清空购物车")
            
            result = CartResult(
                success=True,
                added_count=0,
                failed_count=0,
                failed_products=[],
                message="购物车不为空，已跳过添加步骤"
            )
            return result
        
        # Start adding products
        print(f"\n🛒 Starting to add {len(products)} products to cart...")
        print("=" * 50)
        
        added_count = 0
        skipped_count = 0
        failed_products = []
        
        for i, product in enumerate(products, 1):
            title = product.get("title", "Unknown product")
            product_url = product.get("product_url", "")
            # Priority: promotion_quantity > quantity > 1
            quantity = product.get("promotion_quantity") or product.get("quantity", 1)
            
            quantity_text = f" x{quantity}" if quantity > 1 else ""
            print(f"\n[{i}/{len(products)}] {title}{quantity_text}")
            
            # 检查商品是否已经在购物车中
            if self._is_product_in_cart(title, cart_items):
                print(f"   ⏭️  已在购物车中，跳过")
                skipped_count += quantity
                if progress_callback:
                    progress_callback(title, True)  # 标记为成功（因为已经在购物车中）
                continue
            
            # Add product multiple times if quantity > 1
            success_count = 0
            
            # 如果没有 product_url，尝试从所有产品源（bonus + eerder-gekocht）中匹配
            if not product_url:
                matched_product = self._find_product_in_all_sources(title, available_products=available_products)
                if matched_product:
                    product_url = matched_product.get("product_url")
                    matched_title = matched_product.get('title', title)
                    # 判断来源：检查是否在 available_products 中
                    if available_products and any(p.get('title') == matched_product.get('title') for p in available_products):
                        source = 'bonus'
                    else:
                        source = matched_product.get('source', 'eerder-gekocht')
                    
                    if product_url:
                        print(f"   🔍 在 {source} 中找到匹配: {matched_title}")
                        print(f"   ✅ 使用 product_url 添加到购物车: {product_url}")
                        # 更新 product 信息
                        product.update(matched_product)
                    else:
                        matched_url = matched_product.get("product_url", "") or "无"
                        print(f"   ⚠️  在 {source} 中找到产品但无 URL: {matched_title}")
                        print(f"   📋 匹配产品的 URL: {matched_url}")
                        print(f"   🔄 回退到搜索功能...")
                        # 使用搜索功能，如果搜索成功会继续，否则会跳过
                        if not self._find_product_by_search(title):
                            print(f"   ❌ 搜索失败，跳过")
                            failed_products.append(f"{title}{quantity_text} (no product_url, search failed)")
                            if progress_callback:
                                progress_callback(title, False)
                            continue
                else:
                    print(f"   ⚠️  在所有产品源（bonus + eerder-gekocht）中未找到匹配: {title}")
                    print(f"   🔄 尝试使用搜索功能...")
                    # 使用搜索功能
                    if not self._find_product_by_search(title):
                        print(f"   ❌ 搜索失败，跳过")
                        failed_products.append(f"{title}{quantity_text} (not found in JSON, search failed)")
                        if progress_callback:
                            progress_callback(title, False)
                        continue
            
            # 访问商品页面（如果有 URL）或使用搜索（已在上面处理）
            if product_url:
                # 使用 product_url 访问商品页面
                print(f"   🌐 访问商品页面: {product_url}")
                if self._find_product_by_url(product_url):
                    # 一次性添加指定数量（_add_to_cart 内部会处理多次点击或使用数量输入框）
                    success = self._add_to_cart(quantity=quantity)
                    
                    if success:
                        success_count = quantity
                        if quantity > 1:
                            print(f"   ✅ Added {quantity} items to cart")
                        else:
                            print(f"   ✅ Added to cart")
                    else:
                        print(f"   ❌ 添加到购物车失败")
                else:
                    # 如果无法访问商品页面
                    print(f"   ⚠️  无法访问商品页面")
            else:
                # 如果没有 product_url，说明已经通过搜索找到了商品页面，直接添加
                # 一次性添加指定数量
                success = self._add_to_cart(quantity=quantity)
                
                if success:
                    success_count = quantity
                    if quantity > 1:
                        print(f"   ✅ Added {quantity} items to cart")
                    else:
                        print(f"   ✅ Added to cart")
                else:
                    print(f"   ❌ 添加到购物车失败")
            
            if success_count == quantity:
                added_count += quantity
                if quantity == 1:
                    print(f"   ✅ Added to cart")
                if progress_callback:
                    progress_callback(title, True)
            elif success_count > 0:
                # Partially added
                failed_products.append(f"{title} (only {success_count}/{quantity} added)")
                print(f"   ⚠️ Partially added ({success_count}/{quantity})")
                added_count += success_count
                if progress_callback:
                    progress_callback(title, False)
            else:
                failed_products.append(f"{title}{quantity_text}")
                print(f"   ❌ Failed to add")
                if progress_callback:
                    progress_callback(title, False)
            
            # Short delay to avoid too fast operations
            time.sleep(0.3)  # 缩短等待时间
        
        # Summary
        total_processed = added_count + skipped_count
        result = CartResult(
            success=added_count > 0 or skipped_count > 0,
            added_count=added_count,
            failed_count=len(failed_products),
            failed_products=failed_products,
            message=f"Added {added_count} new products, skipped {skipped_count} existing products"
        )
        
        print("\n" + "=" * 50)
        print(f"✅ Complete! {result.message}")
        if skipped_count > 0:
            print(f"   ⏭️  跳过了 {skipped_count} 个已在购物车中的商品")
        if failed_products:
            print(f"\n❌ Failed products ({len(failed_products)} items):")
            for product in failed_products:
                print(f"   - {product}")
        
        return result
    
    def add_from_buckets(self, buckets: Dict[str, List[Dict[str, Any]]],
                        progress_callback: Optional[Callable[[str, bool], None]] = None,
                        available_products: Optional[List[Dict[str, Any]]] = None) -> CartResult:
        """
        Add products from buckets to cart - convenient method
        
        Args:
            buckets: Bucket dictionary, format like {"essentials": [...], "meat": [...]}
            progress_callback: Progress callback function
            available_products: 可用的产品列表（bonus + eerder-gekocht），用于匹配时搜索
            
        Returns:
            CartResult: Operation result
        """
        # Merge all products from buckets
        all_products = []
        for bucket_name, items in buckets.items():
            all_products.extend(items)
        
        print(f"📦 Extracted {len(all_products)} products from {len(buckets)} buckets")
        
        return self.add_products(all_products, progress_callback=progress_callback, available_products=available_products)
    
    def get_cart_total_amount(self) -> float:
        """
        从购物车按钮读取总金额
        
        Returns:
            购物车总金额（欧元），如果无法读取则返回0.0
        """
        try:
            # 确保在主页或任意页面（购物车按钮在导航栏）
            current_url = self.driver.current_url
            if '/mijnlijst' in current_url:
                # 如果在购物车页面，先回到主页
                self.driver.get(self.base_url)
                time.sleep(1)
            
            # 查找购物车按钮
            cart_button_selectors = [
                "[data-testid='navigation-shoppingList']",
                "a[href='/mijnlijst']",
                "a[aria-label*='winkelmand']",
                "a[aria-label*='Totaalbedrag']",
            ]
            
            cart_button = None
            for selector in cart_button_selectors:
                try:
                    cart_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if cart_button:
                        break
                except:
                    continue
            
            if not cart_button:
                return 0.0
            
            # 方法1: 从aria-label中提取金额（最可靠，包含总金额）
            aria_label = cart_button.get_attribute("aria-label") or ""
            if "Totaalbedrag" in aria_label:
                # 提取总金额，格式可能是 "Totaalbedrag winkelmand €21.70"
                # 优先匹配 "Totaalbedrag" 后面的金额
                amount_match = re.search(r'Totaalbedrag[^€]*€?\s*(\d+[.,]\d+)', aria_label)
                if amount_match:
                    amount_str = amount_match.group(1).replace(',', '.')
                    try:
                        amount = float(amount_str)
                        if amount > 0:  # 确保是正数
                            return amount
                    except:
                        pass
            
            # 方法2: 从priceWrapper中提取总金额（排除折扣金额）
            try:
                price_wrapper = cart_button.find_element(By.CSS_SELECTOR, ".priceWrapper-DO7YYj")
                # 明确查找总金额元素，排除折扣金额元素
                price_elem = price_wrapper.find_element(By.CSS_SELECTOR, ".price-Eu_FGd:not(.discountPrice-vnkEJF)")
                price_text = price_elem.text.strip()
                # 提取数字，确保是正数
                amount_match = re.search(r'(\d+[.,]\d+)', price_text)
                if amount_match:
                    amount_str = amount_match.group(1).replace(',', '.')
                    try:
                        amount = float(amount_str)
                        if amount > 0:  # 确保是正数
                            return amount
                    except:
                        pass
            except:
                pass
            
            # 方法3: 从价格元素中提取（排除折扣价格）
            try:
                # 查找所有价格元素，排除折扣价格
                price_elems = cart_button.find_elements(By.CSS_SELECTOR, ".price-Eu_FGd:not(.discountPrice-vnkEJF), [class*='price-Eu']:not([class*='discount'])")
                for price_elem in price_elems:
                    price_text = price_elem.text.strip()
                    # 跳过包含负号的文本
                    if '-' in price_text or price_text.startswith('-'):
                        continue
                    # 提取数字
                    amount_match = re.search(r'(\d+[.,]\d+)', price_text)
                    if amount_match:
                        amount_str = amount_match.group(1).replace(',', '.')
                        try:
                            amount = float(amount_str)
                            if amount > 0:  # 确保是正数
                                return amount
                        except:
                            continue
            except:
                pass
            
            return 0.0
        except Exception as e:
            print(f"   ⚠️ 读取购物车金额时出错: {e}")
            return 0.0
    
    def scrape_cart_content(self) -> List[Dict[str, Any]]:
        """
        抓取购物车中的详细产品信息（排除推荐商品部分）
        
        Returns:
            购物车中产品的详细信息列表，每个产品包含title, price等信息
        """
        cart_products = []
        try:
            # 确保在购物车页面
            current_url = self.driver.current_url
            if '/mijnlijst' not in current_url:
                self.view_cart()
                time.sleep(2)
            
            # 根据实际HTML结构，查找购物车商品列表
            # 购物车商品在 <ul class="lane_items__w6nqQ"> 中
            # 每个商品是 <li class="lane_item__68OyI" data-testhook="myl-lane-product">
            cart_items = []
            
            # 方法1: 使用 data-testhook="myl-lane-product" 查找购物车商品
            try:
                items = self.driver.find_elements(By.CSS_SELECTOR, "[data-testhook='myl-lane-product']")
                if items:
                    cart_items = items
            except:
                pass
            
            # 方法2: 如果方法1失败，查找 lane_items 容器中的商品
            if not cart_items:
                try:
                    # 查找包含"Boodschappen"标题的lane，排除"Suggesties voor jou"
                    lane_headers = self.driver.find_elements(By.CSS_SELECTOR, "h2[data-testhook='product-lane']")
                    for header in lane_headers:
                        header_text = header.text.strip().lower()
                        # 只处理"Boodschappen"部分，排除推荐商品部分
                        if 'boodschappen' in header_text and 'suggesties' not in header_text:
                            # 找到对应的lane容器
                            lane_container = header.find_element(By.XPATH, "./following-sibling::ul[contains(@class, 'lane_items')] | ./parent::div//ul[contains(@class, 'lane_items')]")
                            items = lane_container.find_elements(By.CSS_SELECTOR, "li[data-testhook='myl-lane-product'], li.lane_item__68OyI")
                            if items:
                                cart_items = items
                                break
                except:
                    pass
            
            # 方法3: 如果还是没找到，尝试查找所有 lane_item，但排除推荐商品部分
            if not cart_items:
                try:
                    all_items = self.driver.find_elements(By.CSS_SELECTOR, "li.lane_item__68OyI, li[data-testhook='myl-lane-product']")
                    filtered_items = []
                    for item in all_items:
                        try:
                            # 检查是否在推荐商品section中
                            # 查找最近的包含"Suggesties"或"voor jou"的父元素
                            parent_xpath = "./ancestor::*[contains(@class, 'suggestion') or contains(@class, 'recommendation') or contains(@class, 'recommended') or contains(text(), 'Suggesties') or contains(text(), 'voor jou')]"
                            try:
                                parent = item.find_element(By.XPATH, parent_xpath)
                                # 如果找到推荐商品标识的父元素，跳过
                                continue
                            except:
                                # 如果找不到推荐标识的父元素，说明是购物车商品
                                filtered_items.append(item)
                        except:
                            filtered_items.append(item)
                    
                    if filtered_items:
                        cart_items = filtered_items
                except:
                    pass
            
            # 提取每个产品的详细信息
            for item in cart_items:
                try:
                    # 检查是否在推荐商品section中
                    try:
                        item_text = item.text.lower()
                        if ('suggesties' in item_text or 
                            'suggestions' in item_text or 
                            'voor jou' in item_text or
                            'for you' in item_text):
                            continue
                    except:
                        pass
                    
                    # 检查父元素是否包含推荐商品标识
                    try:
                        parent_xpath = "./ancestor::*[contains(@class, 'suggestion') or contains(@class, 'recommendation') or contains(@class, 'recommended') or contains(text(), 'Suggesties') or contains(text(), 'voor jou')]"
                        parent = item.find_element(By.XPATH, parent_xpath)
                        continue
                    except:
                        pass
                    
                    product = {}
                    
                    # 提取标题 - 根据实际HTML结构
                    title = ""
                    title_selectors = [
                        "[data-testhook='product-title'] span.line-clamp_root__7DevG",
                        "[data-testhook='product-title']",
                        ".product-card-list-view_title__mjL5y",
                        ".title_root__xSlPL",
                        "span[data-testhook='product-title-line-clamp']",
                    ]
                    
                    for selector in title_selectors:
                        try:
                            title_elem = item.find_element(By.CSS_SELECTOR, selector)
                            title = title_elem.text.strip()
                            if title:
                                break
                        except:
                            continue
                    
                    # 如果还是没找到，尝试从整个item中提取
                    if not title:
                        try:
                            text_lines = item.text.strip().split('\n')
                            for line in text_lines:
                                line = line.strip()
                                # 跳过价格、数量等非标题行
                                if (len(line) > 3 and len(line) < 200 and 
                                    not re.match(r'^[€$]?\d+[.,]\d+', line) and
                                    not re.match(r'^\d+\s*(stuks?|g|kg|ml|l|per stuk|per stuk|ca\.)', line.lower()) and
                                    line.lower() not in ['winkelmandje', 'cart', 'totaal', 'total', 'voeg toe', 'toevoegen', '-', '+', '1', '2', '3', '4', '5']):
                                    title = line
                                    break
                        except:
                            pass
                    
                    if not title:
                        continue
                    
                    # 验证标题不应包含推荐商品标识
                    title_lower = title.lower()
                    if ('suggesties' in title_lower or 
                        'suggestions' in title_lower or 
                        'voor jou' in title_lower or
                        'for you' in title_lower):
                        continue
                    
                    product['title'] = title
                    
                    # 提取价格 - 根据实际HTML结构
                    price = ""
                    price_selectors = [
                        "[data-testhook='price-amount']",
                        ".price-amount_root__Sa88q",
                        ".price_list__Yo1Ch",
                        ".price_amount__s-QN4",
                    ]
                    
                    for selector in price_selectors:
                        try:
                            price_elem = item.find_element(By.CSS_SELECTOR, selector)
                            # 价格可能分散在多个span中（整数部分和小数部分）
                            try:
                                # 尝试获取整数部分和小数部分
                                integer_part = price_elem.find_element(By.CSS_SELECTOR, ".price-amount_integer__+e2XO, span[class*='integer']")
                                fractional_part = price_elem.find_element(By.CSS_SELECTOR, ".price-amount_fractional__kjJ7u, span[class*='fractional']")
                                integer = integer_part.text.strip()
                                fractional = fractional_part.text.strip()
                                if integer and fractional:
                                    price = f"€{integer}.{fractional}"
                                    break
                            except:
                                # 如果无法分别获取，尝试获取整个文本
                                price_text = price_elem.text.strip()
                                if price_text and ('€' in price_text or re.match(r'\d+[.,]\d+', price_text)):
                                    price = price_text
                                    break
                        except:
                            continue
                    
                    # 如果还是没找到价格，尝试从整个item中查找
                    if not price:
                        try:
                            # 查找所有包含价格的元素
                            price_elems = item.find_elements(By.CSS_SELECTOR, "[class*='price'], [data-testhook*='price']")
                            for price_elem in price_elems:
                                price_text = price_elem.text.strip()
                                # 检查是否包含价格格式
                                if price_text and ('€' in price_text or re.match(r'\d+[.,]\d+', price_text)):
                                    # 提取价格数字
                                    price_match = re.search(r'(\d+[.,]\d+)', price_text)
                                    if price_match:
                                        price = f"€{price_match.group(1).replace(',', '.')}"
                                        break
                        except:
                            pass
                    
                    # 如果找不到价格，可能是推荐商品，跳过
                    if not price:
                        continue
                    
                    product['price'] = price
                    
                    # 提取数量 - 根据实际HTML结构
                    quantity = 1
                    try:
                        # 查找数量输入框
                        qty_elem = item.find_element(By.CSS_SELECTOR, "input[type='number'][name='quantity'], input[data-testhook='product-quantity-input']")
                        qty_value = qty_elem.get_attribute('value')
                        if qty_value:
                            quantity = int(qty_value)
                    except:
                        # 如果找不到输入框，尝试从按钮文本中提取
                        try:
                            qty_button = item.find_element(By.CSS_SELECTOR, "button[data-testhook='product-quantity-button']")
                            qty_text = qty_button.text.strip()
                            # 按钮文本格式可能是 "- 1 +"
                            qty_match = re.search(r'\d+', qty_text)
                            if qty_match:
                                quantity = int(qty_match.group(0))
                        except:
                            pass
                    
                    product['quantity'] = quantity
                    
                    # 提取产品URL
                    product_url = ""
                    try:
                        link_elem = item.find_element(By.CSS_SELECTOR, "a[href*='/producten/product/']")
                        product_url = link_elem.get_attribute('href')
                        if product_url and not product_url.startswith('http'):
                            product_url = self.base_url + product_url
                    except:
                        pass
                    
                    product['product_url'] = product_url
                    
                    cart_products.append(product)
                except Exception as e:
                    continue
            
            return cart_products
        except Exception as e:
            print(f"⚠️ 抓取购物车内容时出错: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _get_cart_items(self) -> List[str]:
        """
        获取购物车中所有商品的标题列表
        
        Returns:
            购物车中商品标题列表
        """
        cart_items = []
        try:
            # 尝试从购物车页面获取商品列表
            # 先检查是否已经在购物车页面
            current_url = self.driver.current_url
            if '/mijnlijst' not in current_url:
                # 如果不在购物车页面，尝试打开购物车
                self.view_cart()
                time.sleep(0.2)  # 最小等待时间
            
            # 首先检查购物车是否为空 - 通过检查是否有价格元素
            price_elements = self.driver.find_elements(By.CSS_SELECTOR, 
                ".price-Eu_FGd, .priceWrapper-DO7YYj, [class*='price']")
            if not price_elements:
                # 如果没有价格元素，可能购物车为空
                return []
            
            # 查找购物车中的商品标题 - 使用多种选择器
            product_title_selectors = [
                "[data-testhook='cart-item-title']",
                "[data-testhook='product-title']",
                "[data-testhook='cart-product-title']",
                ".cart-item-title",
                "[class*='cart-item'] [class*='title']",
                "[class*='product-title']",
                "[class*='cart-product'] [class*='title']",
                "h2, h3, h4",  # 标题标签
            ]
            
            for selector in product_title_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        for elem in elements:
                            try:
                                title = elem.text.strip()
                                # 过滤掉明显不是商品标题的文本（如"购物车"、"总计"等）
                                if title and len(title) > 3 and len(title) < 200:
                                    # 排除常见的非商品文本
                                    exclude_keywords = ['winkelmandje', 'cart', 'totaal', 'total', 
                                                       'bestellen', 'order', 'afrekenen', 'checkout',
                                                       '€', 'euro', 'korting', 'discount']
                                    if not any(keyword in title.lower() for keyword in exclude_keywords):
                                        cart_items.append(title.lower())
                            except:
                                continue
                        if cart_items:
                            break
                except:
                    continue
            
            # 如果通过标题选择器没找到，尝试从购物车项目容器中提取
            if not cart_items:
                try:
                    # 查找购物车项目容器
                    cart_item_containers = self.driver.find_elements(By.CSS_SELECTOR,
                        "[data-testhook*='cart-item'], [class*='cart-item'], [class*='cart-product']")
                    
                    for container in cart_item_containers:
                        try:
                            # 尝试从容器中找到标题
                            title_elem = container.find_element(By.CSS_SELECTOR,
                                "[class*='title'], h2, h3, h4, [data-testhook*='title']")
                            title = title_elem.text.strip()
                            if title and len(title) > 3:
                                cart_items.append(title.lower())
                        except:
                            # 如果找不到标题元素，尝试从容器文本中提取第一行
                            try:
                                text = container.text.strip().split('\n')[0]
                                if text and len(text) > 3 and len(text) < 200:
                                    cart_items.append(text.lower())
                            except:
                                continue
                except:
                    pass
            
            # 如果还是没找到，但页面中有价格元素，说明购物车不为空
            # 尝试从页面中提取所有可能的商品名称
            if not cart_items and price_elements:
                try:
                    # 查找所有包含文本的元素，排除价格和按钮
                    all_text_elements = self.driver.find_elements(By.CSS_SELECTOR,
                        "p, span, div, a, h1, h2, h3, h4")
                    for elem in all_text_elements[:100]:  # 只检查前100个元素
                        try:
                            text = elem.text.strip()
                            # 检查是否是商品标题（长度合理，不包含价格格式）
                            if (5 < len(text) < 150 and 
                                not re.match(r'^[€$]?\d+[.,]\d+', text) and  # 不是价格
                                not text.lower() in ['winkelmandje', 'cart', 'totaal', 'total']):
                                cart_items.append(text.lower())
                        except:
                            continue
                except:
                    pass
            
            # 去重并返回
            unique_items = list(set(cart_items))
            return unique_items
        except Exception as e:
            print(f"⚠️ 获取购物车内容时出错: {e}")
            return []
    
    def _is_product_in_cart(self, product_title: str, cart_items: List[str] = None) -> bool:
        """
        检查商品是否已经在购物车中
        
        Args:
            product_title: 商品标题
            cart_items: 购物车商品列表（可选，如果不提供会自动获取）
        
        Returns:
            True如果商品已在购物车中，False如果不在
        """
        try:
            if cart_items is None:
                cart_items = self._get_cart_items()
            
            # 如果购物车有特殊标记（检测到价格但无法提取商品名称），保守策略：假设商品可能已存在
            if cart_items and cart_items[0] == "__cart_not_empty__":
                # 这种情况下，我们无法准确判断，但为了安全，可以跳过添加
                # 或者返回False让用户决定
                # 这里我们返回False，让程序尝试添加（如果用户想强制添加）
                return False
            
            # 将商品标题转换为小写进行比较
            title_lower = product_title.lower()
            
            # 检查完全匹配或部分匹配
            for cart_item in cart_items:
                # 完全匹配
                if title_lower == cart_item:
                    return True
                # 部分匹配（商品标题包含在购物车商品中，或购物车商品包含在商品标题中）
                if title_lower in cart_item or cart_item in title_lower:
                    # 进一步检查：确保匹配的部分足够长（避免误匹配）
                    min_length = min(len(title_lower), len(cart_item))
                    if min_length >= 5:  # 至少5个字符才进行匹配
                        # 计算匹配度
                        if len(title_lower) <= len(cart_item):
                            match_ratio = len(title_lower) / len(cart_item) if len(cart_item) > 0 else 0
                        else:
                            match_ratio = len(cart_item) / len(title_lower) if len(title_lower) > 0 else 0
                        
                        if match_ratio >= 0.6:  # 至少60%匹配
                            return True
            
            return False
        except Exception as e:
            print(f"⚠️ 检查商品是否在购物车中时出错: {e}")
            return False
    
    def view_cart(self):
        """View cart"""
        try:
            cart_selectors = [
                "[data-testhook='cart-button']",
                "[data-testid='navigation-shoppingList']",
                "[aria-label*='winkelmand']",
                "a[href*='/mijnlijst']",
                ".cart-button"
            ]
            
            for selector in cart_selectors:
                try:
                    cart_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if cart_button.is_displayed():
                        cart_button.click()
                        time.sleep(2)
                        print("✅ Cart page opened")
                        return True
                except:
                    continue
            
            # If button not found, directly access cart URL
            self.driver.get(f"{self.base_url}/mijnlijst")
            time.sleep(2)
            print("✅ Cart page opened")
            return True
        except Exception as e:
            print(f"❌ Unable to open cart: {e}")
            return False
    
    def close(self):
        """Close browser (optional, default keeps open for viewing)"""
        if self.driver:
            print("\n💡 Browser will remain open, you can view the cart")
            print("   To close, please manually close the browser window")
            print(f"   💾 登录状态和cookies已保存到: {self.session_manager.user_data_dir}")
            # If auto-close needed, uncomment below
            # self.driver.quit()
            # self.driver = None
    
    def clear_session(self):
        """清除会话数据（谨慎使用！会删除所有保存的cookies和登录状态）"""
        self.session_manager.clear_session()
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


def add_to_cart_simple(products: List[Dict[str, Any]], 
                       headless: bool = False) -> CartResult:
    """
    Simple one-click add products to cart
    
    Args:
        products: Product list
        headless: Whether to use headless mode
    
    Returns:
        CartResult: Operation result
    
    Example:
        >>> products = [
        ...     {"title": "AH Halfvolle melk", "product_url": "https://..."},
        ...     {"title": "AH Eieren", "product_url": "https://..."}
        ... ]
        >>> result = add_to_cart_simple(products)
        >>> print(f"Successfully added {result.added_count} products")
    """
    with CartAutomation(headless=headless) as cart:
        return cart.add_products(products)


def add_buckets_to_cart(buckets: Dict[str, List[Dict[str, Any]]],
                        headless: bool = False) -> CartResult:
    """
    One-click add products from buckets to cart
    
    Args:
        buckets: Bucket dictionary
        headless: Whether to use headless mode
    
    Returns:
        CartResult: Operation result
    
    Example:
        >>> buckets = {
        ...     "essentials": [{"title": "Melk", ...}],
        ...     "meat": [{"title": "Kip", ...}]
        ... }
        >>> result = add_buckets_to_cart(buckets)
    """
    with CartAutomation(headless=headless) as cart:
        return cart.add_from_buckets(buckets)

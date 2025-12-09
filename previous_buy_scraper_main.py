"""独立的主程序：专门抓取 eerder-gekocht (previous buy) 产品"""
import os
import sys
import time
import json
from datetime import datetime
from config import Config
from scraper import AHBonusScraper
from session_manager import SessionManager
from selenium.webdriver.common.by import By


def scrape_previous_buy_products():
    """抓取 eerder-gekocht (previous buy) 产品"""
    print("📦 Eerder-gekocht Product Scraper")
    print("=" * 50)
    
    # Load configuration
    config = Config.from_env()
    
    # Initialize components
    session_manager = SessionManager(user_data_dir=config.chrome_user_data_dir)
    scraper = AHBonusScraper(config, session_manager=session_manager)
    
    # Scrape eerder-gekocht products
    print("\n📦 Step 1: Scraping eerder-gekocht products...")
    
    try:
        # Setup driver if needed
        if not scraper.driver:
            scraper._setup_driver_with_session()
        
        # Visit eerder-gekocht page
        eerder_gekocht_url = "https://www.ah.nl/producten/eerder-gekocht"
        print(f"🌐 Visiting: {eerder_gekocht_url}")
        scraper.driver.get(eerder_gekocht_url)
        time.sleep(3)
        
        # Accept cookies
        print("🍪 Looking for cookie consent dialog...")
        try:
            cookie_btn = scraper.driver.find_element(By.XPATH, 
                "//button[@data-testid='accept-cookies']")
            if cookie_btn.is_displayed():
                cookie_btn.click()
                time.sleep(1)
                print("✅ Cookies accepted")
        except:
            print("⚠️ Cookie banner not found - continuing anyway")
        
        # Check login status
        needs_login = False
        login_selectors = [
            "//a[contains(@href, 'inloggen')]",
            "//button[contains(text(), 'Inloggen')]",
            "//a[contains(text(), 'Inloggen')]",
        ]
        
        for selector in login_selectors:
            try:
                login_btn = scraper.driver.find_element(By.XPATH, selector)
                if login_btn.is_displayed():
                    needs_login = True
                    print("🔐 检测到登录按钮，需要登录")
                    break
            except:
                continue
        
        # Wait for page to load (basic check)
        print("⏳ 等待页面内容加载...")
        try:
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            WebDriverWait(scraper.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 
                    "[data-testhook='promotion-card'], [data-testhook='product-card'], [data-testid='product-card']"))
            )
            print("✅ 检测到产品卡片")
        except:
            print("⚠️ 未检测到产品卡片，继续尝试...")
        
        # Wait for user to manually login (if needed) and scroll, then press Enter once
        if config.auto_mode:
            print("🔐 自动模式：跳过登录等待，使用已保存的cookies")
            time.sleep(3)
        else:
            print("\n" + "=" * 70)
            if needs_login:
                print("🔐📜 请手动操作浏览器（登录 + 滚动）：")
                print("=" * 70)
                print("  1. 在浏览器中手动点击登录按钮并完成登录")
                print("  2. 登录完成后，手动滚动页面加载所有产品")
                print("  3. 如果有 'Meer resultaten' 按钮，请手动点击加载更多产品")
                print("  4. 确保所有需要抓取的产品都已加载完成")
                print("  5. 完成后，在此处按 Enter 键开始抓取...")
            else:
                print("📜 请手动操作浏览器（滚动）：")
                print("=" * 70)
                print("  1. 在浏览器中手动滚动页面，加载所有产品")
                print("  2. 如果有 'Meer resultaten' 按钮，请手动点击加载更多产品")
                print("  3. 确保所有需要抓取的产品都已加载完成")
                print("  4. 完成后，在此处按 Enter 键开始抓取...")
            print("=" * 70)
            
            try:
                user_input = input("\n💡 请完成所有操作后按 Enter 键开始抓取: ")
                print("✅ 收到确认，开始抓取产品...")
            except KeyboardInterrupt:
                print("\n⚠️ 用户取消操作")
                return
            
            time.sleep(2)  # 给一点时间让页面稳定
        
        # Extract products
        eerder_elements = []
        product_selectors = [
            "[data-testhook='promotion-card']",
            "[data-testhook='product-card']",
            "[data-testid='product-card']",
            "[class*='product-card']",
        ]
        
        for selector in product_selectors:
            try:
                elements = scraper.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    eerder_elements = elements
                    break
            except:
                continue
        
        print(f"📦 从eerder-gekocht页面找到 {len(eerder_elements)} 个产品")
        
        # Extract product information
        products = []
        eerder_count = 0
        import re
        
        for i, element in enumerate(eerder_elements):
            try:
                # Extract title
                title = ""
                try:
                    title_elem = element.find_element(By.CSS_SELECTOR, 
                        "[data-testhook='promotion-card-title']")
                    title = title_elem.text.strip()
                except:
                    try:
                        title = element.text.strip().split('\n')[0].strip()
                        if len(title) < 2 or len(title) > 200:
                            title = ""
                    except:
                        pass
                
                if not title:
                    continue
                
                # Extract price
                price_info = scraper._extract_price_selenium(element)
                
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
                
                # Extract product URL
                product_url = ""
                try:
                    # Try multiple methods to get product URL
                    link_elems = element.find_elements(By.TAG_NAME, "a")
                    for link_elem in link_elems:
                        href = link_elem.get_attribute("href")
                        if href and "/producten/" in href:
                            product_url = href
                            break
                    
                    if not product_url:
                        product_url = element.get_attribute("href")
                    
                    if product_url and not product_url.startswith("http"):
                        product_url = config.ah_base_url + product_url
                except:
                    pass
                
                # Extract promotion quantity
                promotion_quantity = 1
                try:
                    shield_selectors = [
                        "[data-testid='product-shield'] .shield_text__kNeiW",
                        ".shield_text__kNeiW",
                        "[data-testid='product-shield']",
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
                    
                    if not shield_text:
                        try:
                            shield_text = element.text.strip()
                        except:
                            pass
                    
                    patterns = [
                        r'^(\d+)[eE]\s*halve',
                        r'^(\d+)\s+voor',
                        r'^(\d+)voor',
                        r'^(\d+)\s+voor\s+\d+',
                        r'(\d+)\s+voor',
                        r'^(\d+)x',
                        r'^(\d+)\s*x',
                        r'(\d+)x',
                        r'(\d+)\s*x',
                    ]
                    
                    for pattern in patterns:
                        match = re.search(pattern, shield_text, re.IGNORECASE)
                        if match:
                            promotion_quantity = int(match.group(1))
                            if promotion_quantity > 1:
                                break
                except:
                    pass
                
                product = {
                    "title": title,
                    "price": price_info.get("formatted_price", "Unknown"),
                    "current_price": price_info.get("current_price", ""),
                    "original_price": price_info.get("original_price", ""),
                    "discount": price_info.get("discount_percent", 0),
                    "description": description or title,
                    "image_url": image_url,
                    "product_url": product_url,
                    "promotion_quantity": promotion_quantity,
                    "source": "eerder-gekocht"
                }
                
                products.append(product)
                eerder_count += 1
            except:
                continue
        
        print(f"✅ 从eerder-gekocht页面抓取了 {eerder_count} 个产品")
        
        # Save eerder-gekocht products with user choice
        if eerder_count > 0:
            eerder_file = config.eerder_gekocht_file
            eerder_products = [p for p in products if p.get("source") == "eerder-gekocht"]
            
            # Check if file exists
            if not os.path.exists(eerder_file):
                # File doesn't exist, create new file
                print(f"📝 文件不存在，创建新文件保存...")
                eerder_data = {
                    "timestamp": datetime.now().isoformat(),
                    "products": eerder_products
                }
                with open(eerder_file, 'w', encoding='utf-8') as f:
                    json.dump(eerder_data, f, ensure_ascii=False, indent=2)
                print(f"✅ 完成！已保存 {eerder_count} 个eerder-gekocht产品到新文件")
            else:
                # File exists, ask user for choice
                print(f"\n📋 检测到已存在的文件: {eerder_file}")
                print("请选择保存方式：")
                print("  1. [O]verwrite - 覆盖所有数据（默认）")
                print("  2. [A]ppend - 追加新项目")
                
                if config.auto_mode:
                    # Auto mode: default to overwrite
                    choice = 'o'
                    print("🔧 自动模式：默认选择覆盖")
                else:
                    try:
                        user_input = input("\n💡 请输入选择 [O/A] (默认: O): ").strip().lower()
                        if not user_input:
                            choice = 'o'
                        elif user_input.startswith('a'):
                            choice = 'a'
                        else:
                            choice = 'o'
                    except (KeyboardInterrupt, EOFError):
                        print("\n⚠️ 用户取消操作，默认选择覆盖")
                        choice = 'o'
                
                if choice == 'a':
                    # Append mode: merge existing and new products
                    print("📦 追加模式：合并现有数据和新数据...")
                    try:
                        with open(eerder_file, 'r', encoding='utf-8') as f:
                            existing_data = json.load(f)
                            if isinstance(existing_data, dict) and 'products' in existing_data:
                                existing_products = existing_data['products']
                            elif isinstance(existing_data, list):
                                existing_products = existing_data
                            else:
                                existing_products = []
                    except Exception as e:
                        print(f"⚠️ 加载现有数据失败: {e}，将创建新文件")
                        existing_products = []
                    
                    # Create unique keys for existing products
                    existing_keys = set()
                    for p in existing_products:
                        title = p.get('title', '').lower().strip()
                        url = p.get('product_url', '') or ''
                        key = f"{title}|{url}"
                        existing_keys.add(key)
                    
                    # Find new products
                    new_products = []
                    for p in eerder_products:
                        title = p.get('title', '').lower().strip()
                        url = p.get('product_url', '') or ''
                        key = f"{title}|{url}"
                        if key not in existing_keys:
                            new_products.append(p)
                            existing_keys.add(key)
                    
                    # Merge products
                    all_products = existing_products + new_products
                    
                    if new_products:
                        print(f"📦 发现 {len(new_products)} 个新产品，追加到数据库")
                    else:
                        print(f"ℹ️  没有新产品需要添加")
                    
                    eerder_data = {
                        "timestamp": datetime.now().isoformat(),
                        "products": all_products
                    }
                    with open(eerder_file, 'w', encoding='utf-8') as f:
                        json.dump(eerder_data, f, ensure_ascii=False, indent=2)
                    print(f"✅ 完成！已追加保存 (总计 {len(all_products)} 个产品，本次新增 {len(new_products)} 个)")
                else:
                    # Overwrite mode: replace all data
                    print("🔄 覆盖模式：替换所有数据...")
                    eerder_data = {
                        "timestamp": datetime.now().isoformat(),
                        "products": eerder_products
                    }
                    with open(eerder_file, 'w', encoding='utf-8') as f:
                        json.dump(eerder_data, f, ensure_ascii=False, indent=2)
                    print(f"✅ 完成！已覆盖保存 {eerder_count} 个eerder-gekocht产品")
        else:
            print("⚠️ 未抓取到任何产品")
        
    except Exception as e:
        print(f"❌ 抓取失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    scrape_previous_buy_products()


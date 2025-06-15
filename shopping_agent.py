import asyncio
import json
import time
import os
import random
from typing import List, Dict, Any, Optional
import pandas as pd
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import pyautogui

from llama_index.core import Document
from llama_index.core.agent import AgentRunner
from llama_index.core.tools import FunctionTool
from llama_index.llms.ollama import Ollama
from llama_index.llms.openai import OpenAI
from llama_index.llms.anthropic import Anthropic
from llama_index.core.agent import ReActAgent
from llama_index.core import Settings
from config import AgentConfig


class AHShoppingAgent:
    def __init__(self, config: AgentConfig = None):
        """Initialize the shopping agent with configuration."""
        self.config = config or AgentConfig()
        self.setup_llm()
        self.products_data = []
        self.selected_products = []
        self.driver = None
        
    def setup_llm(self):
        """Setup the LLM based on configuration."""
        if self.config.llm_provider == "ollama":
            self.llm = Ollama(model=self.config.model_name, request_timeout=120.0)
        elif self.config.llm_provider == "openai":
            if self.config.openai_api_key:
                import os
                os.environ["OPENAI_API_KEY"] = self.config.openai_api_key
            self.llm = OpenAI(model=self.config.model_name)
        elif self.config.llm_provider == "anthropic":
            if self.config.anthropic_api_key:
                import os
                os.environ["ANTHROPIC_API_KEY"] = self.config.anthropic_api_key
            self.llm = Anthropic(model=self.config.model_name)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.config.llm_provider}")
        
        Settings.llm = self.llm
        
    def categorize_product(self, product_text: str) -> str:
        """
        Categorize a product based on its title and description text.
        
        Args:
            product_text: Combined title and description text (should be lowercase)
            
        Returns:
            Category string: 'meat', 'vegetables', 'fruit', or 'other'
        """
        # Define keywords for each category
        meat_keywords = [
            'vlees', 'beef', 'rundvlees', 'varkensvlees', 'kip', 'chicken', 'kalkoen', 'turkey',
            'lam', 'lamb', 'vis', 'fish', 'zalm', 'salmon', 'tonijn', 'tuna', 'kabeljauw',
            'gehakt', 'worst', 'sausage', 'spek', 'bacon', 'ham', 'shoarma', 'kebab',
            'biefstuk', 'steak', 'schnitzel', 'kotelet', 'vleesproduct', 'meat', 'poultry',
            'bapao', 'rundvlees', 'kippenvlees', 'hamburger', 'kipfilet'
        ]
        
        vegetable_keywords = [
            'groente', 'vegetables', 'tomaat', 'tomato', 'komkommer', 'cucumber', 'paprika',
            'pepper', 'ui', 'onion', 'wortel', 'carrot', 'sla', 'lettuce', 'spinazie',
            'spinach', 'broccoli', 'bloemkool', 'cauliflower', 'courgette', 'zucchini',
            'aubergine', 'eggplant', 'champignon', 'mushroom', 'prei', 'leek', 'selderij',
            'celery', 'radijs', 'radish', 'biet', 'beetroot', 'kool', 'cabbage', 'andijvie',
            'chicory', 'rucola', 'arugula', 'knoflook', 'garlic', 'gember', 'ginger',
            'peterselie', 'parsley', 'basilicum', 'basil', 'kruiden', 'herbs', 'salade'
        ]
        
        fruit_keywords = [
            'fruit', 'appel', 'apple', 'peer', 'pear', 'banaan', 'banana', 'sinaasappel',
            'orange', 'citroen', 'lemon', 'limoen', 'lime', 'aardbei', 'strawberry',
            'frambozen', 'raspberry', 'blauwe bes', 'blueberry', 'druif', 'grape',
            'ananas', 'pineapple', 'mango', 'kiwi', 'perzik', 'peach', 'abrikoos',
            'apricot', 'pruim', 'plum', 'kers', 'cherry', 'meloen', 'melon', 'watermeloen',
            'watermelon', 'avocado', 'kokos', 'coconut', 'passievrucht', 'passion fruit',
            'grapefruit', 'mandarin', 'mandarijn', 'vijg', 'fig', 'dadel', 'date'
        ]
        
        # Check each category
        for keyword in meat_keywords:
            if keyword in product_text:
                return 'meat'
        
        for keyword in vegetable_keywords:
            if keyword in product_text:
                return 'vegetables'
        
        for keyword in fruit_keywords:
            if keyword in product_text:
                return 'fruit'
        
        # Default to other if no category matches
        return 'other'

    def scrape_ah_bonus_products(self, interactive_mode: bool = True) -> List[Dict[str, Any]]:
        """
        Scrape AH bonus products from the website.
        Returns a list of product dictionaries.
        
        Args:
            interactive_mode: If True, keeps browser open for debugging and manual interaction
        """
        print("🔍 Scraping AH bonus products...")
        
        # Setup Chrome driver with profile support
        driver = self._setup_chrome_driver(interactive_mode=interactive_mode, for_automation=False)
        
        try:
            # Navigate to AH bonus page
            print(f"🌐 Navigating to: {self.config.ah_bonus_url}")
            driver.get(self.config.ah_bonus_url)
            time.sleep(self.config.automation_delay)
            
            # Accept cookies if present
            try:
                cookie_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Accepteren') or contains(text(), 'Accept') or contains(text(), 'Akkoord')]"))
                )
                cookie_button.click()
                print("✅ Accepted cookies")
                time.sleep(1)
            except:
                print("ℹ️ No cookie banner found or already accepted")
                pass
            
            if interactive_mode:
                print("\n🔍 INTERACTIVE MODE ACTIVATED")
                print("📱 Browser window is open - you can:")
                print("   1. Navigate manually to the products page")
                print("   2. Check what selectors are available")
                print("   3. Press ENTER when ready to continue scraping")
                print("   4. Type 'manual' to add products manually")
                print("   5. Type 'quit' to exit")
                
                user_input = input("\nPress ENTER to continue with auto-scraping, or type command: ").strip().lower()
                
                if user_input == 'quit':
                    return []
                elif user_input == 'manual':
                    return self._manual_product_entry(driver)
            
            # Wait for page to load and scroll to load more products
            print("⏳ Waiting for page to load...")
            time.sleep(3)
            
            # Improved scrolling to load ALL products
            print("📜 Scrolling to load ALL products...")
            last_product_count = 0
            scroll_attempts = 0
            max_scroll_attempts = 50  # Prevent infinite scrolling
            
            while scroll_attempts < max_scroll_attempts:
                # Scroll to bottom
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                
                # Check current product count
                current_elements = driver.find_elements(By.CSS_SELECTOR, "[data-testhook='promotion-card']")
                current_count = len(current_elements)
                
                print(f"   Scroll {scroll_attempts + 1}: Found {current_count} products")
                
                # If no new products loaded, try a few more times then break
                if current_count == last_product_count:
                    # Try clicking "Load More" button if it exists
                    try:
                        load_more_selectors = [
                            "[data-testhook='load-more']",
                            "button[aria-label*='meer']",
                            "button:contains('Meer laden')",
                            "button:contains('Load more')",
                            ".load-more-button"
                        ]
                        
                        load_more_clicked = False
                        for selector in load_more_selectors:
                            try:
                                if ":contains(" in selector:
                                    load_more_btn = driver.find_element(By.XPATH, f"//button[contains(text(), 'Meer laden') or contains(text(), 'Load more')]")
                                else:
                                    load_more_btn = driver.find_element(By.CSS_SELECTOR, selector)
                                
                                if load_more_btn.is_displayed() and load_more_btn.is_enabled():
                                    driver.execute_script("arguments[0].scrollIntoView();", load_more_btn)
                                    time.sleep(1)
                                    load_more_btn.click()
                                    print(f"   ✅ Clicked 'Load More' button")
                                    time.sleep(3)
                                    load_more_clicked = True
                                    break
                            except:
                                continue
                        
                        if load_more_clicked:
                            continue
                    except:
                        pass
                    
                    # If still no new products after trying load more, we've likely reached the end
                    if current_count == last_product_count:
                        print(f"   ✅ No more products to load. Final count: {current_count}")
                        break
                
                last_product_count = current_count
                scroll_attempts += 1
                
                # Add some variety to scrolling pattern
                if scroll_attempts % 3 == 0:
                    driver.execute_script("window.scrollTo(0, 0);")
                    time.sleep(1)
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)
            
            print(f"📊 Completed scrolling after {scroll_attempts} attempts")
            
            # Get page source for debugging
            page_source = driver.page_source
            print(f"📄 Page source length: {len(page_source)} characters")
            
            # Use the correct selector for AH promotion cards
            product_selector = "[data-testhook='promotion-card']"
            print(f"🔍 Looking for products with selector: {product_selector}")
            
            product_elements = driver.find_elements(By.CSS_SELECTOR, product_selector)
            print(f"📦 Found {len(product_elements)} promotion card elements")
            
            # Fallback selectors if the main one doesn't work
            if len(product_elements) == 0:
                fallback_selectors = [
                    ".promotion-card_root__tQA3z",
                    "[class*='promotion-card']",
                    "a[href*='/bonus/']",
                    "[data-testid='promotion-card']",
                    ".card"
                ]
                
                print("🔍 Trying fallback selectors...")
                for selector in fallback_selectors:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    print(f"   Selector '{selector}': found {len(elements)} elements")
                    if elements and len(elements) > len(product_elements):
                        product_elements = elements
                        print(f"   ✅ Using fallback selector '{selector}' with {len(elements)} elements")
                        break
            
            if len(product_elements) == 0 and interactive_mode:
                print("\n❌ No products found with automatic selectors!")
                print("🔧 DEBUGGING MODE:")
                print("   - Check the browser window")
                print("   - Look at the page structure")
                print("   - You can manually inspect elements")
                
                debug_choice = input("\nType 'manual' to add products manually, or ENTER to continue: ").strip().lower()
                if debug_choice == 'manual':
                    return self._manual_product_entry(driver)
            
            products = []
            for i, element in enumerate(product_elements[:self.config.max_products_to_scrape]):
                try:
                    # Show progress every 10 products instead of every product
                    if (i + 1) % 10 == 0 or i == 0:
                        print(f"🔍 Processing products... {i+1}/{min(len(product_elements), self.config.max_products_to_scrape)}")
                    
                    # Extract product title using the correct selector
                    title = ""
                    try:
                        title_element = element.find_element(By.CSS_SELECTOR, "[data-testhook='promotion-card-title']")
                        title = title_element.text.strip()
                    except:
                        # Fallback title selectors
                        title_selectors = [
                            ".promotion-card-title_root__YObeO",
                            "[class*='promotion-card-title']",
                            "h1", "h2", "h3", "h4", "h5",
                            ".line-clamp_root__7DevG",
                            "span"
                        ]
                        for selector in title_selectors:
                            try:
                                title_elem = element.find_element(By.CSS_SELECTOR, selector)
                                title = title_elem.text.strip()
                                if title:
                                    break
                            except:
                                continue
                    
                    if not title:
                        continue
                    
                    # Extract description
                    description = ""
                    try:
                        desc_elements = element.find_elements(By.CSS_SELECTOR, "[data-testhook='card-description']")
                        if desc_elements:
                            descriptions = [elem.text.strip() for elem in desc_elements if elem.text.strip()]
                            description = " | ".join(descriptions)
                    except:
                        pass
                    
                    # Extract price using enhanced logic
                    price_info = {
                        "current_price": "",
                        "original_price": "",
                        "formatted_price": "",
                        "discount_label": "",
                        "promotion_type": ""
                    }
                    
                    try:
                        price_element = element.find_element(By.CSS_SELECTOR, "[data-testhook='price']")
                        
                        # Try to get the current price from data attributes
                        current_price = price_element.get_attribute("data-testpricenow")
                        original_price = price_element.get_attribute("data-testpricewas")
                        
                        if current_price:
                            price_info["current_price"] = f"€{current_price}"
                        if original_price:
                            price_info["original_price"] = f"€{original_price}"
                            
                        # Calculate discount percentage if both prices available
                        if current_price and original_price:
                            try:
                                current_float = float(current_price)
                                original_float = float(original_price)
                                discount_percent = round(((original_float - current_float) / original_float) * 100)
                                price_info["formatted_price"] = f"€{current_price} (was €{original_price}, save {discount_percent}%)"
                            except:
                                price_info["formatted_price"] = f"€{current_price} (was €{original_price})"
                        elif current_price:
                            price_info["formatted_price"] = f"€{current_price}"
                        else:
                            # Fallback to text extraction
                            price_text = price_element.text.strip()
                            if price_text:
                                price_info["formatted_price"] = price_text
                    except:
                        # Fallback price selectors
                        price_selectors = [
                            ".promotion-price_root__UAFIC",
                            "[class*='price']",
                            "[class*='Price']"
                        ]
                        for selector in price_selectors:
                            try:
                                price_elem = element.find_element(By.CSS_SELECTOR, selector)
                                price_text = price_elem.text.strip()
                                if price_text:
                                    price_info["formatted_price"] = price_text
                                    break
                            except:
                                continue
                    
                    # Extract promotion/discount labels
                    try:
                        promotion_labels = element.find_elements(By.CSS_SELECTOR, "[data-testhook='promotion-labels'], .promotion-labels_root__T-KNC")
                        if promotion_labels:
                            for label_container in promotion_labels:
                                label_text = label_container.text.strip()
                                if label_text:
                                    if "gratis" in label_text.lower():
                                        price_info["promotion_type"] = "Buy X Get Y Free"
                                    elif "%" in label_text:
                                        price_info["promotion_type"] = "Percentage Discount"
                                    elif "korting" in label_text.lower():
                                        price_info["promotion_type"] = "Discount"
                                    else:
                                        price_info["promotion_type"] = "Special Offer"
                                    price_info["discount_label"] = label_text
                                    break
                    except:
                        pass
                    
                    # Final price for display - use formatted price or fallback
                    final_price = price_info["formatted_price"] or "Unknown"
                    
                    # Extract image URL
                    image_url = ""
                    try:
                        img_elem = element.find_element(By.TAG_NAME, "img")
                        image_url = (img_elem.get_attribute("src") or 
                                   img_elem.get_attribute("data-src") or 
                                   img_elem.get_attribute("data-srcset"))
                        # Clean up srcset if needed
                        if image_url and " " in image_url:
                            image_url = image_url.split(" ")[0]
                    except:
                        pass
                    
                    # Get product URL from the link
                    product_url = ""
                    try:
                        product_url = element.get_attribute("href")
                        if product_url and not product_url.startswith("http"):
                            product_url = self.config.ah_base_url + product_url
                    except:
                        pass
                    
                    # Categorize product based on title and description
                    full_text = f"{title} {description}".lower()
                    category = self.categorize_product(full_text)
                    
                    product = {
                        "title": title,
                        "price": final_price,
                        "current_price": price_info["current_price"],
                        "original_price": price_info["original_price"],
                        "discount_label": price_info["discount_label"],
                        "promotion_type": price_info["promotion_type"],
                        "category": category,
                        "image_url": image_url,
                        "product_url": product_url,
                        "description": description or title
                    }
                    
                    products.append(product)
                    
                except Exception as e:
                    # Only log errors if in debug mode
                    continue
            
            self.products_data = products
            print(f"\n✅ Successfully scraped {len(products)} products")
            
            # Print category distribution
            categories = {}
            for product in products:
                cat = product["category"]
                categories[cat] = categories.get(cat, 0) + 1
            print(f"📊 Product distribution: {categories}")
            
            # Print first few products for verification
            if products:
                print("\n📋 Sample products found:")
                for i, product in enumerate(products[:3]):
                    print(f"   {i+1}. {product['title']} - {product['price']} ({product['category']})")
                    if product['description'] != product['title']:
                        print(f"      Description: {product['description']}")
            
            if interactive_mode:
                print("\n🎉 Scraping completed!")
                print("📱 Browser window will remain open for your review")
                print("💡 You can manually navigate and inspect the page")
                input("\nPress ENTER to continue to the next step...")
                # Don't close the driver in interactive mode
                self.driver = driver
            else:
                driver.quit()
            
            return products
            
        except Exception as e:
            print(f"❌ Error scraping products: {e}")
            if interactive_mode:
                print("🔧 Browser window remains open for debugging")
                input("Press ENTER to continue...")
                self.driver = driver
            else:
                driver.quit()
            return []
    
    def _manual_product_entry(self, driver) -> List[Dict[str, Any]]:
        """Allow user to manually enter products when scraping fails."""
        print("\n📝 MANUAL PRODUCT ENTRY MODE")
        print("Enter products manually (press ENTER with empty title to finish)")
        
        products = []
        while True:
            print(f"\n--- Product {len(products) + 1} ---")
            title = input("Product title (or ENTER to finish): ").strip()
            if not title:
                break
                
            price = input("Price (optional): ").strip() or "Unknown"
            
            print("Category options: meat, vegetables, fruit, other")
            category = input("Category: ").strip().lower()
            if category not in ["meat", "vegetables", "fruit", "other"]:
                category = "other"
            
            product_url = input("Product URL (optional): ").strip()
            
            product = {
                "title": title,
                "price": price,
                "image_url": "",
                "product_url": product_url,
                "description": title
            }
            
            products.append(product)
            print(f"✅ Added: {title} ({category})")
        
        self.products_data = products
        print(f"\n✅ Manually entered {len(products)} products")
        
        # Keep driver open
        self.driver = driver
        return products

    def create_product_selection_tool(self):
        """Create a tool for LLM to select products."""
        def select_products_from_list(
            selected_product_titles: List[str]
        ) -> str:
            """
            Select products by their titles from the available product list.
            
            Args:
                selected_product_titles: List of product titles to select
            
            Returns:
                JSON string of selected products
            """
            if not self.products_data:
                return json.dumps({"error": "No products available. Please scrape products first."})
            
            # Find products by title
            selected = []
            not_found = []
            
            for title in selected_product_titles:
                found = False
                for product in self.products_data:
                    if title.lower() in product["title"].lower() or product["title"].lower() in title.lower():
                        selected.append(product)
                        found = True
                        break
                
                if not found:
                    not_found.append(title)
            
            self.selected_products = selected
            
            print(f"Selected {len(selected)} products:")
            for product in selected:
                print(f"  - {product['title']} - {product['price']} ({product['category']})")
            
            if not_found:
                print(f"Not found: {', '.join(not_found)}")
            
            result = {
                "selected_count": len(selected),
                "products": selected,
                "not_found": not_found
            }
            
            return json.dumps(result, indent=2)
        
        return FunctionTool.from_defaults(fn=select_products_from_list)
    
    def create_cart_automation_tool(self):
        """Create a tool for automating cart additions."""
        def add_products_to_cart() -> str:
            """
            Automate adding selected products to the shopping cart.
            Includes interactive login waiting and final cart validation.
            Browser will remain open to show the final cart state.
            
            Returns:
                Status message about the automation process
            """
            if not self.selected_products:
                return "No products selected. Please select products first."
            
            try:
                print("🤖 Starting cart automation...")
                
                # Setup Chrome driver for cart automation (always visible for interaction)
                chrome_options = Options()
                # Never use headless mode for cart automation to allow user interaction
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument("--disable-blink-features=AutomationControlled")
                chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                chrome_options.add_experimental_option('useAutomationExtension', False)
                
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
                self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                self.driver.maximize_window()
                
                # Navigate to AH website
                print("🌐 Navigating to AH website...")
                self.driver.get(self.config.ah_base_url)
                time.sleep(self.config.automation_delay)
                
                # Accept cookies if present
                try:
                    cookie_button = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Accepteren') or contains(text(), 'Accept')]"))
                    )
                    cookie_button.click()
                    print("✅ Accepted cookies")
                    time.sleep(1)
                except:
                    print("ℹ️ No cookie banner found or already accepted")
                    pass
                
                added_count = 0
                failed_products = []
                login_prompted = False
                
                for i, product in enumerate(self.selected_products, 1):
                    try:
                        print(f"🛒 Adding product {i}/{len(self.selected_products)}: {product['title']}")
                        
                        # Check if we need to login (only on first product addition attempt)
                        if not login_prompted and self._needs_login():
                            print("\n🔐 LOGIN REQUIRED")
                            print("📱 Please log in to your AH account in the browser window")
                            print("💡 Steps to follow:")
                            print("   1. Click on 'Inloggen' or 'Account' in the top right")
                            print("   2. Enter your email and password")
                            print("   3. Complete the login process")
                            print("   4. Make sure you're logged in (check for your name/account icon)")
                            print("   5. Press ENTER here when you're ready to continue")
                            
                            input("\n⏳ Press ENTER after you've successfully logged in...")
                            login_prompted = True
                            print("✅ Proceeding with cart automation...")
                        
                        # Navigate to product page if URL available
                        if product.get("product_url"):
                            modified_url = product.get("product_url").replace("/groep/","?id=")
                            self.driver.get(modified_url)
                            time.sleep(self.config.automation_delay)
                            
                            # Try to add to cart
                            if self._add_product_to_cart(product):
                                added_count += 1
                                print(f"✅ Successfully added: {product['title']}")
                            else:
                                failed_products.append(product['title'])
                                print(f"❌ Failed to add: {product['title']}")
                        else:
                            # Try to search for the product
                            print(f"🔍 No direct URL, searching for: {product['title']}")
                            if self._search_and_add_product(product):
                                added_count += 1
                                print(f"✅ Successfully found and added: {product['title']}")
                            else:
                                failed_products.append(product['title'])
                                print(f"❌ Failed to find/add: {product['title']}")
                        
                    except Exception as e:
                        print(f"❌ Error adding {product['title']}: {e}")
                        failed_products.append(product['title'])
                        continue
                
                # Add specific required items: 2L half volle melk and 10 eggs
                print("\n🥛 Adding required items: 2L half volle melk and 10 eggs...")
                required_items_status = self._add_required_items()
                
                # Final cart validation with user interaction
                print("\n🔍 Performing final cart validation...")
                cart_validation_result = self._validate_cart_interactive()
                
                # Show summary
                result_message = f"Cart automation completed!\n"
                result_message += f"✅ Successfully added: {added_count}/{len(self.selected_products)} selected products\n"
                if failed_products:
                    result_message += f"❌ Failed to add: {', '.join(failed_products)}\n"
                result_message += f"\n🥛 Required Items: {required_items_status}\n"
                result_message += f"\n🛒 Cart Validation: {cart_validation_result}"
                
                # Final interactive review
                print("\n" + "="*60)
                print("🎉 CART AUTOMATION COMPLETED!")
                print("="*60)
                print(result_message)
                print("\n📱 The browser window will remain open for your review.")
                print("💡 You can now:")
                print("   - Review your cart contents")
                print("   - Make any manual adjustments")
                print("   - Proceed to checkout when ready")
                print("   - Close the browser when finished")
                
                print("\n⏳ Press ENTER when you're done reviewing your cart...")
                input()
                
                # Don't quit the driver - let user close it manually
                print("✅ Cart automation session completed. Browser remains open for your use.")
                return result_message
                
            except Exception as e:
                error_msg = f"Error during cart automation: {e}"
                print(f"❌ {error_msg}")
                if self.driver:
                    print("🔧 Browser window remains open for debugging")
                return error_msg
        
        return FunctionTool.from_defaults(fn=add_products_to_cart)
    
    def run_shopping_workflow(self, 
                             user_requirements: str = None,
                             interactive_mode: bool = True) -> str:
        """
        Run the complete shopping workflow with LLM agent.
        
        Args:
            user_requirements: User's shopping requirements and preferences
            interactive_mode: If True, keeps browser open for debugging and manual interaction
        """
        try:
            print("🤖 Starting AH Shopping Agent Workflow")
            print("=" * 50)
            
            # Step 1: Scrape products
            print("📊 Step 1: Scraping AH bonus products...")
            products = self.scrape_ah_bonus_products(interactive_mode=interactive_mode)
            
            if not products:
                return "❌ No products found. Cannot proceed with selection."
            
            print(f"✅ Found {len(products)} products to choose from")
            
            # Step 2: Use LLM agent to select products
            print("\n🧠 Step 2: Using LLM to select products based on requirements...")
            
            # Create tools for the agent
            product_selection_tool = self.create_product_selection_tool()
            cart_automation_tool = self.create_cart_automation_tool()
            
            # Create agent
            agent = ReActAgent.from_tools(
                [product_selection_tool, cart_automation_tool], 
                llm=self.llm, 
                verbose=True
            )
            
            # Prepare the full product list for the LLM
            products_info = "\n".join([
                f"- {product['title']} | {product['price']} | Category: {product['category']} | Description: {product['description']}"
                for product in products
            ])
            
            # Default requirements if none provided
            if not user_requirements:
                user_requirements = """
                Please select healthy and diverse products for a weekly grocery shopping.
                Focus on:
                - 3 types of meat
                - 5 types of vegetables
                - 3 types of fruit
                - Fresh ingredients for balanced meals
                - A mix of proteins, vegetables, and fruits
                - Good value for money (considering the discounts)
                - Products that work well together for meal planning
                
                After selecting products, add them to the cart using the automation tool.
                """
            
            # Create comprehensive prompt for the LLM
            llm_prompt = f"""
            You are a helpful shopping assistant. Here are the available AH bonus products:

            {products_info}

            User Requirements:
            {user_requirements}

            Please:
            1. Review all available products carefully
            2. Select appropriate products based on the user's requirements
            3. Use the select_products_from_list tool with the exact product titles
            4. After selection, use the add_products_to_cart tool to automate adding them to the cart

            Remember to:
            - Consider nutritional balance and variety
            - Look for good value (discounted items)
            - Select products that complement each other
            - Use the exact product titles as they appear in the list
            """
            
            print(f"\n📝 Sending {len(products)} products to LLM for selection...")
            print(f"💡 User requirements: {user_requirements[:100]}{'...' if len(user_requirements) > 100 else ''}")
            
            # Execute the agent
            response = agent.chat(llm_prompt)
            
            print("\n🎉 Shopping workflow completed!")
            print("=" * 50)
            print(f"🤖 Agent response: {response}")
            
            return str(response)
            
        except Exception as e:
            error_msg = f"Error in shopping workflow: {e}"
            print(f"❌ {error_msg}")
            return error_msg
    
    def _add_product_to_cart(self, product) -> bool:
        """Add a single product to the cart. For bonus products, handle groups and select random product."""
        try:
            self.driver.get(product["product_url"])
            time.sleep(self.config.automation_delay)
            
            # Check if this is a bonus product group page
            if self._is_bonus_product_group():
                print(f"🎁 Detected bonus product group for: {product['title']}")
                return self._handle_bonus_product_group(product)
            else:
                # Regular product - look for standard add to cart button
                return self._add_regular_product_to_cart(product)
            
        except Exception as e:
            print(f"❌ Error adding {product['title']}: {e}")
            return False
    
    def _is_bonus_product_group(self) -> bool:
        """Check if the current page is a bonus product group with multiple products to choose from."""
        try:
            # Look for indicators that this is a bonus group page
            group_indicators = [
                "[data-testhook='bonus-product-group']",
                ".bonus-product-group",
                "[class*='bonus-group']",
                "[data-testhook='promotion-products']",
                ".promotion-products"
            ]
            
            for selector in group_indicators:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    return True
            
            # Alternative check: look for multiple product cards on the page
            product_cards = self.driver.find_elements(By.CSS_SELECTOR, "[data-testhook='product-card'], .product-card")
            return len(product_cards) > 1
            
        except:
            return False
    
    def _handle_bonus_product_group(self, product) -> bool:
        """Handle bonus product groups by selecting a random product and adding it to cart."""
        try:
            print(f"🎯 Selecting random product from bonus group: {product['title']}")
            
            # Find all products in the group
            product_selectors = [
                "[data-testhook='product-card']",
                ".product-card",
                "[class*='product-card']",
                "[data-testhook='promotion-product']"
            ]
            
            available_products = []
            for selector in product_selectors:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    available_products = elements
                    break
            
            if not available_products:
                print(f"❌ No products found in bonus group for: {product['title']}")
                return False
            
            print(f"🔍 Found {len(available_products)} products in bonus group")
            
            # Select a random product from the group
            selected_product = random.choice(available_products)
            
            # Get product info for logging
            try:
                product_title = selected_product.find_element(By.CSS_SELECTOR, "h1, h2, h3, h4, h5, .product-title, [data-testhook='product-title']").text.strip()
                print(f"🎲 Randomly selected: {product_title}")
            except:
                print(f"🎲 Randomly selected product from group")
            
            # Look for the specific SVG plus button in the selected product
            return self._add_to_cart_with_svg_button(selected_product)
            
        except Exception as e:
            print(f"❌ Error handling bonus product group: {e}")
            return False
    
    def _add_to_cart_with_svg_button(self, product_element) -> bool:
        """Add product to cart using the specific SVG plus button."""
        try:
            # Look for the specific SVG plus button you mentioned
            svg_button_selectors = [
                # Direct SVG selector
                "svg.plus-button_icon__cSPiv",
                "svg[class*='plus-button']",
                "svg[width='30'][height='30']",
                # Button containing the SVG
                "button svg.plus-button_icon__cSPiv",
                "button svg[class*='plus-button']",
                # Button with plus icon
                "button[aria-label*='toevoegen']",
                "button[title*='toevoegen']",
                # Parent button of the SVG
                "button:has(svg.plus-button_icon__cSPiv)",
                "button:has(svg[class*='plus-button'])"
            ]
            
            add_button = None
            
            # Try to find the button within the product element first
            for selector in svg_button_selectors:
                try:
                    if ":has(" in selector:
                        # For CSS :has() selector, use XPath instead
                        xpath = ".//button[.//svg[contains(@class, 'plus-button')]]"
                        add_button = product_element.find_element(By.XPATH, xpath)
                    else:
                        add_button = product_element.find_element(By.CSS_SELECTOR, selector)
                    
                    if add_button and add_button.is_displayed() and add_button.is_enabled():
                        break
                except:
                    continue
            
            # If not found in product element, search in the whole page
            if not add_button:
                print("🔍 Searching for plus button in entire page...")
                for selector in svg_button_selectors:
                    try:
                        if ":has(" in selector:
                            # Use XPath for better compatibility
                            xpath = "//button[.//svg[contains(@class, 'plus-button')]]"
                            add_button = self.driver.find_element(By.XPATH, xpath)
                        else:
                            add_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                        
                        if add_button and add_button.is_displayed() and add_button.is_enabled():
                            break
                    except:
                        continue
            
            # Alternative: look for SVG with use href="#svg_plus"
            if not add_button:
                try:
                    svg_plus = self.driver.find_element(By.CSS_SELECTOR, "svg use[href='#svg_plus']")
                    # Get the parent button
                    add_button = svg_plus.find_element(By.XPATH, "./ancestor::button")
                except:
                    pass
            
            if not add_button:
                print("❌ Could not find the specific SVG plus button")
                return False
            
            # Scroll to button and click
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", add_button)
            time.sleep(0.5)
            
            # Try clicking the button
            try:
                add_button.click()
                print("✅ Successfully clicked SVG plus button")
            except:
                # Try JavaScript click if regular click fails
                self.driver.execute_script("arguments[0].click();", add_button)
                print("✅ Successfully clicked SVG plus button (via JavaScript)")
            
            time.sleep(1)  # Wait for cart to update
            return True
            
        except Exception as e:
            print(f"❌ Error clicking SVG plus button: {e}")
            return False
    
    def _add_regular_product_to_cart(self, product) -> bool:
        """Add regular product to cart using standard add to cart button."""
        try:
            # Look for standard add to cart buttons
            add_to_cart_selectors = [
                "[data-testhook='add-to-cart-button']",
                "[data-test-id='add-to-cart']",
                ".add-to-cart-button",
                "button[aria-label*='toevoegen']",
                "button[title*='toevoegen']",
                "button[aria-label*='winkelmandje']",
                ".ah-button--primary"
            ]
            
            button_found = False
            for selector in add_to_cart_selectors:
                try:
                    add_button = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    
                    # Scroll to button and click
                    self.driver.execute_script("arguments[0].scrollIntoView();", add_button)
                    time.sleep(0.5)
                    add_button.click()
                    
                    button_found = True
                    break
                except:
                    continue
            
            # Try XPath for text-based selection
            if not button_found:
                try:
                    xpath_selector = "//button[contains(text(), 'Toevoegen') or contains(text(), 'winkelmandje')]"
                    add_button = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((By.XPATH, xpath_selector))
                    )
                    add_button.click()
                    button_found = True
                except:
                    pass
            
            if not button_found:
                print(f"❌ Could not find add to cart button for {product['title']}")
                return False
            
            time.sleep(1)  # Wait for the cart to update
            return True
        
        except Exception as e:
            print(f"❌ Error adding regular product {product['title']}: {e}")
            return False

    def _search_and_add_product(self, product) -> bool:
        """Search for a product and add it to cart."""
        try:
            # Navigate to main AH page for search
            self.driver.get(self.config.ah_base_url)
            time.sleep(1)
            
            # Find search box
            search_selectors = [
                "[data-testhook='search-input']",
                "input[placeholder*='Zoeken']",
                "input[type='search']",
                ".search-input"
            ]
            
            search_box = None
            for selector in search_selectors:
                try:
                    search_box = self.driver.find_element(By.CSS_SELECTOR, selector)
                    break
                except:
                    continue
            
            if not search_box:
                print(f"❌ Could not find search box")
                return False
            
            # Search for the product
            search_box.clear()
            search_box.send_keys(product['title'])
            search_box.submit()
            
            time.sleep(2)
            
            # Look for the first product in search results and add to cart
            first_product = self.driver.find_element(By.CSS_SELECTOR, "[data-testhook='product-card']:first-child")
            return self._add_to_cart_with_svg_button(first_product)
            
        except Exception as e:
            print(f"❌ Error searching for {product['title']}: {e}")
            return False

    def _add_required_items(self) -> str:
        """Add required items: 2L half volle melk and 10 eggs."""
        try:
            results = []
            
            # Add milk
            print("🥛 Searching for 2L half volle melk...")
            if self._search_for_item("half volle melk"):
                results.append("✅ Added 2L half volle melk")
            else:
                results.append("❌ Failed to add 2L half volle melk")
            
            # Add eggs
            print("🥚 Searching for 10 eggs...")
            if self._search_for_item("eieren scharreleieren"):
                results.append("✅ Added eggs")
            else:
                results.append("❌ Failed to add eggs")
            
            return " | ".join(results)
            
        except Exception as e:
            return f"❌ Error adding required items: {e}"

    def _search_for_item(self, search_term: str) -> bool:
        """Search for a specific item and add first result to cart."""
        try:
            print(f"🔍 Searching for: {search_term}")
            
            # Navigate to main AH page
            self.driver.get(self.config.ah_base_url)
            time.sleep(1)
            
            # Find search box
            search_selectors = [
                "[data-testhook='search-input']",
                "input[placeholder*='Zoeken']",
                "input[type='search']",
                ".search-input",
                "#search-input"
            ]
            
            search_box = None
            for selector in search_selectors:
                try:
                    search_box = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if search_box.is_displayed():
                        break
                except:
                    continue
            
            if not search_box:
                print(f"❌ Could not find search box")
                return False
            
            # Search for the item
            search_box.clear()
            search_box.send_keys(search_term)
            search_box.send_keys("\n")  # Press Enter
            time.sleep(2)
            
            # Look for first product result
            product_selectors = [
                "[data-testhook='product-card']",
                ".product-card",
                "[class*='product-card']"
            ]
            
            first_product = None
            for selector in product_selectors:
                try:
                    products = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if products:
                        first_product = products[0]
                        break
                except:
                    continue
            
            if not first_product:
                print(f"❌ No products found for search: {search_term}")
                return False
            
            # Try to add the first product to cart
            try:
                # Click on the product first to go to its page
                first_product.click()
                time.sleep(1)
                
                # Look for add to cart button
                add_button_selectors = [
                    "[data-testhook='add-to-cart-button']",
                    "button[aria-label*='toevoegen']",
                    ".add-to-cart-button",
                    "svg.plus-button_icon__cSPiv",
                    "button svg[class*='plus-button']"
                ]
                
                for selector in add_button_selectors:
                    try:
                        if "svg" in selector:
                            # For SVG selectors, find the parent button
                            svg_elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                            add_button = svg_elem.find_element(By.XPATH, "./ancestor::button")
                        else:
                            add_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                        
                        if add_button.is_displayed() and add_button.is_enabled():
                            add_button.click()
                            print(f"✅ Successfully added {search_term} to cart")
                            time.sleep(1)
                            return True
                    except:
                        continue
                
                print(f"❌ Could not find add to cart button for {search_term}")
                return False
                
            except Exception as e:
                print(f"❌ Error adding {search_term} to cart: {e}")
                return False
            
        except Exception as e:
            print(f"❌ Error searching for {search_term}: {e}")
            return False

    def _validate_cart_interactive(self) -> str:
        """Validate cart contents with user interaction."""
        try:
            print("\n🛒 Validating cart contents...")
            
            # Navigate to cart page
            cart_selectors = [
                "[data-testhook='cart-button']",
                "[aria-label*='winkelmandje']",
                "a[href*='/winkelmandje']",
                ".cart-button"
            ]
            
            cart_button = None
            for selector in cart_selectors:
                try:
                    cart_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if cart_button.is_displayed():
                        break
                except:
                    continue
            
            if cart_button:
                cart_button.click()
                time.sleep(2)
                print("✅ Navigated to cart page")
            else:
                print("⚠️ Could not find cart button - cart may be empty or page structure changed")
            
            print("\n📱 Please review your cart in the browser:")
            print("   - Check if all desired products were added")
            print("   - Verify quantities are correct")
            print("   - Remove any unwanted items")
            print("   - Check the total price")
            
            validation_result = input("\nIs your cart looking good? (y/n): ").strip().lower()
            
            if validation_result in ['y', 'yes', 'ja']:
                return "✅ Cart validated successfully by user"
            else:
                return "⚠️ User reported cart issues - manual review needed"
                
        except Exception as e:
            return f"❌ Error during cart validation: {e}"
    
    def _setup_chrome_driver(self, interactive_mode: bool = False, for_automation: bool = False) -> webdriver.Chrome:
        """Setup Chrome driver with proper configuration to avoid profile conflicts."""
        try:
            chrome_options = Options()
            
            if interactive_mode and not for_automation:
                # For interactive mode (scraping), use a clean temporary profile
                print("🔧 Setting up Chrome for interactive scraping...")
                # Create unique temporary user data directory
                import tempfile
                temp_dir = tempfile.mkdtemp(prefix="chrome_profile_")
                chrome_options.add_argument(f"--user-data-dir={temp_dir}")
                chrome_options.add_argument("--no-first-run")
                chrome_options.add_argument("--no-default-browser-check")
            else:
                # For automation mode, use incognito to avoid profile conflicts
                print("🔧 Setting up Chrome for automation (incognito mode)...")
                chrome_options.add_argument("--incognito")
            
            # Common options for all modes
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage") 
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # Don't run headless for interactive modes
            if not interactive_mode and for_automation:
                # Only use headless for non-interactive automation
                pass  # Keep browser visible for user interaction
            
            # Setup service
            service = Service(ChromeDriverManager().install())
            
            # Create driver
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            driver.maximize_window()
            
            print("✅ Chrome driver setup successful")
            return driver
            
        except Exception as e:
            print(f"❌ Error setting up Chrome driver: {e}")
            # Fallback: try with minimal options
            try:
                print("🔄 Trying fallback Chrome setup...")
                chrome_options = Options()
                chrome_options.add_argument("--incognito")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)
                driver.maximize_window()
                
                print("✅ Fallback Chrome driver setup successful")
                return driver
                
            except Exception as fallback_error:
                print(f"❌ Fallback Chrome setup also failed: {fallback_error}")
                raise fallback_error

    def collect_interactive_requirements(self) -> Dict[str, Any]:
        """
        Collect additional shopping requirements from user through interactive prompts.
        
        Returns:
            Dictionary containing user's shopping preferences and requirements
        """
        print("\n📝 INTERACTIVE SHOPPING REQUIREMENTS")
        print("=" * 50)
        print("Let's customize your shopping list based on your specific needs!")
        
        requirements = {
            "dietary_preferences": [],
            "specific_items": [],
            "categories_focus": {},
            "budget_preference": "",
            "meal_planning": {},
            "allergies": [],
            "household_size": "",
            "special_occasions": ""
        }
        
        # Household size
        print("\n👥 HOUSEHOLD INFORMATION")
        household = input("How many people are you shopping for? (e.g., 2, 4, family of 5): ").strip()
        requirements["household_size"] = household
        
        # Dietary preferences
        print("\n🥗 DIETARY PREFERENCES")
        print("Select any dietary preferences (separate with commas):")
        print("- vegetarian, vegan, keto, low-carb, gluten-free, dairy-free, organic, healthy")
        dietary = input("Your preferences: ").strip()
        if dietary:
            requirements["dietary_preferences"] = [pref.strip().lower() for pref in dietary.split(",")]
        
        # Allergies
        print("\n⚠️  ALLERGIES & RESTRICTIONS")
        allergies = input("Any food allergies or restrictions? (e.g., nuts, shellfish, lactose): ").strip()
        if allergies:
            requirements["allergies"] = [allergy.strip().lower() for allergy in allergies.split(",")]
        
        # Specific required items
        print("\n📋 SPECIFIC ITEMS NEEDED")
        print("Enter specific items you need (one per line, press ENTER twice to finish):")
        print("Examples: 2L half volle melk, 10 eggs, whole grain bread, organic chicken, etc.")
        
        specific_items = []
        while True:
            item = input("Item (or ENTER to finish): ").strip()
            if not item:
                break
            
            # Parse quantity and item
            item_data = {
                "name": item,
                "quantity": "",
                "size": "",
                "brand_preference": ""
            }
            
            # Try to extract quantity/size info
            import re
            quantity_match = re.search(r'(\d+[\.,]?\d*)\s*([a-zA-Z]*)', item)
            if quantity_match:
                item_data["quantity"] = quantity_match.group(1)
                if quantity_match.group(2):
                    item_data["size"] = quantity_match.group(2)
            
            specific_items.append(item_data)
            print(f"  ✅ Added: {item}")
        
        requirements["specific_items"] = specific_items
        
        # Category focus
        print("\n🏷️  CATEGORY PREFERENCES")
        print("How much focus on each category? (1=low, 2=medium, 3=high, or skip)")
        
        categories = ["meat", "vegetables", "fruit", "dairy", "grains", "snacks", "beverages"]
        for category in categories:
            focus = input(f"{category.capitalize()} focus (1-3 or skip): ").strip()
            if focus and focus.isdigit() and 1 <= int(focus) <= 3:
                requirements["categories_focus"][category] = int(focus)
        
        # Budget preference
        print("\n💰 BUDGET PREFERENCE")
        budget_options = ["budget-conscious", "balanced", "premium"]
        print("Budget preference:")
        for i, option in enumerate(budget_options, 1):
            print(f"  {i}. {option}")
        
        budget_choice = input("Choose (1-3): ").strip()
        if budget_choice.isdigit() and 1 <= int(budget_choice) <= 3:
            requirements["budget_preference"] = budget_options[int(budget_choice) - 1]
        
        # Meal planning
        print("\n🍽️  MEAL PLANNING")
        meal_days = input("How many days are you shopping for? (e.g., 3, 7, 14): ").strip()
        meal_types = input("Meal types needed (breakfast, lunch, dinner, snacks): ").strip()
        
        if meal_days or meal_types:
            requirements["meal_planning"] = {
                "days": meal_days,
                "meal_types": [meal.strip().lower() for meal in meal_types.split(",") if meal.strip()]
            }
        
        # Special occasions
        print("\n🎉 SPECIAL OCCASIONS")
        special = input("Any special occasions or events? (party, BBQ, birthday, etc.): ").strip()
        requirements["special_occasions"] = special
        
        # Summary
        print("\n📋 REQUIREMENTS SUMMARY")
        print("=" * 30)
        if requirements["household_size"]:
            print(f"👥 Household: {requirements['household_size']}")
        if requirements["dietary_preferences"]:
            print(f"🥗 Dietary: {', '.join(requirements['dietary_preferences'])}")
        if requirements["allergies"]:
            print(f"⚠️  Allergies: {', '.join(requirements['allergies'])}")
        if requirements["specific_items"]:
            print(f"📋 Specific items: {len(requirements['specific_items'])} items")
        if requirements["budget_preference"]:
            print(f"💰 Budget: {requirements['budget_preference']}")
        if requirements["special_occasions"]:
            print(f"🎉 Special: {requirements['special_occasions']}")
        
        confirm = input("\nLooks good? (y/n): ").strip().lower()
        if confirm not in ['y', 'yes', 'ja']:
            print("Let's try again...")
            return self.collect_interactive_requirements()
        
        return requirements

    def scrape_product_categories(self, driver) -> Dict[str, List[str]]:
        """
        Scrape available product categories from the AH website.
        
        Returns:
            Dictionary mapping category names to their subcategories
        """
        categories = {}
        try:
            print("🏷️ Scraping website categories...")
            
            # Look for navigation menu or category links
            category_selectors = [
                "[data-testhook='category-nav']",
                ".category-navigation", 
                ".main-navigation",
                "[aria-label*='categor']",
                ".nav-categories",
                "[data-testid*='category']"
            ]
            
            category_elements = []
            for selector in category_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        category_elements.extend(elements)
                        break
                except:
                    continue
            
            # If no category navigation found, look for category links
            if not category_elements:
                link_selectors = [
                    "a[href*='/categorie/']",
                    "a[href*='/category/']", 
                    ".category-link",
                    "[data-category]"
                ]
                
                for selector in link_selectors:
                    try:
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements:
                            category_elements.extend(elements[:20])  # Limit to first 20
                            break
                    except:
                        continue
            
            # Extract category information
            if category_elements:
                print(f"Found {len(category_elements)} category elements")
                
                for element in category_elements:
                    try:
                        category_name = element.text.strip()
                        category_url = element.get_attribute("href")
                        
                        if category_name and len(category_name) > 1:
                            # Clean up category name
                            category_clean = category_name.lower().strip()
                            
                            # Map to our standard categories
                            if any(keyword in category_clean for keyword in ['vlees', 'meat', 'vis', 'fish', 'kip', 'chicken']):
                                if 'meat' not in categories:
                                    categories['meat'] = []
                                categories['meat'].append(category_name)
                            elif any(keyword in category_clean for keyword in ['groente', 'vegetable', 'sla', 'salad']):
                                if 'vegetables' not in categories:
                                    categories['vegetables'] = []
                                categories['vegetables'].append(category_name)
                            elif any(keyword in category_clean for keyword in ['fruit', 'appel', 'banaan', 'aardbei']):
                                if 'fruit' not in categories:
                                    categories['fruit'] = []
                                categories['fruit'].append(category_name)
                            elif any(keyword in category_clean for keyword in ['zuivel', 'dairy', 'melk', 'kaas', 'yoghurt']):
                                if 'dairy' not in categories:
                                    categories['dairy'] = []
                                categories['dairy'].append(category_name)
                            elif any(keyword in category_clean for keyword in ['brood', 'bakkerij', 'bread', 'graan']):
                                if 'grains' not in categories:
                                    categories['grains'] = []
                                categories['grains'].append(category_name)
                            elif any(keyword in category_clean for keyword in ['snack', 'snoep', 'chips', 'koek']):
                                if 'snacks' not in categories:
                                    categories['snacks'] = []
                                categories['snacks'].append(category_name)
                            elif any(keyword in category_clean for keyword in ['drank', 'beverage', 'water', 'sap']):
                                if 'beverages' not in categories:
                                    categories['beverages'] = []
                                categories['beverages'].append(category_name)
                            else:
                                if 'other' not in categories:
                                    categories['other'] = []
                                categories['other'].append(category_name)
                                
                    except:
                        continue
                        
                print(f"✅ Extracted categories: {list(categories.keys())}")
                for cat, items in categories.items():
                    print(f"   {cat}: {len(items)} subcategories")
                    
            else:
                print("⚠️ No category elements found, using default categories")
                # Fallback to default categories
                categories = {
                    'meat': ['Vlees, vis & vegetarisch'],
                    'vegetables': ['Groente & fruit'],
                    'fruit': ['Groente & fruit'],
                    'dairy': ['Zuivel & eieren'],
                    'grains': ['Brood & bakkerij'],
                    'snacks': ['Snacks & snoep'],
                    'beverages': ['Dranken'],
                    'other': ['Overige']
                }
                
        except Exception as e:
            print(f"❌ Error scraping categories: {e}")
            # Fallback categories
            categories = {
                'meat': ['Vlees & vis'],
                'vegetables': ['Groenten'],
                'fruit': ['Fruit'],
                'dairy': ['Zuivel'],
                'grains': ['Brood'],
                'snacks': ['Snacks'],
                'beverages': ['Dranken'],
                'other': ['Overige']
            }
            
        return categories


def main():
    """Main function to run the shopping agent."""
    print("🛒 Welcome to AH Shopping Agent!")
    print("=" * 50)
    
    try:
        # Initialize the agent
        agent = AHShoppingAgent()
        
        # Get user requirements
        print("\n📝 Please describe your shopping requirements:")
        print("(Or press ENTER for default requirements)")
        user_input = input("\nYour requirements: ").strip()
        
        if not user_input:
            user_input = None
        
        # Run the shopping workflow
        result = agent.run_shopping_workflow(
            user_requirements=user_input,
            interactive_mode=True
        )
        
        print(f"\n🎉 Workflow completed!")
        print(f"📋 Result: {result}")
        
    except KeyboardInterrupt:
        print("\n\n⏹️ Shopping agent stopped by user")
    except Exception as e:
        print(f"\n❌ Error running shopping agent: {e}")
    finally:
        print("\n👋 Thank you for using AH Shopping Agent!")


if __name__ == "__main__":
    main()
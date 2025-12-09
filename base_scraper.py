"""Base scraper class for AH.nl - supports multiple product categories"""
import json
import time
import os
from abc import ABC, abstractmethod
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


class BaseAHScraper(ABC):
    """Base scraper class for AH.nl - can be extended for different categories"""
    
    def __init__(self, config, category_name: str, base_url: str):
        """
        初始化基础scraper
        
        Args:
            config: Config对象
            category_name: 品类名称（如 "bonus", "groente", "vlees"等）
            base_url: 该品类的URL
        """
        self.config = config
        self.category_name = category_name
        self.base_url = base_url
        self.driver = None
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        # 缓存文件路径
        self.cache_file = f"products_cache_{category_name}.json"
    
    def _load_cache(self) -> Optional[List[Dict[str, Any]]]:
        """Load products from cache if valid"""
        if not os.path.exists(self.cache_file):
            return None
        
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Check if cache has timestamp
            if isinstance(cache_data, dict) and 'timestamp' in cache_data:
                cache_time = datetime.fromisoformat(cache_data['timestamp'])
                expiry_time = cache_time + timedelta(hours=self.config.cache_expiry_hours)
                
                if datetime.now() < expiry_time:
                    print(f"✅ Using cached {self.category_name} products (cached at {cache_time.strftime('%Y-%m-%d %H:%M:%S')})")
                    return cache_data.get('products', [])
                else:
                    print(f"ℹ️ Cache expired (expired at {expiry_time.strftime('%Y-%m-%d %H:%M:%S')})")
                    return None
            else:
                return None
                
        except Exception as e:
            print(f"⚠️ Error loading cache: {e}")
            return None
    
    def _save_cache(self, products: List[Dict[str, Any]]):
        """Save products to cache with timestamp"""
        try:
            cache_data = {
                'timestamp': datetime.now().isoformat(),
                'category': self.category_name,
                'products': products
            }
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            print(f"✅ {self.category_name} products cached to {self.cache_file}")
        except Exception as e:
            print(f"⚠️ Error saving cache: {e}")
    
    def delete_cache(self):
        """Delete cache file completely"""
        if os.path.exists(self.cache_file):
            try:
                os.remove(self.cache_file)
                print(f"🗑️  Deleted cache file: {self.cache_file}")
            except Exception as e:
                print(f"⚠️ Error deleting cache file: {e}")
    
    def _setup_driver(self):
        """Setup Chrome driver"""
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
    
    def _accept_cookies(self):
        """Accept cookies - common method for all scrapers"""
        print("🍪 Looking for cookie consent dialog...")
        
        accept_selectors = [
            "//button[@data-testid='accept-cookies']",
            "//button[contains(text(), 'Accepteren')]",
            "//button[contains(text(), 'Accept')]",
        ]
        
        for selector in accept_selectors:
            try:
                cookie_button = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                self.driver.execute_script("arguments[0].scrollIntoView(true);", cookie_button)
                time.sleep(0.5)
                cookie_button.click()
                print("✅ Cookies accepted")
                time.sleep(1)
                return True
            except:
                continue
        
        print("⚠️ Cookie banner not found or could not be accepted - continuing anyway")
        return False
    
    @abstractmethod
    def _try_lightweight_scrape(self) -> Optional[List[Dict[str, Any]]]:
        """
        尝试使用轻量级方法抓取（requests + BeautifulSoup）
        子类需要实现这个方法
        
        Returns:
            产品列表，如果失败返回None
        """
        pass
    
    @abstractmethod
    def _scrape_with_selenium(self) -> List[Dict[str, Any]]:
        """
        使用Selenium抓取（备用方法）
        子类需要实现这个方法
        
        Returns:
            产品列表
        """
        pass
    
    @abstractmethod
    def _extract_product_from_element(self, element) -> Optional[Dict[str, Any]]:
        """
        从HTML元素中提取产品信息
        子类需要实现这个方法
        
        Args:
            element: Selenium WebElement或BeautifulSoup元素
        
        Returns:
            产品字典，如果提取失败返回None
        """
        pass
    
    def scrape_products(self, use_cache: bool = True, 
                       prefer_lightweight: bool = True) -> List[Dict[str, Any]]:
        """
        抓取产品 - 通用方法
        
        Args:
            use_cache: 是否使用缓存
            prefer_lightweight: 是否优先使用轻量级方法
        
        Returns:
            产品列表
        """
        # Step 1: Check cache
        if use_cache:
            cached_products = self._load_cache()
            if cached_products:
                print(f"✅ Using {len(cached_products)} cached {self.category_name} products")
                return cached_products
        
        print(f"🔍 Starting to scrape AH.nl/{self.category_name} page...")
        
        # Step 2: Try lightweight method first
        if prefer_lightweight:
            products = self._try_lightweight_scrape()
            if products:
                self._save_cache(products)
                return products
        
        # Step 3: Fallback to Selenium
        print("🌐 Using Selenium (fallback method)...")
        products = self._scrape_with_selenium()
        self._save_cache(products)
        return products
    
    def summarize_products(self, products: List[Dict[str, Any]]) -> str:
        """Summarize products - can be overridden by subclasses"""
        if not products:
            return f"No {self.category_name} products found"
        
        summary = f"📊 AH.nl {self.category_name.capitalize()} Products Summary\n"
        summary += f"=" * 50 + "\n"
        summary += f"Total products: {len(products)}\n\n"
        
        # Show top 10 products
        summary += f"🔥 Top 10 Products:\n"
        for i, product in enumerate(products[:10], 1):
            summary += f"  {i}. {product['title']} - {product.get('price', 'Unknown')}\n"
        
        return summary
    
    def __del__(self):
        """Cleanup"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass


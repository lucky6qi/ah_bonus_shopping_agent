"""Session and Cookie Management for AH.nl automation"""
import os
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any, Union
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


class SessionManager:
    """管理Chrome浏览器会话和cookies，支持持久化登录状态"""
    
    def __init__(self, user_data_dir: Optional[str] = None):
        """
        初始化Session Manager
        
        Args:
            user_data_dir: Chrome用户数据目录路径，如果为None则使用默认路径
                          (~/.ah_shopping_agent/chrome_profile)
        """
        if user_data_dir is None:
            # 使用默认路径：用户主目录下的.ah_shopping_agent/chrome_profile
            home_dir = Path.home()
            default_dir = home_dir / ".ah_shopping_agent" / "chrome_profile"
            user_data_dir = str(default_dir)
        
        self.user_data_dir = Path(user_data_dir)
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存登录状态的文件
        self.login_state_file = self.user_data_dir.parent / "login_state.json"
        
        # 清理可能的锁定文件
        self._cleanup_lock_files()
        
        print(f"📁 Session directory: {self.user_data_dir}")
    
    def _cleanup_lock_files(self):
        """清理可能阻止 Chrome 启动的锁定文件"""
        import glob
        
        # 先检查是否有 Chrome 进程在使用这个 profile
        import subprocess
        try:
            result = subprocess.run(
                ['pgrep', '-f', f'user-data-dir.*{self.user_data_dir}'],
                capture_output=True,
                text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                print(f"⚠️ 检测到 Chrome 进程正在使用该 profile，正在关闭...")
                subprocess.run(['pkill', '-f', f'user-data-dir.*{self.user_data_dir}'], 
                             capture_output=True)
                import time
                time.sleep(2)
        except Exception:
            pass
        
        # 清理锁定文件
        lock_patterns = [
            "SingletonLock",
            "SingletonSocket",
            "SingletonCookie",
            "lockfile",
            ".lock"
        ]
        
        for pattern in lock_patterns:
            for lock_file in glob.glob(str(self.user_data_dir / pattern)):
                try:
                    Path(lock_file).unlink()
                    print(f"🧹 Cleaned up lock file: {lock_file}")
                except Exception:
                    pass
        
        # 清理 Chromium 锁定文件
        for lock_file in glob.glob(str(self.user_data_dir / ".org.chromium.Chromium.*")):
            try:
                Path(lock_file).unlink()
                print(f"🧹 Cleaned up Chromium lock file: {lock_file}")
            except Exception:
                pass
    
    def create_driver(self, headless: bool = False) -> webdriver.Chrome:
        """
        创建Chrome driver，使用用户数据目录保存cookies和登录状态
        
        Args:
            headless: 是否使用无头模式
        
        Returns:
            Chrome WebDriver实例
        """
        chrome_options = Options()
        
        if headless:
            chrome_options.add_argument("--headless")
        
        # 使用用户数据目录 - 这是关键！可以保存cookies和登录状态
        chrome_options.add_argument(f"--user-data-dir={self.user_data_dir}")
        
        # 其他选项
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # 尝试使用 ChromeDriverManager，如果失败则尝试直接使用系统 chromedriver
        try:
            # 强制重新下载匹配的 ChromeDriver
            driver_path = ChromeDriverManager().install()
            print(f"✅ Using ChromeDriver: {driver_path}")
            
            # 启用详细日志以诊断问题
            service = Service(
                driver_path,
                log_path=str(self.user_data_dir.parent / "chromedriver.log")
            )
            
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            print(f"⚠️ ChromeDriverManager failed: {e}")
            print("🔄 Trying to use system chromedriver...")
            # 回退方案：尝试直接使用 ChromeDriver（如果系统已安装）
            try:
                driver = webdriver.Chrome(options=chrome_options)
            except Exception as e2:
                print(f"❌ Failed to create Chrome driver: {e2}")
                print("\n💡 可能的解决方案：")
                print("   1. 更新 Chrome 浏览器到最新版本")
                print("   2. 运行: pip install --upgrade webdriver-manager")
                print("   3. 清理缓存: rm -rf ~/.wdm")
                raise
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        # 不resize窗口，保持默认大小
        
        return driver
    
    def save_login_state(self, username: Optional[str] = None, logged_in: bool = False):
        """
        保存登录状态
        
        Args:
            username: 用户名（可选）
            logged_in: 是否已登录
        """
        state = {
            "username": username,
            "logged_in": logged_in,
            "last_check": time.time()
        }
        
        try:
            with open(self.login_state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"⚠️ Failed to save login state: {e}")
    
    def load_login_state(self) -> Dict[str, Any]:
        """
        加载登录状态
        
        Returns:
            登录状态字典
        """
        if not self.login_state_file.exists():
            return {"logged_in": False}
        
        try:
            with open(self.login_state_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Failed to load login state: {e}")
            return {"logged_in": False}
    
    def check_login_status(self, driver: webdriver.Chrome, base_url: str = "https://www.ah.nl", refresh_page: bool = False, debug: bool = False) -> Optional[bool]:
        """
        检查当前是否已登录
        
        Args:
            driver: Chrome WebDriver实例
            base_url: AH网站基础URL
            refresh_page: 是否刷新页面（默认False，避免打断用户登录）
        
        Returns:
            True如果已登录，False如果未登录
        """
        try:
            # 只在明确要求时才刷新页面，避免打断用户登录
            if refresh_page:
                driver.get(base_url)
                time.sleep(2)
            
            # 检查登录状态 - 查找登录按钮或用户图标
            # 如果找到登录按钮，说明未登录
            login_indicators = [
                "//a[contains(@href, 'inloggen')]",
                "//button[contains(text(), 'Inloggen')]",
                "//a[contains(@href, '/inloggen')]",
                "[data-testhook='login-button']"
            ]
            
            for indicator in login_indicators:
                try:
                    if "//" in indicator:
                        element = driver.find_element(By.XPATH, indicator)
                    else:
                        element = driver.find_element(By.CSS_SELECTOR, indicator)
                    
                    if element.is_displayed():
                        print("🔐 检测到未登录状态")
                        return False
                except:
                    continue
            
            # 检查是否找到用户相关元素（表示已登录）
            # 优先检测Premium User图标（根据用户提供的SVG结构）
            premium_user_indicators = [
                # 精确匹配Premium User SVG
                "//svg[@title='Premium User']",
                "//svg[contains(@class, 'userIcon-I5WQMR')]",
                "//svg[contains(@class, 'userIcon')]",
                # 通过class检测
                "//*[contains(@class, 'userIcon-I5WQMR')]",
                "//*[contains(@class, 'userIcon')]",
                # 通过父元素检测
                "//*[contains(@class, 'icon-_1y03W')]",
            ]
            
            for indicator in premium_user_indicators:
                try:
                    elements = driver.find_elements(By.XPATH, indicator)
                    if debug and elements:
                        print(f"   🔍 找到 {len(elements)} 个匹配元素: {indicator}")
                    for element in elements:
                        try:
                            # 检查元素是否可见（可能在DOM中但不可见）
                            if element.is_displayed():
                                # 额外检查：确认是Premium User
                                title = element.get_attribute("title")
                                class_attr = element.get_attribute("class") or ""
                                if debug:
                                    print(f"   🔍 元素可见 - title: {title}, class: {class_attr}")
                                if "Premium User" in (title or "") or "userIcon" in class_attr:
                                    print("✅ 检测到已登录状态（通过Premium User图标）")
                                    self.save_login_state(logged_in=True)
                                    return True
                        except Exception as e:
                            if debug:
                                print(f"   ⚠️ 检查元素可见性时出错: {e}")
                            continue
                except Exception as e:
                    if debug:
                        print(f"   ⚠️ 查找元素时出错: {e}")
                    continue
            
            # 检查其他用户相关元素
            user_indicators = [
                "//a[contains(@href, '/mijn-ah')]",
                "//button[contains(@aria-label, 'Account')]",
                "[data-testhook='account-button']",
                "[data-testhook='user-menu']",
            ]
            
            for indicator in user_indicators:
                try:
                    if "//" in indicator:
                        element = driver.find_element(By.XPATH, indicator)
                    else:
                        element = driver.find_element(By.CSS_SELECTOR, indicator)
                    
                    if element.is_displayed():
                        print("✅ 检测到已登录状态（通过用户菜单）")
                        self.save_login_state(logged_in=True)
                        return True
                except:
                    continue
            
            # 额外检查：查找包含"Premium User"文本的元素
            try:
                premium_user_elements = driver.find_elements(By.XPATH, 
                    "//*[contains(text(), 'Premium User') or contains(@title, 'Premium User')]")
                if premium_user_elements:
                    for elem in premium_user_elements:
                        try:
                            if elem.is_displayed():
                                print("✅ 检测到已登录状态（通过Premium User文本）")
                                self.save_login_state(logged_in=True)
                                return True
                        except:
                            continue
            except:
                pass
            
            # 检查页面URL是否包含登录后的页面
            try:
                current_url = driver.current_url
                if '/mijn-ah' in current_url or '/account' in current_url.lower():
                    print("✅ 检测到已登录状态（通过URL）")
                    self.save_login_state(logged_in=True)
                    return True
            except:
                pass
            
            # 尝试通过页面源码检测（更宽松的方式）
            try:
                page_source = driver.page_source
                if 'Premium User' in page_source or 'userIcon-I5WQMR' in page_source:
                    # 如果页面源码中包含Premium User，尝试更精确的检测
                    # 检查是否有可见的用户相关元素
                    try:
                        # 尝试查找任何包含userIcon的元素
                        user_elements = driver.find_elements(By.XPATH, "//*[contains(@class, 'user')]")
                        for elem in user_elements[:10]:  # 只检查前10个
                            try:
                                if elem.is_displayed():
                                    print("✅ 检测到已登录状态（通过页面内容）")
                                    self.save_login_state(logged_in=True)
                                    return True
                            except:
                                continue
                    except:
                        pass
            except:
                pass
            
            # 如果都不确定，返回None表示无法确定（不刷新页面，让用户继续登录）
            # 返回False会导致频繁刷新，所以返回None让调用者知道状态不确定
            return None  # None表示无法确定，需要继续等待
            
        except Exception as e:
            print(f"⚠️ 检查登录状态时出错: {e}")
            return None  # 出错时也返回None，避免误判
    
    def wait_for_manual_login(self, driver: webdriver.Chrome, timeout: int = 300):
        """
        等待用户手动登录
        
        Args:
            driver: Chrome WebDriver实例
            timeout: 超时时间（秒），默认5分钟
        
        Returns:
            True如果登录成功，False如果超时
        """
        print("\n" + "=" * 60)
        print("🔐 需要登录")
        print("=" * 60)
        print("请在浏览器中完成登录操作：")
        print("  1. 输入用户名和密码")
        print("  2. 如果出现手机验证码，请手动输入")
        print("  3. 登录成功后，程序会自动继续")
        print("=" * 60)
        print(f"\n⏳ 等待登录（最多{timeout}秒）...")
        print("💡 提示：程序不会刷新页面，请放心登录")
        
        # 只在开始时检查一次登录状态（刷新页面）
        # 之后不再刷新，避免打断用户登录
        initial_check = self.check_login_status(driver, refresh_page=True)
        if initial_check is True:
            print("✅ 检测到已登录状态")
            self.save_login_state(logged_in=True)
            return True
        
        start_time = time.time()
        check_interval = 2  # 每2秒检查一次（不刷新页面）
        last_status_print = 0
        check_count = 0
        
        while time.time() - start_time < timeout:
            check_count += 1
            # 检查登录状态，但不刷新页面（避免打断用户登录）
            # 每5次检查时启用debug模式，帮助诊断问题
            debug_mode = (check_count % 5 == 0)
            status = self.check_login_status(driver, refresh_page=False, debug=debug_mode)
            
            if status is True:
                elapsed = int(time.time() - start_time)
                print(f"\n✅ 登录成功！（耗时 {elapsed} 秒）")
                self.save_login_state(logged_in=True)
                return True
            elif status is False:
                # 明确检测到未登录，但也不刷新页面
                pass
            # status is None 表示无法确定，继续等待
            
            time.sleep(check_interval)
            remaining = int(timeout - (time.time() - start_time))
            
            # 每10秒打印一次状态（不刷新页面）
            if remaining > 0 and int(time.time() - start_time) - last_status_print >= 10:
                print(f"   等待中... 剩余 {remaining} 秒（不会刷新页面，请继续登录）")
                # 打印当前检测到的状态，帮助调试
                if status is None:
                    print(f"   💡 提示：无法确定登录状态，请确保已登录")
                elif status is False:
                    print(f"   💡 提示：检测到未登录状态")
                last_status_print = int(time.time() - start_time)
        
        print(f"\n⏰ 超时：{timeout}秒内未检测到登录")
        return False
    
    def ensure_logged_in(self, driver: webdriver.Chrome, 
                        base_url: str = "https://www.ah.nl",
                        auto_wait: bool = True) -> bool:
        """
        确保用户已登录，如果未登录则等待手动登录
        
        Args:
            driver: Chrome WebDriver实例
            base_url: AH网站基础URL
            auto_wait: 如果未登录，是否自动等待用户手动登录
        
        Returns:
            True如果已登录，False如果未登录或登录失败
        """
        # 先检查是否已登录（刷新页面一次）
        status = self.check_login_status(driver, base_url, refresh_page=True)
        if status is True:
            return True
        
        # 如果未登录且auto_wait为True，等待用户手动登录
        if auto_wait:
            return self.wait_for_manual_login(driver)
        else:
            print("⚠️ 未登录，请手动登录后再继续")
            return False
    
    def clear_session(self):
        """清除会话数据（谨慎使用！）"""
        try:
            import shutil
            if self.user_data_dir.exists():
                shutil.rmtree(self.user_data_dir)
                print(f"🗑️  已清除会话目录: {self.user_data_dir}")
            
            if self.login_state_file.exists():
                self.login_state_file.unlink()
                print(f"🗑️  已清除登录状态文件")
        except Exception as e:
            print(f"⚠️ 清除会话时出错: {e}")


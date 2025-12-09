import os
from dataclasses import dataclass
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    """Simplified configuration class"""
    
    # ═══════════════════════════════════════════════════════════
    # 🔴 LLM SETTINGS - Anthropic Claude API Key
    # ═══════════════════════════════════════════════════════════
    anthropic_api_key: Optional[str] = None
    
    # AH Website Settings
    ah_bonus_url: str = "https://www.ah.nl/bonus"
    ah_base_url: str = "https://www.ah.nl"
    
    # Data Storage
    products_cache_file: str = "products_cache.json"
    
    # Scraper Settings
    max_products: int = 1000
    request_timeout: int = 10
    cache_expiry_hours: int = 6  # Cache expiry time in hours
    
    # Session/Cookie Management
    chrome_user_data_dir: Optional[str] = None  # Chrome用户数据目录，None则使用默认路径
    login_timeout: int = 300  # 登录超时时间（秒），默认5分钟
    
    # Auto Mode Settings
    auto_mode: bool = False  # 自动模式，跳过所有用户确认
    notification_email: Optional[str] = None  # 完成通知邮箱
    
    # Data Storage
    eerder_gekocht_file: str = "eerder_gekocht_products.json"  # eerder-gekocht数据文件
    
    @classmethod
    def from_env(cls) -> 'Config':
        """Create configuration from .env file or environment variables"""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        chrome_data_dir = os.getenv("CHROME_USER_DATA_DIR")
        login_timeout = int(os.getenv("LOGIN_TIMEOUT", "300"))
        auto_mode = os.getenv("AUTO_MODE", "false").lower() == "true"
        notification_email = os.getenv("NOTIFICATION_EMAIL")
        
        return cls(
            anthropic_api_key=api_key,
            chrome_user_data_dir=chrome_data_dir,
            login_timeout=login_timeout,
            auto_mode=auto_mode,
            notification_email=notification_email,
        )

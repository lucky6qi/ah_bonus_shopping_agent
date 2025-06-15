import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class AgentConfig:
    """Configuration class for the shopping agent."""
    
    # LLM Settings
    llm_provider: str = "anthropic"  # "ollama", "openai", or "anthropic"
    model_name: str = "claude-3-5-sonnet-20241022"  # Latest Claude model
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    
    # Product Selection Settings
    meat_count: int = 3
    vegetable_count: int = 5
    fruit_count: int = 3
    max_products_to_scrape: int = 1000  # Increased from 50 to scrape all products
    
    # Automation Settings
    headless_scraping: bool = True
    headless_automation: bool = False  # Keep browser visible for automation
    page_load_timeout: int = 10
    automation_delay: float = 2.0
    
    # Chrome Profile Settings (for persistent login)
    use_existing_chrome_profile: bool = True  # Changed to True
    chrome_profile_path: Optional[str] = None  # Will auto-detect default Chrome profile
    chrome_profile_name: Optional[str] = "Default"  # Profile name to use
    
    # AH Website Settings
    ah_bonus_url: str = "https://www.ah.nl/bonus"
    ah_base_url: str = "https://www.ah.nl"
    
    # Product Categorization Keywords (Dutch)
    meat_keywords: list = None
    vegetable_keywords: list = None
    fruit_keywords: list = None
    
    def __post_init__(self):
        """Initialize default keywords if not provided."""
        if self.meat_keywords is None:
            self.meat_keywords = [
                "vlees", "kip", "rundvlees", "varken", "worst", "gehakt", 
                "biefstuk", "kipfilet", "spek", "ham", "salami", "braadworst",
                "kalkoen", "lam", "vis", "zalm", "tonijn", "kabeljauw"
            ]
        
        if self.vegetable_keywords is None:
            self.vegetable_keywords = [
                "groente", "tomaat", "ui", "wortel", "paprika", "broccoli", 
                "spinazie", "sla", "komkommer", "courgette", "aubergine",
                "prei", "champignons", "rode kool", "witte kool", "bloemkool"
            ]
            
        if self.fruit_keywords is None:
            self.fruit_keywords = [
                "fruit", "appel", "banaan", "sinaasappel", "peer", "druiven", 
                "aardbei", "citroen", "kiwi", "ananas", "mango", "avocado",
                "perzik", "pruim", "kers", "frambozen", "bosbessen"
            ]
    
    @classmethod
    def from_env(cls) -> 'AgentConfig':
        """Create configuration from environment variables."""
        return cls(
            llm_provider=os.getenv("LLM_PROVIDER", "anthropic"),
            model_name=os.getenv("MODEL_NAME", "claude-3-5-sonnet-20241022"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            meat_count=int(os.getenv("MEAT_COUNT", "3")),
            vegetable_count=int(os.getenv("VEGETABLE_COUNT", "5")),
            fruit_count=int(os.getenv("FRUIT_COUNT", "3")),
            headless_scraping=os.getenv("HEADLESS_SCRAPING", "true").lower() == "true",
            headless_automation=os.getenv("HEADLESS_AUTOMATION", "false").lower() == "true",
            use_existing_chrome_profile=os.getenv("USE_EXISTING_CHROME_PROFILE", "false").lower() == "true",
            chrome_profile_path=os.getenv("CHROME_PROFILE_PATH"),
            chrome_profile_name=os.getenv("CHROME_PROFILE_NAME", "Default")
        )
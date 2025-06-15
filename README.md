# AH Shopping Agent

An intelligent shopping agent built with LlamaIndex that can automatically scrape Albert Heijn (AH) bonus products, use AI to select items by category, and automate adding them to your shopping cart.

## Features

- **🤖 AI-Powered Product Selection**: Uses LlamaIndex with LLM (Ollama/OpenAI) to intelligently select products
- **🕷️ Web Scraping**: Automatically scrapes AH bonus page for current deals
- **🛒 Cart Automation**: Uses Selenium to automatically add selected products to cart
- **📊 Smart Categorization**: Categorizes products into meat, vegetables, fruits using Dutch keywords
- **⚙️ Configurable**: Flexible configuration for product counts, LLM providers, and automation settings
- **🔄 Robust Error Handling**: Multiple selector strategies and fallbacks for reliable automation

## Prerequisites

- **Python 3.10 or later**
- **Chrome browser** (for Selenium automation)
- **LLM Backend**: Either:
  - Ollama with llama3.2 model installed locally, OR
  - OpenAI API key for GPT models

### Setting up Ollama (Recommended)

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull the llama3.2 model
ollama pull llama3.2

# Start Ollama service
ollama serve
```

## Installation

### Option 1: Poetry (Recommended)

```bash
# Clone the repository
git clone <repository-url>
cd shopping_agent

# Install dependencies using Poetry
poetry install

# Activate the virtual environment
poetry shell
```

### Option 2: pip

```bash
# Clone the repository
git clone <repository-url>
cd shopping_agent

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Quick Start

```bash
# Run with default settings (3 meat, 5 vegetables, 3 fruits)
python shopping_agent.py

# Or run the example script
python example.py
```

### Command Line Options

```bash
# Use OpenAI instead of Ollama
python shopping_agent.py --llm openai --model gpt-4

# Customize product counts
python shopping_agent.py --meat 2 --vegetables 4 --fruits 2

# Run in headless mode (hide browser)
python shopping_agent.py --headless

# Combine options
python shopping_agent.py --llm ollama --model llama3.2 --meat 1 --vegetables 3 --fruits 1
```

### Programmatic Usage

```python
import asyncio
from shopping_agent import AHShoppingAgent
from config import AgentConfig

# Create custom configuration
config = AgentConfig(
    llm_provider="ollama",  # or "openai"
    model_name="llama3.2",  # or "gpt-4"
    meat_count=3,
    vegetable_count=5,
    fruit_count=3,
    headless_automation=False  # Show browser during automation
)

# Create and run agent
agent = AHShoppingAgent(config=config)
result = await agent.run_shopping_workflow()
```

### Environment Variables

You can configure the agent using environment variables:

```bash
export LLM_PROVIDER=ollama
export MODEL_NAME=llama3.2
export MEAT_COUNT=3
export VEGETABLE_COUNT=5
export FRUIT_COUNT=3
export HEADLESS_SCRAPING=true
export HEADLESS_AUTOMATION=false
export OPENAI_API_KEY=your_api_key_here  # Only needed for OpenAI
```

Then use:

```python
config = AgentConfig.from_env()
agent = AHShoppingAgent(config=config)
```

## How It Works

1. **🔍 Product Scraping**: 
   - Navigates to AH bonus page using Selenium
   - Extracts product information (title, price, image, URL)
   - Categorizes products using Dutch keyword matching

2. **🤖 AI Selection**:
   - Uses LlamaIndex ReAct agent with custom tools
   - LLM intelligently selects random products from each category
   - Respects specified counts for meat, vegetables, and fruits

3. **🛒 Cart Automation**:
   - Opens browser and navigates to each product page
   - Finds and clicks "Add to Cart" buttons using multiple selector strategies
   - Provides detailed feedback on success/failure for each product

## Configuration Options

The `AgentConfig` class supports extensive customization:

```python
@dataclass
class AgentConfig:
    # LLM Settings
    llm_provider: str = "ollama"  # "ollama" or "openai"
    model_name: str = "llama3.2"
    openai_api_key: Optional[str] = None
    
    # Product Selection
    meat_count: int = 3
    vegetable_count: int = 5
    fruit_count: int = 3
    max_products_to_scrape: int = 50
    
    # Automation Settings
    headless_scraping: bool = True
    headless_automation: bool = False
    page_load_timeout: int = 10
    automation_delay: float = 2.0
    
    # Custom keywords for categorization
    meat_keywords: list = [...]
    vegetable_keywords: list = [...]
    fruit_keywords: list = [...]
```

## Troubleshooting

### Common Issues

1. **Chrome Driver Issues**:
   - The script automatically downloads ChromeDriver
   - Ensure Chrome browser is installed and up to date

2. **LLM Connection Issues**:
   - For Ollama: Make sure `ollama serve` is running and model is pulled
   - For OpenAI: Verify your API key is set correctly

3. **Website Changes**:
   - AH may update their website structure
   - The script uses multiple selector strategies for robustness
   - Check for updates if scraping fails

4. **Network Issues**:
   - Ensure stable internet connection
   - Consider increasing `automation_delay` for slower connections

### Debug Mode

Run with verbose output to see detailed logs:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Architecture

```
shopping_agent.py     # Main agent class with LlamaIndex integration
├── AHShoppingAgent   # Core agent class
├── scrape_ah_bonus_products()  # Web scraping functionality
├── create_product_selection_tool()  # LLM tool for product selection
├── create_cart_automation_tool()    # LLM tool for cart automation
└── run_shopping_workflow()  # Complete workflow orchestration

config.py            # Configuration management
├── AgentConfig      # Dataclass for all settings
└── Environment variable support

example.py           # Usage examples and demo script
```

## Dependencies

- **LlamaIndex**: Core AI agent framework
- **Selenium**: Web browser automation
- **BeautifulSoup**: HTML parsing
- **Pandas/NumPy**: Data processing
- **Requests**: HTTP client
- **WebDriver Manager**: Automatic ChromeDriver management

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## License

[Add your license here]

## Disclaimer

This tool is for educational purposes. Please respect Albert Heijn's terms of service and use responsibly. The automated cart functionality should be used with caution and human oversight.

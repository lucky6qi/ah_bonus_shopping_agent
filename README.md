# AH Shopping Agent

A shopping agent for scraping AH.nl bonus products and automating cart operations.

## Features

- 🕷️ Scrape discount products from ah.nl/bonus
- 📊 Product summaries and categorization
- 🤖 AI-powered product categorization
- 🛒 Automated cart operations

## Installation

```bash
# Install dependencies
uv sync

# Or manually
pip install -r requirements.txt
```

## Configuration

Create a `.env` file in the project root:

```bash
ANTHROPIC_API_KEY=your_api_key_here
```

## Usage

### Basic

```bash
uv run python main.py
```

### Programmatic

```python
from config import Config
from scraper import AHBonusScraper
from bucket_generator import BucketGenerator

config = Config.from_env()
scraper = AHBonusScraper(config)

# Scrape products
products = scraper.scrape_bonus_products()

# Generate buckets
generator = BucketGenerator(config.anthropic_api_key)
user_prompt = """Shopping Requirements:
Buy healthy ingredients for a week

Must-buy Items:
必须买2盒1L牛奶 10个鸡蛋 3种打折商品"""
buckets = generator.generate_buckets(
    products=products,
    user_prompt=user_prompt
)

# Add to cart
from cart_automation import add_buckets_to_cart
result = add_buckets_to_cart(buckets)
```

## Requirements

- Python 3.10+
- Chrome browser
- Anthropic API key

## License

MIT

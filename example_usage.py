"""Usage examples"""
import os
import json
from config import Config
from scraper import AHBonusScraper
from bucket_generator import BucketGenerator
from cart_automation import add_to_cart_simple, add_buckets_to_cart


def example_scrape():
    """Scrape products"""
    config = Config()
    scraper = AHBonusScraper(config)
    products = scraper.scrape_bonus_products()
    summary = scraper.summarize_products(products)
    print(summary)


def example_generate_buckets():
    """Scrape and generate buckets"""
    config = Config.from_env()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    
    if not api_key:
        print("⚠️ Need ANTHROPIC_API_KEY")
        return
    
    scraper = AHBonusScraper(config)
    generator = BucketGenerator(api_key)
    
    products = scraper.scrape_bonus_products()
    
    user_prompt = """Shopping Requirements:
Buy healthy ingredients for a week, including meat, vegetables, fruits"""
    
    buckets = generator.generate_buckets(
        products=products,
        user_prompt=user_prompt
    )
    
    print(generator.format_buckets(buckets))


def example_add_to_cart():
    """Add products to cart"""
    products = [
        {"title": "AH Halfvolle melk 1 liter", "product_url": ""},
        {"title": "AH Scharreleieren 10 stuks", "product_url": ""},
        {"title": "AH Bruin brood", "product_url": ""}
    ]
    
    result = add_to_cart_simple(products, headless=False)
    print(f"✅ Added {result.added_count} products")
    if result.failed_products:
        print(f"❌ Failed: {result.failed_products}")


def example_full_workflow():
    """Full workflow: scrape -> generate -> add to cart"""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("⚠️ Need ANTHROPIC_API_KEY")
        return
    
    config = Config()
    scraper = AHBonusScraper(config)
    generator = BucketGenerator(api_key)
    
    # Load from cache or scrape
    products = []
    if os.path.exists(config.products_cache_file):
        with open(config.products_cache_file, 'r', encoding='utf-8') as f:
            products = json.load(f)
        print(f"✅ Loaded {len(products)} products from cache")
    else:
        print("⚠️ Cache not found, scraping...")
        products = scraper.scrape_bonus_products()
    
    # Generate buckets
    user_prompt = """Shopping Requirements:
Buy healthy ingredients for a week, including meat, vegetables, fruits, and essentials"""
    
    buckets = generator.generate_buckets(
        products=products[:100],
        user_prompt=user_prompt
    )
    
    print(generator.format_buckets(buckets))
    
    # Add to cart
    result = add_buckets_to_cart(buckets, headless=False)
    print(f"✅ Complete! {result.message}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "full":
            example_full_workflow()
        elif cmd == "cart":
            example_add_to_cart()
        elif cmd == "buckets":
            example_generate_buckets()
        else:
            example_scrape()
    else:
        example_scrape()

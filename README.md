# AH Shopping Agent

智能购物代理，用于抓取 AH.nl 折扣商品并自动化购物车操作。支持 AI 驱动的商品分类和购物车智能检查。

## ✨ 主要功能

- 🕷️ 抓取 ah.nl/bonus 折扣商品（支持缓存）
- 📦 加载历史购买商品（eerder-gekocht）
- 🤖 AI 智能分类商品（Anthropic Claude API）
- 🛒 自动化购物车操作和智能检查
- 💰 自动监控购物车金额（默认最低 50 欧元）
- 🤖 自动模式（完成后发送邮件通知）

## 📋 系统要求

- Python 3.10+
- Chrome 浏览器
- Anthropic API key

## 🚀 安装

```bash
uv sync
# 或
pip install -r requirements.txt
```

## ⚙️ 配置

创建 `.env` 文件：

```bash
ANTHROPIC_API_KEY=your_api_key_here
AUTO_MODE=false                    # 可选：自动模式
NOTIFICATION_EMAIL=your@email.com # 可选：邮件通知
```

## 📖 使用方法

### 基本使用

```bash
# 交互模式
uv run python main.py

# 自动模式
uv run python main.py --auto
```

### 自定义购物提示

编辑 `prompts/default_prompt.txt`：

```
Shopping Requirements:
Buy healthy ingredients for a week for 2 adults.

Must-buy Items:
必须买2盒1L牛奶 10个鸡蛋 4种肉类，总价格需要高于50。
```

### 编程方式

```python
from config import Config
from scraper import AHBonusScraper
from bucket_generator import BucketGenerator
from cart_automation import CartAutomation
from session_manager import SessionManager

config = Config.from_env()
session_manager = SessionManager(user_data_dir=config.chrome_user_data_dir)
scraper = AHBonusScraper(config, session_manager=session_manager)

# 抓取商品
bonus_products = scraper.scrape_bonus_products(use_selenium=True, use_cache=True)

# AI 分类
generator = BucketGenerator(config.anthropic_api_key)
buckets = generator.generate_buckets(
    bonus_products=bonus_products,
    user_prompt="购买健康食材..."
)

# 添加到购物车
cart = CartAutomation(
    user_data_dir=config.chrome_user_data_dir,
    driver=scraper.get_driver(),
    session_manager=session_manager
)
cart.add_from_buckets(buckets, available_products=bonus_products)
```

## 📝 注意事项

- 首次运行需要手动登录 AH.nl 账户
- 需要有效的 Anthropic API key
- 交互模式会保持浏览器窗口打开

## 📄 License

MIT

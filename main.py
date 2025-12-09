"""Main program entry"""
import os
from config import Config
from scraper import AHBonusScraper
from bucket_generator import BucketGenerator
from cart_automation import CartAutomation, add_buckets_to_cart


def main(auto_mode: bool = False):
    """Main function"""
    mode_text = "🤖 AUTO MODE" if auto_mode else "🛒 AH Shopping Agent"
    print(mode_text)
    print("=" * 50)
    
    # Load configuration
    config = Config.from_env()
    # Override auto_mode if passed as parameter
    if auto_mode:
        config.auto_mode = True
    # ═══════════════════════════════════════════════════════════
    # 🔴 LLM CONFIGURATION - Check for Anthropic API key
    # ═══════════════════════════════════════════════════════════
    if not config.anthropic_api_key:
        config.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        if not config.anthropic_api_key:
            print("⚠️ Warning: ANTHROPIC_API_KEY not set, bucket generation will be unavailable")
    
    # Initialize components
    # 创建共享的SessionManager，以便scraper和cart共享同一个浏览器窗口
    from session_manager import SessionManager
    session_manager = SessionManager(user_data_dir=config.chrome_user_data_dir)
    
    scraper = AHBonusScraper(config, session_manager=session_manager)
    
    # 1. Scrape bonus products and load previously bought products
    print("\n📊 Step 1: Scraping AH.nl/bonus products...")
    bonus_products = scraper.scrape_bonus_products(use_selenium=True, use_cache=True, wait_for_login=not config.auto_mode)
    
    if not bonus_products:
        print("❌ No bonus products found, exiting")
        return
    
    # Load previously bought products (eerder-gekocht) from JSON file
    previously_buy_products = []
    try:
        import json
        if os.path.exists(config.eerder_gekocht_file):
            with open(config.eerder_gekocht_file, 'r', encoding='utf-8') as f:
                eerder_data = json.load(f)
                if isinstance(eerder_data, dict) and 'products' in eerder_data:
                    previously_buy_products = eerder_data['products']
                    print(f"✅ 加载了 {len(previously_buy_products)} 个previously bought产品")
                elif isinstance(eerder_data, list):
                    previously_buy_products = eerder_data
                    print(f"✅ 加载了 {len(previously_buy_products)} 个previously bought产品")
                
                # 验证source字段
                if previously_buy_products:
                    products_with_source = [p for p in previously_buy_products if p.get('source') == 'eerder-gekocht']
                    products_without_source = [p for p in previously_buy_products if not p.get('source')]
                    if products_without_source:
                        print(f"⚠️  发现 {len(products_without_source)} 个previously bought产品缺少source字段，将自动添加")
                        for p in products_without_source:
                            p['source'] = 'eerder-gekocht'
                    print(f"📊 Previously bought产品统计: {len(products_with_source)} 个有source字段")
        else:
            print(f"ℹ️  {config.eerder_gekocht_file} 不存在，跳过previously bought产品")
    except Exception as e:
        print(f"⚠️ 加载previously bought产品失败: {e}")
        import traceback
        traceback.print_exc()
    
    # Combine products for summary (bonus products first)
    all_products = bonus_products + previously_buy_products
    print(f"📦 总共 {len(bonus_products)} 个bonus产品 + {len(previously_buy_products)} 个previously bought产品 = {len(all_products)} 个产品")
    
    # Save products to cache
    try:
        import json
        with open(config.products_cache_file, 'w', encoding='utf-8') as f:
            json.dump(all_products, f, ensure_ascii=False, indent=2)
        print(f"✅ Product data cached to {config.products_cache_file}")
    except:
        pass
    
    # 2. Summarize product information
    print("\n📝 Step 2: Generating product summary...")
    summary = scraper.summarize_products(all_products)
    print(summary)
    
    # 3. Generate base bucket
    # ═══════════════════════════════════════════════════════════
    # 🔴 LLM USAGE - Generate intelligent product buckets
    # ═══════════════════════════════════════════════════════════
    if config.anthropic_api_key:
        print("\n🤖 Step 4: Generating base bucket based on base_prompt...")
        # LLM initialization - creates Anthropic Claude client
        generator = BucketGenerator(config.anthropic_api_key)
        
        # Get user prompt (can be from file or direct input)
        prompt_file = "prompts/default_prompt.txt"
        user_prompt = ""
        
        # Try to load from file first
        if os.path.exists(prompt_file):
            try:
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    user_prompt = f.read().strip()
                print(f"\n📝 Loaded prompt from {prompt_file}")
                print(f"Prompt content:\n{user_prompt}\n")
            except Exception as e:
                print(f"⚠️ Failed to load prompt file: {e}")
        
        # If no file or file is empty, use default or ask for input (unless auto_mode)
        if not user_prompt:
            if config.auto_mode:
                # Auto mode: use default prompt
                user_prompt = """Shopping Requirements:
Buy healthy ingredients for a week, including meat, vegetables, fruits, and essentials.

Must-buy Items:
"""
            else:
                print("\nEnter shopping prompt (or press ENTER for default):")
                print("You can include:")
                print("  - Shopping Requirements: ...")
                print("  - Must-buy Items: ...")
                print("Or just type your requirements directly")
                user_input = input("> ").strip()
                if user_input:
                    user_prompt = user_input
                else:
                    # Default prompt
                    user_prompt = """Shopping Requirements:
Buy healthy ingredients for a week, including meat, vegetables, fruits, and essentials.

Must-buy Items:
"""
        
        # LLM API call - uses Claude to categorize products intelligently
        # Pass both bonus products (priority) and previously bought products
        buckets = generator.generate_buckets(
            bonus_products=bonus_products,
            previously_buy_products=previously_buy_products,
            user_prompt=user_prompt
        )
        
        print("\n" + generator.format_buckets(buckets))
        
        # 5. Check current cart and validate with LLM
        print("\n🛒 Step 5: Checking current cart...")
        # 复用scraper的driver和session_manager，使用同一个浏览器窗口
        cart = CartAutomation(
            user_data_dir=config.chrome_user_data_dir,
            login_timeout=config.login_timeout,
            driver=scraper.get_driver(),  # 复用scraper的浏览器窗口
            session_manager=session_manager,  # 共享SessionManager
            eerder_gekocht_file=config.eerder_gekocht_file  # 传入 eerder-gekocht 文件路径
        )
        
        try:
            # 先从购物车按钮读取总金额
            print("\n🛒 Step 5: Checking current cart...")
            cart_total = cart.get_cart_total_amount()
            
            if cart_total == 0.0:
                # 如果金额为0，购物车为空，直接添加商品，不需要LLM检查
                print(f"💰 购物车总金额: €0.00")
                print("📦 购物车为空，直接添加商品...")
                # 传入所有可用产品（bonus + eerder-gekocht），以便匹配时能同时搜索两个数据源
                result = cart.add_from_buckets(buckets, available_products=all_products)
                
                # 检查总金额是否超过50欧元
                min_total_amount = 50.0
                final_total = cart.get_cart_total_amount()
                print(f"\n💰 购物车总金额: €{final_total:.2f}")
                if final_total < min_total_amount:
                    print(f"⚠️  购物车总金额 €{final_total:.2f} 未达到最低要求 €{min_total_amount:.2f}")
                    print("💡 提示：如果需要达到最低金额，可以手动添加更多商品或重新运行程序")
                else:
                    print(f"✅ 购物车总金额 €{final_total:.2f} 已达到最低要求 €{min_total_amount:.2f}")
            else:
                # 如果金额不为0，必须进行LLM检查
                print(f"💰 购物车总金额: €{cart_total:.2f}")
                
                # 抓取购物车内容
                cart_products = cart.scrape_cart_content()
                
                if cart_products:
                    print(f"📦 当前购物车中有 {len(cart_products)} 种商品")
                else:
                    print("⚠️ 无法抓取购物车商品列表，但购物车不为空")
                    # 即使无法抓取商品列表，也创建一个空列表进行LLM检查
                    cart_products = []
                
                # 必须进行LLM检查（只检查一次）
                print("\n🤖 使用LLM检查购物车是否满足要求...")
                cart_check = generator.check_cart_with_llm(
                    cart_products=cart_products,
                    user_requirements=user_prompt,
                    available_products=all_products  # 传入可用产品列表（bonus + previously bought），让LLM选择需要添加的产品
                )
                
                print(f"\n📊 购物车检查结果:")
                print(f"   满足要求: {'✅ 是' if cart_check.get('satisfied') else '❌ 否'}")
                
                if cart_check.get('missing_items'):
                    print(f"\n   缺少的商品:")
                    for item in cart_check['missing_items']:
                        print(f"     - {item}")
                
                if cart_check.get('suggestions'):
                    print(f"\n   建议添加:")
                    for suggestion in cart_check['suggestions']:
                        print(f"     - {suggestion}")
                
                if cart_check.get('analysis'):
                    print(f"\n   分析说明:")
                    print(f"     {cart_check['analysis']}")
                
                # 如果购物车满足要求，跳过添加步骤
                if cart_check.get('satisfied'):
                    print("\n✅ 购物车已满足要求，跳过添加步骤")
                else:
                    # 如果购物车不满足要求，添加缺失的商品（使用force_add=True强制添加）
                    # 循环添加商品，直到总金额超过50欧元或达到最大尝试次数
                    max_attempts = 3
                    attempt = 0
                    min_total_amount = 50.0  # 最小总金额要求
                    
                    while attempt < max_attempts:
                        attempt += 1
                        products_to_add = cart_check.get('products_to_add', [])
                        
                        if products_to_add:
                            # 显示LLM生成的购物清单
                            print("\n" + generator.format_products_to_add(products_to_add))
                            print(f"\n🛒 开始添加缺失的商品 ({len(products_to_add)} 个)... [尝试 {attempt}/{max_attempts}]")
                            # 使用force_add=True强制添加，即使购物车已有其他商品
                            # 传入所有可用产品（bonus + eerder-gekocht），以便匹配时能同时搜索两个数据源
                            add_result = cart.add_products(products_to_add, force_add=True, available_products=all_products)
                            if add_result.success:
                                print(f"✅ 成功添加 {add_result.added_count} 个商品")
                            
                            # 检查总金额是否超过50欧元
                            current_total = cart.get_cart_total_amount()
                            print(f"\n💰 当前购物车总金额: €{current_total:.2f}")
                            
                            if current_total >= min_total_amount:
                                print(f"✅ 购物车总金额已达到 €{current_total:.2f}，超过最低要求 €{min_total_amount:.2f}")
                                break
                            else:
                                remaining = min_total_amount - current_total
                                print(f"⚠️  购物车总金额 €{current_total:.2f} 未达到最低要求 €{min_total_amount:.2f}，还需 €{remaining:.2f}")
                                
                                if attempt < max_attempts:
                                    print(f"\n🔄 继续添加商品以达到最低金额要求...")
                                    # 重新检查购物车并获取更多需要添加的商品
                                    cart_products = cart.scrape_cart_content()
                                    cart_check = generator.check_cart_with_llm(
                                        cart_products=cart_products,
                                        user_requirements=user_prompt,
                                        available_products=all_products
                                    )
                                    # 如果LLM认为已满足要求，但金额仍不足，强制添加更多商品
                                    if cart_check.get('satisfied'):
                                        print("⚠️  LLM认为已满足要求，但金额不足，使用buckets添加更多商品...")
                                        result = cart.add_from_buckets(buckets, available_products=all_products)
                                        current_total = cart.get_cart_total_amount()
                                        if current_total >= min_total_amount:
                                            break
                        else:
                            # 如果没有products_to_add，使用buckets添加
                            print("\n🛒 使用buckets添加商品...")
                            # 传入所有可用产品（bonus + eerder-gekocht），以便匹配时能同时搜索两个数据源
                            result = cart.add_from_buckets(buckets, available_products=all_products)
                            current_total = cart.get_cart_total_amount()
                            if current_total >= min_total_amount:
                                break
                    
                    # 最终检查总金额
                    final_total = cart.get_cart_total_amount()
                    print(f"\n💰 最终购物车总金额: €{final_total:.2f}")
                    if final_total < min_total_amount:
                        print(f"⚠️  警告：购物车总金额 €{final_total:.2f} 未达到最低要求 €{min_total_amount:.2f}")
                    else:
                        print(f"✅ 购物车总金额 €{final_total:.2f} 已达到最低要求 €{min_total_amount:.2f}")
            
            # 统一显示购物车并结束
            cart.view_cart()
            
            if config.auto_mode:
                # Auto mode: close browser and send email notification
                print("\n🤖 自动模式：关闭浏览器...")
                try:
                    cart.close()
                except:
                    pass
                
                # Send email notification
                if config.notification_email:
                    from email_notifier import EmailNotifier
                    notifier = EmailNotifier()
                    notifier.send_shopping_complete_notification(config.notification_email)
                else:
                    print("⚠️ 未配置NOTIFICATION_EMAIL，跳过邮件通知")
                
                print("\n✅ 自动模式完成！")
            else:
                print("\n💡 Browser will remain open for you to review and checkout")
                print("   Please manually close the browser when done")
                print(f"   💾 登录状态和cookies已保存，下次运行会自动使用")
                
                # Delete cache file completely after adding to cart
                scraper.delete_cache()
                
                # 不等待用户输入，直接完成（浏览器保持打开）
                print("\n✅ 程序完成！浏览器窗口保持打开，您可以继续使用。")
                print("   要关闭浏览器，请手动关闭窗口。")
        finally:
            # 不关闭浏览器，保持打开供用户使用
            # cart.close()  # 已注释，不关闭浏览器
            # 确保driver不会被关闭
            if scraper.get_driver():
                print("\n💡 浏览器窗口保持打开，请手动关闭")
            pass
    else:
        print("\n⚠️ Skipping bucket generation (ANTHROPIC_API_KEY required)")
    
    # 程序完成，但不退出，保持浏览器打开
    print("\n✅ 程序完成！浏览器窗口保持打开，您可以继续使用。")
    print("   要关闭浏览器，请手动关闭窗口。")
    print("   按 Ctrl+C 退出程序（浏览器窗口仍会保持打开）")
    
    # 保持程序运行，防止自动退出导致浏览器关闭
    try:
        import signal
        import sys
        def signal_handler(sig, frame):
            print("\n\n程序已停止，但浏览器窗口保持打开")
            sys.exit(0)
        signal.signal(signal.SIGINT, signal_handler)
        
        # 保持driver引用，防止被垃圾回收导致浏览器关闭
        _driver_keepalive = scraper.get_driver() if hasattr(scraper, 'get_driver') else None
        _cart_keepalive = cart if 'cart' in locals() else None
        
        # 等待用户中断，但不关闭浏览器
        print("\n⏸️  程序等待中... (按 Ctrl+C 退出，浏览器窗口保持打开)")
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n程序已停止，但浏览器窗口保持打开")
        pass


if __name__ == "__main__":
    import sys
    # Check if auto_mode flag is passed
    auto_mode = "--auto" in sys.argv or os.getenv("AUTO_MODE", "false").lower() == "true"
    main(auto_mode=auto_mode)

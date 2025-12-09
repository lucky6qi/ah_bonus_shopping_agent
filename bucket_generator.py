"""Generate base bucket based on base_prompt"""
import anthropic
from typing import List, Dict, Any, Optional
import json


class BucketGenerator:
    """Generate shopping list bucket classification based on prompts"""
    
    def __init__(self, api_key: str):
        # ═══════════════════════════════════════════════════════════
        # 🔴 LLM INITIALIZATION - Anthropic Claude API
        # ═══════════════════════════════════════════════════════════
        self.client = anthropic.Anthropic(api_key=api_key)
        
        # ═══════════════════════════════════════════════════════════
        # 🔴 LLM PROMPT - Base prompt for product categorization
        # ═══════════════════════════════════════════════════════════
        self.base_prompt = """You are an intelligent shopping assistant. Please categorize products into different buckets based on user shopping requirements.

Bucket classification rules:
1. Essentials (essentials) - Daily essential basic products, such as milk, eggs, bread, etc.
2. Meat (meat) - Various meats and proteins
3. Vegetables (vegetables) - Fresh vegetables
4. Fruit (fruit) - Fresh fruits
5. Snacks (snacks) - Snacks, sweets, etc.
6. Beverages (beverages) - Various drinks
7. Other (other) - Other products

PRODUCT SELECTION PRIORITY RULES:
- ALWAYS prioritize BONUS products (discount products) first when selecting products
- Only use PREVIOUSLY BOUGHT products if:
  1. The required product is NOT available in bonus products, OR
  2. The bonus product doesn't match the user's specific requirements (e.g., size, brand, type)
- When both sources have similar products, prefer the bonus product for better value
- Match product names exactly as they appear in the product lists

Please generate reasonable product lists for each bucket based on user requirements and available product information."""
    
    def generate_buckets(self, bonus_products: List[Dict[str, Any]], 
                        previously_buy_products: List[Dict[str, Any]] = None,
                        user_prompt: str = "") -> Dict[str, List[Dict[str, Any]]]:
        """Generate base bucket
        
        Args:
            bonus_products: List of bonus (discount) products - HIGH PRIORITY
            previously_buy_products: List of previously bought products - FALLBACK ONLY
            user_prompt: Combined shopping prompt (can include requirements and must-buy items)
        """
        if previously_buy_products is None:
            previously_buy_products = []
        
        # Combine all products for product lookup (bonus first, then previously bought)
        all_products = bonus_products + previously_buy_products
        
        # Prepare bonus products list (priority source)
        bonus_products_text = "\n".join([
            f"- {p['title']} | {p['price']} | Discount: {p.get('discount', 0)}% | Source: BONUS"
            for p in bonus_products[:100]  # Limit quantity for efficiency
        ])
        
        # Prepare previously bought products list (fallback source)
        previously_buy_products_text = ""
        if previously_buy_products:
            previously_buy_products_text = "\n".join([
                f"- {p['title']} | {p['price']} | Discount: {p.get('discount', 0)}% | Source: PREVIOUSLY_BOUGHT"
                for p in previously_buy_products[:100]  # Limit quantity for efficiency
            ])
        
        # Parse user prompt to extract requirements and must-buy items
        user_requirements = ""
        must_buy_items = ""
        
        if user_prompt:
            # Try to parse structured format (Shopping Requirements: ... Must-buy Items: ...)
            if "Shopping Requirements:" in user_prompt or "Must-buy Items:" in user_prompt:
                lines = user_prompt.split('\n')
                current_section = None
                requirements_lines = []
                must_buy_lines = []
                
                for line in lines:
                    if "Shopping Requirements:" in line:
                        current_section = "requirements"
                        req_text = line.split("Shopping Requirements:", 1)[1].strip()
                        if req_text:
                            requirements_lines.append(req_text)
                    elif "Must-buy Items:" in line:
                        current_section = "must_buy"
                        must_text = line.split("Must-buy Items:", 1)[1].strip()
                        if must_text:
                            must_buy_lines.append(must_text)
                    elif current_section == "requirements" and line.strip():
                        requirements_lines.append(line.strip())
                    elif current_section == "must_buy" and line.strip():
                        must_buy_lines.append(line.strip())
                
                user_requirements = "\n".join(requirements_lines) if requirements_lines else ""
                must_buy_items = "\n".join(must_buy_lines) if must_buy_lines else ""
            else:
                # If no structured format, treat entire prompt as requirements
                user_requirements = user_prompt
        
        # Build user prompt section
        user_prompt_section = ""
        if must_buy_items:
            user_prompt_section = f"""
IMPORTANT - Must-buy items:
{must_buy_items}

You MUST include these items in the shopping list. Match the quantities and specifications as closely as possible from the available products.
"""
        
        # Build previously bought products section (avoid nested f-string with backslash)
        previously_buy_section = ""
        if previously_buy_products_text:
            previously_buy_section = f"=== PREVIOUSLY BOUGHT PRODUCTS (FALLBACK ONLY - Use only if not found in bonus products) ===\n{previously_buy_products_text}\n"
        
        # Build complete prompt
        prompt = f"""{self.base_prompt}

=== BONUS PRODUCTS (HIGH PRIORITY - Use these first) ===
{bonus_products_text}

{previously_buy_section}User requirements:
{user_requirements or "Buy healthy ingredients for a week, including meat, vegetables, fruits, and essentials"}

{user_prompt_section}

PRODUCT SELECTION INSTRUCTIONS:
1. FIRST search in BONUS PRODUCTS list - these have discounts and should be prioritized
2. ONLY if a product is NOT found in bonus products, then search in PREVIOUSLY BOUGHT PRODUCTS
3. When selecting products, prefer bonus products even if previously bought products have similar items
4. Match product names EXACTLY as they appear in the product lists above

IMPORTANT LANGUAGE REQUIREMENT:
- ALL product titles in the output MUST be in DUTCH (Nederlands)
- Match product names from the available products list exactly as they appear
- If translating from user requirements, use proper Dutch product names
- Example: "milk" → "AH Halfvolle Melk", "eggs" → "AH Scharreleieren", "bread" → "AH Volkoren Brood"

Please select appropriate products for each bucket, maximum 10 products per bucket. 
IMPORTANT: If user_prompt is provided, you MUST include those items first.
Return JSON format:
{{
  "essentials": [{{"title": "Product name in Dutch", "price": "Price", "quantity": 1, "reason": "Selection reason"}}],
  "meat": [...],
  "vegetables": [...],
  "fruit": [...],
  "snacks": [...],
  "beverages": [...],
  "other": [...]
}}"""
        
        try:
            # ═══════════════════════════════════════════════════════════
            # 🔴 LLM API CALL - Claude 3.5 Sonnet
            # ═══════════════════════════════════════════════════════════
            # This is where the LLM is called to generate intelligent bucket classification
            message = self.client.messages.create(
                model="claude-haiku-4-5",  # LLM Model
                max_tokens=4000,
                messages=[{
                    "role": "user",
                    "content": prompt  # LLM Prompt with products and requirements
                }]
            )
            
            # Parse response
            response_text = message.content[0].text
            
            # Print raw LLM response for debugging
            print("\n" + "=" * 50)
            print("🤖 LLM Raw Response (generate_buckets):")
            print("=" * 50)
            print(response_text)
            print("=" * 50 + "\n")
            
            # Try to extract JSON
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                buckets = json.loads(json_str)
                
                # Convert to product dictionary format
                result = {}
                for bucket_name, items in buckets.items():
                    result[bucket_name] = []
                    # Ensure items is a list
                    if not isinstance(items, list):
                        continue
                    for item in items:
                        # Skip if item is not a dictionary (could be string or other type)
                        if not isinstance(item, dict):
                            # If item is a string, try to find product by title
                            if isinstance(item, str):
                                product = self._find_product(all_products, item)
                                if product:
                                    result[bucket_name].append({
                                        **product,
                                        "quantity": product.get("promotion_quantity", 1),
                                        "reason": "Auto-matched from LLM response"
                                    })
                            continue
                        # Find complete information from products (search in all products, but prioritize bonus)
                        product = self._find_product(all_products, item.get("title", ""))
                        if product:
                            product_copy = {
                                **product,
                                "reason": item.get("reason", "")
                            }
                            # Priority: user-specified quantity > promotion_quantity > 1
                            if "quantity" in item:
                                product_copy["quantity"] = item["quantity"]
                            elif product.get("promotion_quantity", 1) > 1:
                                # Use promotion quantity if no user-specified quantity
                                product_copy["quantity"] = product.get("promotion_quantity", 1)
                            result[bucket_name].append(product_copy)
                
                return result
            else:
                print("⚠️ Unable to parse AI response as JSON format")
                return self._create_default_buckets(all_products)
                
        except Exception as e:
            print(f"❌ Failed to generate bucket: {e}")
            return self._create_default_buckets(all_products)
    
    def _find_product(self, products: List[Dict[str, Any]], title: str) -> Dict[str, Any]:
        """Find matching product in product list"""
        title_lower = title.lower()
        for product in products:
            if title_lower in product["title"].lower() or product["title"].lower() in title_lower:
                return product
        return None
    
    def _create_default_buckets(self, products: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Create default bucket classification"""
        buckets = {
            "essentials": [],
            "meat": [],
            "vegetables": [],
            "fruit": [],
            "snacks": [],
            "beverages": [],
            "other": []
        }
        
        # Simple keyword classification
        keywords = {
            "essentials": ["melk", "milk", "eieren", "eggs", "brood", "bread", "boter", "butter"],
            "meat": ["vlees", "meat", "kip", "chicken", "vis", "fish", "gehakt"],
            "vegetables": ["groente", "vegetable", "tomaat", "tomato", "ui", "onion", "wortel"],
            "fruit": ["fruit", "appel", "apple", "banaan", "banana", "sinaasappel"],
            "snacks": ["snack", "chips", "koek", "snoep", "chocolate"],
            "beverages": ["drank", "drink", "sap", "juice", "water", "cola"]
        }
        
        for product in products:
            title_lower = product["title"].lower()
            categorized = False
            
            for bucket, kw_list in keywords.items():
                if any(kw in title_lower for kw in kw_list):
                    if len(buckets[bucket]) < 10:
                        buckets[bucket].append(product)
                        categorized = True
                        break
            
            if not categorized and len(buckets["other"]) < 10:
                buckets["other"].append(product)
        
        return buckets
    
    def format_buckets(self, buckets: Dict[str, List[Dict[str, Any]]]) -> str:
        """Format bucket output"""
        result = "🛒 Shopping List Classification (Base Buckets)\n"
        result += "=" * 50 + "\n\n"
        
        bucket_names = {
            "essentials": "Essentials",
            "meat": "Meat",
            "vegetables": "Vegetables",
            "fruit": "Fruit",
            "snacks": "Snacks",
            "beverages": "Beverages",
            "other": "Other"
        }
        
        for bucket_name, items in buckets.items():
            display_name = bucket_names.get(bucket_name, bucket_name)
            result += f"📦 {display_name} ({len(items)} items):\n"
            
            for item in items:
                quantity = item.get("quantity", 1)
                quantity_text = f" x{quantity}" if quantity > 1 else ""
                result += f"   - {item['title']}{quantity_text} | {item['price']}\n"
                if item.get("reason"):
                    result += f"     Reason: {item['reason']}\n"
            
            result += "\n"
        
        return result
    
    def format_products_to_add(self, products: List[Dict[str, Any]]) -> str:
        """Format products to add list (from cart check)"""
        if not products:
            return "📋 没有需要添加的商品\n"
        
        result = "🛒 Products to Add (from Cart Check)\n"
        result += "=" * 50 + "\n\n"
        
        for i, product in enumerate(products, 1):
            title = product.get('title', 'Unknown')
            price = product.get('price', product.get('current_price', 'Unknown'))
            quantity = product.get('quantity', 1)
            reason = product.get('reason', '')
            source = product.get('source', '')
            
            quantity_text = f" x{quantity}" if quantity > 1 else ""
            result += f"{i}. {title}{quantity_text} | {price}\n"
            
            if reason:
                result += f"   Reason: {reason}\n"
            if source:
                result += f"   Source: {source}\n"
            result += "\n"
        
        result += f"总计: {len(products)} 个商品\n"
        return result
    
    def check_cart_with_llm(self, cart_products: List[Dict[str, Any]], 
                           user_requirements: str = "",
                           available_products: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        使用LLM检查购物车是否满足用户要求，并返回需要添加的具体产品
        
        Args:
            cart_products: 购物车中的产品列表
            user_requirements: 用户购物要求
            available_products: 可选，可用的产品列表（用于匹配需要添加的产品）
            
        Returns:
            包含检查结果的字典，格式：
            {
                "satisfied": bool,  # 是否满足要求
                "missing_items": List[str],  # 缺少的商品类别或项目
                "suggestions": List[str],  # 建议添加的商品
                "products_to_add": List[Dict],  # 需要添加的具体产品信息
                "analysis": str  # LLM的分析说明
            }
        """
        if not cart_products:
            return {
                "satisfied": False,
                "missing_items": ["购物车为空"],
                "suggestions": [],
                "products_to_add": [],
                "analysis": "购物车为空，需要添加商品"
            }
        
        # 准备购物车产品文本
        cart_text = "\n".join([
            f"- {p.get('title', 'Unknown')} | {p.get('price', 'Unknown')} | Quantity: {p.get('quantity', 1)}"
            for p in cart_products
        ])
        
        # 准备可用产品文本（如果提供），区分bonus和previously bought产品
        available_products_text = ""
        if available_products:
            # 分离bonus和previously bought产品
            bonus_products_list = [p for p in available_products if p.get('source') == 'bonus']
            previously_buy_products_list = [p for p in available_products if p.get('source') == 'eerder-gekocht' or p.get('source') == 'previously-bought']
            
            # 调试信息：打印产品数量
            print(f"🔍 产品分类: {len(bonus_products_list)} 个bonus产品, {len(previously_buy_products_list)} 个previously bought产品")
            
            available_products_text = "\n\n=== BONUS产品（高优先级，优先选择）===\n"
            if bonus_products_list:
                available_products_text += f"共 {len(bonus_products_list)} 个BONUS产品（有折扣优惠）\n"
                available_products_text += "格式：产品名称 | 价格 | 折扣 | product_url\n"
                available_products_text += "\n".join([
                    f"- {p.get('title', 'Unknown')} | {p.get('price', 'Unknown')} | Discount: {p.get('discount', 0)}% | URL: {p.get('product_url', '') or '(无URL)'}"
                    for p in bonus_products_list[:150]  # 增加显示数量
                ])
            else:
                available_products_text += "(无bonus产品)\n"
            
            if previously_buy_products_list:
                available_products_text += f"\n\n=== PREVIOUSLY BOUGHT产品（备选，仅在bonus中找不到时使用）===\n"
                available_products_text += f"共 {len(previously_buy_products_list)} 个PREVIOUSLY BOUGHT产品（用户之前购买过的产品）\n"
                available_products_text += "格式：产品名称 | 价格 | 折扣 | product_url\n"
                available_products_text += "\n".join([
                    f"- {p.get('title', 'Unknown')} | {p.get('price', 'Unknown')} | Discount: {p.get('discount', 0)}% | URL: {p.get('product_url', '') or '(无URL)'}"
                    for p in previously_buy_products_list[:150]  # 增加显示数量
                ])
            else:
                # 检查是否有产品但没有source字段
                products_without_source = [p for p in available_products if not p.get('source')]
                if products_without_source:
                    print(f"⚠️  发现 {len(products_without_source)} 个产品没有source字段，将作为previously bought产品处理")
                    available_products_text += f"\n\n=== PREVIOUSLY BOUGHT产品（备选，仅在bonus中找不到时使用）===\n"
                    available_products_text += f"共 {len(products_without_source)} 个产品（无source字段，视为previously bought）\n"
                    available_products_text += "\n".join([
                        f"- {p.get('title', 'Unknown')} | {p.get('price', 'Unknown')} | {p.get('product_url', '')}"
                        for p in products_without_source[:150]
                    ])
                else:
                    # 明确告知LLM没有previously bought产品
                    available_products_text += "\n\n=== PREVIOUSLY BOUGHT产品（备选，仅在bonus中找不到时使用）===\n"
                    available_products_text += "(当前没有PREVIOUSLY BOUGHT产品可用)\n"
        
        # 构建prompt
        prompt = f"""你是一个智能购物助手。请检查当前购物车是否满足用户的购物要求，并给出需要添加的具体产品。

当前购物车中的商品：
{cart_text}

用户购物要求：
{user_requirements or "购买健康的一周食材，包括肉类、蔬菜、水果和必需品"}
{available_products_text}

请分析：
1. 购物车是否满足用户的基本要求？
2. 购物车总金额是否超过50欧元？如果未超过，必须添加更多商品以达到或超过50欧元。
3. 缺少哪些重要的商品类别或项目？
4. 需要添加哪些具体商品？请从可用产品列表中选择匹配的产品。

**重要：总金额要求**
- 如果用户要求中提到总价格需要高于50欧元（或类似要求），你必须确保添加的商品足够多，使得购物车总金额达到或超过50欧元
- 在计算需要添加的商品时，要考虑当前购物车金额和待添加商品的价格
- 如果当前金额+待添加商品金额仍不足50欧元，必须继续添加更多商品

**产品选择规则（必须严格遵守）：**
- 第一步：在BONUS产品列表中搜索匹配的产品（优先选择有折扣的产品）
- 第二步：如果在BONUS产品列表中找不到匹配的产品，必须在PREVIOUSLY BOUGHT产品列表中搜索
- 第三步：如果两个列表中都找不到，才建议搜索其他产品
- 重要：如果用户要求的产品（如"牛奶"、"鸡蛋"、"面包"）在BONUS列表中找不到，你必须查看PREVIOUSLY BOUGHT产品列表，不要直接说"找不到"或"建议在超市查询"

请以JSON格式返回分析结果：
{{
    "satisfied": true/false,
    "missing_items": ["缺少的商品类别或项目"],
    "suggestions": ["建议添加的商品名称"],
            "products_to_add": [
                {{
                    "title": "产品名称（必须是荷兰语，必须与可用产品列表中的名称完全匹配）",
                    "product_url": "产品的完整URL（必须从可用产品列表中复制，如果产品没有URL则留空）",
                    "quantity": 数量,
                    "reason": "添加原因（说明是从BONUS还是PREVIOUSLY BOUGHT列表中选择的）"
                }}
            ],
    "analysis": "详细的分析说明（必须说明是否检查了PREVIOUSLY BOUGHT产品列表）"
}}

重要规则（必须严格遵守）：
1. PRODUCT SELECTION PRIORITY: 
   - 必须优先从BONUS产品列表中选择产品
   - 如果在BONUS产品中找不到匹配的产品，必须从PREVIOUSLY BOUGHT产品列表中选择
   - 不要跳过PREVIOUSLY BOUGHT产品列表，必须检查两个列表
2. PRODUCT_URL字段（非常重要）：
   - products_to_add中的每个产品必须包含product_url字段
   - product_url必须从可用产品列表中对应产品的URL字段复制（格式：URL: xxx）
   - 如果产品没有URL（显示为"(无URL)"），则product_url字段留空字符串""
   - 不要自己构造URL，必须使用列表中提供的URL
3. 如果提供了可用产品列表，products_to_add中的title必须与可用产品列表中的产品名称完全匹配或高度相似
4. 所有产品名称必须是荷兰语（Nederlands）
5. 在analysis字段中，必须明确说明：
   - 哪些产品来自BONUS列表
   - 哪些产品来自PREVIOUSLY BOUGHT列表
   - 如果某个产品在两个列表中都没有找到，才建议搜索其他来源"""
        
        try:
            message = self.client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=4000,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            response_text = message.content[0].text
            
            # Print raw LLM response for debugging
            print("\n" + "=" * 50)
            print("🤖 LLM Raw Response (check_cart_with_llm):")
            print("=" * 50)
            print(response_text)
            print("=" * 50 + "\n")
            
            # 提取JSON
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                result = json.loads(json_str)
                
                # 如果提供了可用产品列表，处理产品信息
                if available_products and result.get('products_to_add'):
                    matched_products = []
                    for item in result['products_to_add']:
                        title = item.get('title', '')
                        product_url = item.get('product_url', '').strip()
                        
                        # 优先使用LLM返回的product_url
                        if product_url:
                            # LLM已经提供了URL，直接使用
                            # 尝试通过URL或标题从可用产品中找到完整信息
                            matched = None
                            # 先尝试通过URL精确匹配
                            for p in available_products:
                                p_url = p.get('product_url', '').strip()
                                if p_url and p_url == product_url:
                                    matched = p
                                    break
                            # 如果URL匹配失败，尝试通过标题匹配
                            if not matched:
                                matched = self._find_product(available_products, title)
                            
                            if matched:
                                product_copy = {
                                    **matched,
                                    "product_url": product_url,  # 使用LLM提供的URL（确保覆盖）
                                    "quantity": item.get('quantity', 1),
                                    "reason": item.get('reason', '')
                                }
                            else:
                                # 如果找不到匹配，使用LLM提供的信息
                                product_copy = {
                                    "title": title,
                                    "product_url": product_url,
                                    "quantity": item.get('quantity', 1),
                                    "reason": item.get('reason', ''),
                                    "price": "Unknown"
                                }
                            matched_products.append(product_copy)
                        else:
                            # LLM没有提供URL，回退到匹配查找
                            matched = self._find_product(available_products, title)
                            if matched:
                                product_copy = {
                                    **matched,
                                    "quantity": item.get('quantity', 1),
                                    "reason": item.get('reason', '')
                                }
                                matched_products.append(product_copy)
                            else:
                                # 如果没找到匹配，创建一个基本产品信息
                                matched_products.append({
                                    "title": title,
                                    "quantity": item.get('quantity', 1),
                                    "reason": item.get('reason', ''),
                                    "price": "Unknown",
                                    "product_url": ""
                                })
                    result['products_to_add'] = matched_products
                
                return result
            else:
                # 如果无法解析JSON，返回基本分析
                return {
                    "satisfied": False,
                    "missing_items": [],
                    "suggestions": [],
                    "products_to_add": [],
                    "analysis": response_text[:500]  # 返回前500字符
                }
        except Exception as e:
            print(f"⚠️ LLM检查购物车时出错: {e}")
            return {
                "satisfied": False,
                "missing_items": [],
                "suggestions": [],
                "products_to_add": [],
                "analysis": f"检查失败: {str(e)}"
            }
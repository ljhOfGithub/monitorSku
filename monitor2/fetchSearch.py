# from playwright.sync_api import sync_playwright
# import time
# import re
# import json
# from datetime import datetime

# def test_cookies_with_playwright(search_url, cookies_dict):
#     """使用cookies测试访问京东页面"""
#     with sync_playwright() as p:
#         browser = p.chromium.launch(headless=True)
        
#         # 创建上下文并设置cookies
#         context = browser.new_context(
#             user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
#             viewport={'width': 1920, 'height': 1080}
#         )
        
#         # 添加cookies到上下文
#         context.add_cookies([
#             {
#                 'name': 'pt_pin',
#                 'value': cookies_dict['pt_pin'],
#                 'domain': '.jd.com',
#                 'path': '/'
#             },
#             {
#                 'name': 'pt_key',
#                 'value': cookies_dict['pt_key'],
#                 'domain': '.jd.com',
#                 'path': '/'
#             },
#             {
#                 'name': 'pt_token',
#                 'value': cookies_dict.get('pt_token', ''),
#                 'domain': '.jd.com',
#                 'path': '/'
#             }
#         ])
        
#         page = context.new_page()
        
#         try:
#             print(f"🧪 正在测试cookies访问: {search_url}")
            
#             # 监听网络请求
#             page.on("response", lambda response: 
#                 print(f"📡 响应: {response.status} - {response.url}") 
#                 if response.status != 200 else None)
            
#             # 访问页面
#             page.goto(search_url, timeout=60000, wait_until='networkidle')
            
#             # 等待页面加载
#             page.wait_for_timeout(5000)
            
#             # 检查页面标题和内容
#             page_title = page.title()
#             print(f"📄 页面标题: {page_title}")
            
#             # 获取完整的HTML内容
#             html_content = page.content()
            
#             # 保存HTML到文件
#             timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#             filename = f"jd_test_result_{timestamp}.html"
#             with open(filename, 'w', encoding='utf-8') as f:
#                 f.write(html_content)
#             print(f"💾 HTML已保存到: {filename}")
            
#             # 检查是否成功获取商品数据
#             if 'jSubObject' in html_content or 'jSearchList' in html_content:
#                 print("✅ 成功获取商品列表数据！")
#             else:
#                 print("❌ 可能未获取到商品数据")
                
#             # 检查是否有登录提示
#             if '登录' in html_content or 'login' in html_content.lower():
#                 print("⚠️  页面可能包含登录提示")
            
#             # 打印页面关键信息
#             print("\n🔍 页面关键信息:")
#             print(f"   页面URL: {page.url}")
#             print(f"   页面标题: {page_title}")
#             print(f"   HTML长度: {len(html_content)} 字符")
            
#             # 尝试提取商品数量
#             product_elements = page.query_selector_all('.jSubObject, .gl-i-wrap, .p-name')
#             print(f"   找到商品元素: {len(product_elements)} 个")
            
#             return {
#                 'success': True,
#                 'html': html_content,
#                 'title': page_title,
#                 'url': page.url,
#                 'product_count': len(product_elements),
#                 'filename': filename
#             }
            
#         except Exception as e:
#             print(f"❌ 访问失败: {e}")
#             return {
#                 'success': False,
#                 'error': str(e),
#                 'html': '',
#                 'title': '',
#                 'url': ''
#             }
#         finally:
#             browser.close()

# def extract_product_links_with_cookies(search_url, cookies_dict):
#     """使用cookies提取商品链接"""
#     with sync_playwright() as p:
#         browser = p.chromium.launch(headless=True)
        
#         context = browser.new_context(
#             user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
#             viewport={'width': 1920, 'height': 1080}
#         )
        
#         # 设置关键cookies
#         context.add_cookies([
#             {
#                 'name': 'pt_pin',
#                 'value': cookies_dict['pt_pin'],
#                 'domain': '.jd.com',
#                 'path': '/'
#             },
#             {
#                 'name': 'pt_key',
#                 'value': cookies_dict['pt_key'],
#                 'domain': '.jd.com',
#                 'path': '/'
#             },
#             {
#                 'name': 'pt_token',
#                 'value': cookies_dict.get('pt_token', 'h9vlqb9s'),
#                 'domain': '.jd.com',
#                 'path': '/'
#             },
#             {
#                 'name': '__jdv',
#                 'value': cookies_dict.get('__jdv', '95931165%7Candroidapp%7Ct_335139774%7Cappshare%7CCopyURL_shareid00712a023cbbf346176413824972713120_shangxiang_none%7C1764255576022'),
#                 'domain': '.jd.com',
#                 'path': '/'
#             }
#         ])
        
#         page = context.new_page()
#         product_links = []
        
#         try:
#             print(f"🛒 正在提取商品链接: {search_url}")
#             page.goto(search_url, timeout=60000, wait_until='networkidle')
            
#             # 等待商品列表加载
#             page.wait_for_timeout(5000)
            
#             # 滚动页面
#             page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
#             page.wait_for_timeout(3000)
            
#             # 获取页面内容
#             page_content = page.content()
            
#             # 方法1: 正则表达式提取
#             jd_links = re.findall(r'//item\.jd\.com/(\d+)\.html', page_content)
#             unique_skus = list(set(jd_links))
            
#             for sku in unique_skus:
#                 product_links.append({
#                     'sku_id': sku,
#                     'url': f'https://item.jd.com/{sku}.html',
#                     'title': f'商品_{sku}'
#                 })
            
#             # 方法2: CSS选择器提取
#             try:
#                 product_elements = page.query_selector_all('.jSubObject .jPic a, .jItem a, .jDesc a')
#                 for element in product_elements:
#                     href = element.get_attribute('href')
#                     if href and 'item.jd.com' in href:
#                         sku_match = re.search(r'/(\d+)\.html', href)
#                         if sku_match:
#                             sku_id = sku_match.group(1)
#                             # 去重
#                             if not any(p['sku_id'] == sku_id for p in product_links):
#                                 product_links.append({
#                                     'sku_id': sku_id,
#                                     'url': f'https://item.jd.com/{sku_id}.html',
#                                     'title': element.get_attribute('title') or element.text_content()[:50] + '...'
#                                 })
#             except Exception as e:
#                 print(f"CSS选择器提取失败: {e}")
            
#             print(f"📦 成功提取 {len(product_links)} 个商品链接")
#             return product_links
            
#         except Exception as e:
#             print(f"❌ 提取链接失败: {e}")
#             return []
#         finally:
#             browser.close()

# # 主测试函数
# def main():
#     # 你的cookies
#     cookies_dict = {
#         'pt_pin': 'jd_sOHayhdtddBZ',
#         'pt_key': 'AAJpJ69TADBcHa96KtgHpx47xouQOgoE0r6bhKqS3mshoJkKGf0XPF35NoTQLQRwDT4LkXXX_e4',
#         'pt_token': 'h9vlqb9s',
#         '__jdv': '95931165%7Candroidapp%7Ct_335139774%7Cappshare%7CCopyURL_shareid00712a023cbbf346176413824972713120_shangxiang_none%7C1764255576022'
#     }
    
#     search_url = "https://mall.jd.com/view_search-652812-1000080442-1000080442-0-0-2000-5000-1-1-60.html?keyword=pura"
    
#     print("=" * 60)
#     print("🔐 开始Cookies测试")
#     print("=" * 60)
    
#     # 1. 测试cookies是否有效
#     test_result = test_cookies_with_playwright(search_url, cookies_dict)
    
#     if test_result['success']:
#         print("\n✅ Cookies测试成功！")
#         print(f"   页面标题: {test_result['title']}")
#         print(f"   商品数量: {test_result['product_count']}")
#         print(f"   HTML文件: {test_result['filename']}")
        
#         # 2. 提取商品链接
#         print("\n" + "=" * 60)
#         print("🛒 开始提取商品链接")
#         print("=" * 60)
        
#         product_links = extract_product_links_with_cookies(search_url, cookies_dict)
        
#         if product_links:
#             # 保存结果
#             timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#             json_filename = f"jd_products_{timestamp}.json"
            
#             with open(json_filename, 'w', encoding='utf-8') as f:
#                 json.dump({
#                     'search_url': search_url,
#                     'extract_time': datetime.now().isoformat(),
#                     'total_products': len(product_links),
#                     'products': product_links
#                 }, f, ensure_ascii=False, indent=2)
            
#             # 保存为文本文件
#             txt_filename = f"jd_products_{timestamp}.txt"
#             with open(txt_filename, 'w', encoding='utf-8') as f:
#                 f.write(f"京东商品链接提取结果\n")
#                 f.write(f"搜索URL: {search_url}\n")
#                 f.write(f"提取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
#                 f.write(f"商品数量: {len(product_links)}\n")
#                 f.write("=" * 80 + "\n\n")
                
#                 for i, product in enumerate(product_links, 1):
#                     f.write(f"{i}. SKU_ID: {product['sku_id']}\n")
#                     f.write(f"   标题: {product['title']}\n")
#                     f.write(f"   链接: {product['url']}\n")
#                     f.write("-" * 50 + "\n")
            
#             print(f"\n💾 结果已保存:")
#             print(f"   JSON文件: {json_filename}")
#             print(f"   文本文件: {txt_filename}")
            
#             # 打印商品列表
#             print(f"\n📋 商品列表 (前10个):")
#             for i, product in enumerate(product_links[:10], 1):
#                 print(f"   {i}. {product['title']} (SKU: {product['sku_id']})")
                
#             if len(product_links) > 10:
#                 print(f"   ... 还有 {len(product_links) - 10} 个商品")
                
#         else:
#             print("❌ 没有提取到商品链接")
#     else:
#         print(f"❌ Cookies测试失败: {test_result['error']}")

# if __name__ == "__main__":
#     main()
# from playwright.sync_api import sync_playwright
# import time
# import sys

# def simple_refresh_until_error():
#     """最简单的刷新直到出错"""
#     chrome_port = 9222
#     url = "https://item.m.jd.com/product/100219438780.html"
    
#     with sync_playwright() as p:
#         # 连接到浏览器
#         browser = p.chromium.connect_over_cdp(f'http://localhost:{chrome_port}')
        
#         # 获取页面
#         contexts = browser.contexts
#         page = contexts[0].pages[0] if contexts and contexts[0].pages else browser.new_page()
        
#         count = 0
        
#         try:
#             while True:
#                 count += 1
#                 print(f"刷新次数: {count}", end="\r")
                
#                 try:
#                     # 刷新页面
#                     response = page.reload(timeout=10000)
                    
#                     # 检查响应
#                     if response and response.status >= 400:
#                         print(f"\nHTTP错误: {response.status}")
#                         raise Exception(f"HTTP {response.status}")
                    
#                     # 快速检查页面
#                     title = page.title()
#                     if "错误" in title or "404" in title or "异常" in title:
#                         print(f"\n页面标题包含错误: {title}")
#                         raise Exception("页面标题错误")
                    
#                 except Exception as e:
#                     print(f"\n第 {count} 次刷新出错: {e}")
#                     # page.screenshot(path="final_error.png")
#                     break
                
#                 # 等待2秒
#                 time.sleep(2)
                
#         except KeyboardInterrupt:
#             print("\n手动停止")
            
#         except Exception as e:
#             print(f"\n程序出错: {e}")
            
#         finally:
#             print(f"\n总计刷新: {count} 次")

# if __name__ == "__main__":
#     simple_refresh_until_error()
import json
from playwright.sync_api import sync_playwright
import time

# def simple_fetch():
#     """最简化的版本"""
    
#     # SKU列表
#     sku_list = ["100219438780", "100274062116"]
    
#     with sync_playwright() as p:
#         # 连接Chrome
#         browser = p.chromium.connect_over_cdp('http://localhost:9222')
        
#         # 使用第一个可用的页面
#         if browser.contexts and browser.contexts[0].pages:
#             page = browser.contexts[0].pages[0]
#         else:
#             page = browser.new_page()
        
#         for skuid in sku_list:
#             print(f"\n处理SKU: {skuid}")
            
#             try:
#                 # 访问页面
#                 url = f"https://item.m.jd.com/product/{skuid}.html"
#                 page.goto(url, wait_until='networkidle')
                
#                 # 保存HTML
#                 with open(f'{skuid}.html', 'w', encoding='utf-8') as f:
#                     f.write(page.content())
#                 print(f"HTML已保存")
                
#                 # 提取并打印_itemOnly
#                 data = page.evaluate("""
#                     () => {
#                         // 方法1：直接获取全局变量
#                         if (window._itemOnly) {
#                             return window._itemOnly;
#                         }
                        
#                         // 方法2：从脚本中提取
#                         const scripts = document.querySelectorAll('script');
#                         for (const script of scripts) {
#                             const text = script.textContent;
#                             if (text.includes('_itemOnly')) {
#                                 try {
#                                     const match = text.match(/_itemOnly\s*=\s*(\{.*?\});/s);
#                                     if (match) {
#                                         return JSON.parse(match[1]);
#                                     }
#                                 } catch(e) {}
#                             }
#                         }
#                         return null;
#                     }
#                 """)
                
#                 if data:
#                     print(f"_itemOnly数据:")
#                     print(json.dumps(data, ensure_ascii=False, indent=2))
                    
#                     # 保存JSON
#                     with open(f'{skuid}_itemOnly.json', 'w', encoding='utf-8') as f:
#                         json.dump(data, f, ensure_ascii=False, indent=2)
#                     print(f"JSON已保存")
#                 else:
#                     print("未找到_itemOnly")
                    
#             except Exception as e:
#                 print(f"错误: {e}")
            
#             time.sleep(2)
        
#         print("\n所有SKU处理完成!")


# def access_payment_page_with_debug_port(pay_url):
#     """使用Playwright连接调试端口9222访问支付页面"""
#     try:
#         # 连接已运行的浏览器实例（端口9222）
#         with sync_playwright() as p:
#             # 连接到已运行的Chrome实例
#             browser = p.chromium.connect_over_cdp('http://localhost:9222')
            
#             # 获取所有可用的上下文
#             contexts = browser.contexts
#             if not contexts:
#                 # 如果没有上下文，创建一个新的
#                 context = browser.new_context(
#                     user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
#                     viewport={'width': 1920, 'height': 1080},
#                     extra_http_headers={
#                         'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
#                         'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
#                     }
#                 )
#             else:
#                 # 使用第一个可用的上下文
#                 context = contexts[0]
            
#             # 创建一个新页面
#             page = context.new_page()
            
#             try:
#                 # 导航到支付页面
#                 print(f"🌐 正在加载支付页面: {pay_url}")
#                 page.goto(pay_url, timeout=30000, wait_until='networkidle')
                
#                 # 等待页面加载
#                 time.sleep(3)
                
#                 # 尝试查找并点击在线支付按钮
#                 print("🔍 正在查找在线支付按钮...")
                
#                 # 根据错误信息，实际需要点击的是taro-button-core元素
#                 payment_selectors = [
#                     # 根据错误信息，按钮是taro-button-core元素
#                     "taro-button-core.ActionBar_submit_LiQOa",
#                     ".ActionBar_submit_LiQOa",
#                     "taro-button-core[class*='submit']",
#                     "taro-button-core:has-text('在线支付')",
#                     "taro-text-core:has-text('在线支付')",
#                     "text=在线支付 >> visible=true",
#                     # 父级元素选择器
#                     ".ActionBar_text_Hv_Ml",  # 根据错误信息中的类名
#                     ".ActionBar_actionBar_8mJ27 .ActionBar_submit_LiQOa",
#                     # 其他可能的选择器
#                     "button:has-text('在线支付')",
#                     ".pay-online",
#                     "#onlinePay",
#                     "input[value='在线支付']",
#                 ]
                
#                 clicked = False
#                 for selector in payment_selectors:
#                     try:
#                         if page.locator(selector).count() > 0:
#                             print(f"✅ 找到元素: {selector}")
                            
#                             # 先高亮显示找到的元素
#                             page.locator(selector).first.highlight()
                            
#                             # 尝试不同的点击方法
#                             element = page.locator(selector).first
                            
#                             # 方法1: 直接点击
#                             try:
#                                 element.click(timeout=5000)
#                                 clicked = True
#                                 print(f"✅ 方法1 - 已点击在线支付按钮: {selector}")
#                                 break
#                             except:
#                                 print(f"⚠️ 方法1失败，尝试方法2...")
                            
#                             # 方法2: 使用JavaScript点击
#                             try:
#                                 page.evaluate("""
#                                     (selector) => {
#                                         const element = document.querySelector(selector);
#                                         if (element) {
#                                             element.click();
#                                             return true;
#                                         }
#                                         return false;
#                                     }
#                                 """, selector)
#                                 clicked = True
#                                 print(f"✅ 方法2 - 已通过JavaScript点击: {selector}")
#                                 break
#                             except:
#                                 print(f"⚠️ 方法2失败，尝试方法3...")
                            
#                             # 方法3: 点击父元素
#                             try:
#                                 parent_element = element.locator('xpath=..')
#                                 if parent_element.count() > 0:
#                                     parent_element.first.click(timeout=5000)
#                                     clicked = True
#                                     print(f"✅ 方法3 - 已点击父元素: {selector}")
#                                     break
#                             except:
#                                 print(f"⚠️ 方法3失败，尝试方法4...")
                            
#                             # 方法4: 强制点击（绕过拦截）
#                             try:
#                                 element.click(force=True, timeout=5000)
#                                 clicked = True
#                                 print(f"✅ 方法4 - 已强制点击: {selector}")
#                                 break
#                             except:
#                                 print(f"⚠️ 方法4失败，尝试方法5...")
                            
#                             # 方法5: 执行点击事件
#                             try:
#                                 page.evaluate("""
#                                     (selector) => {
#                                         const element = document.querySelector(selector);
#                                         if (element) {
#                                             const event = new MouseEvent('click', {
#                                                 view: window,
#                                                 bubbles: true,
#                                                 cancelable: true
#                                             });
#                                             element.dispatchEvent(event);
#                                             return true;
#                                         }
#                                         return false;
#                                     }
#                                 """, selector)
#                                 clicked = True
#                                 print(f"✅ 方法5 - 已执行点击事件: {selector}")
#                                 break
#                             except:
#                                 print(f"⚠️ 方法5失败，继续尝试下一个选择器...")
                                
#                     except Exception as e:
#                         print(f"⚠️ 尝试选择器 {selector} 时出错: {e}")
#                         continue

#                 if not clicked:
#                     print("❌ 所有点击方法都失败，尝试查找提交订单按钮...")
                    
#                     # 尝试查找提交订单按钮
#                     submit_selectors = [
#                         "text=提交订单",
#                         "button:has-text('提交订单')",
#                         "#orderSubmit",
#                         ".submit-btn",
#                         "input[type='submit']",
#                         "taro-button-core:has-text('提交订单')"
#                     ]
                    
#                     for selector in submit_selectors:
#                         try:
#                             if page.locator(selector).count() > 0:
#                                 print(f"✅ 找到提交订单按钮: {selector}")
#                                 page.locator(selector).first.click(force=True)
#                                 clicked = True
#                                 print(f"✅ 已点击提交订单按钮: {selector}")
#                                 break
#                         except:
#                             continue
                
#                 if clicked:
#                     print("✅ 成功触发点击操作")
#                 else:
#                     print("❌ 未能成功点击任何按钮")
                
#                 # 等待一段时间观察结果
#                 time.sleep(3)
                
#                 # 获取页面标题和内容摘要
#                 page_title = page.title()
#                 print(f"📄 页面标题: {page_title}")
                
#                 # 检查当前URL是否变化
#                 current_url = page.url
#                 print(f"📍 当前URL: {current_url}")
                
#                 # 检查是否有错误信息
#                 error_selectors = [
#                     "text=错误",
#                     "text=失败",
#                     "text=异常",
#                     ".error",
#                     ".error-message",
#                     ".fail",
#                     "text=抱歉，您本单购买的以下商品在所选择的地址下暂时不支持销售"
#                 ]
                
#                 for selector in error_selectors:
#                     try:
#                         if page.locator(selector).count() > 0:
#                             error_text = page.locator(selector).first.text_content()
#                             print(f"⚠️ 检测到错误信息: {error_text[:100]}...")
#                     except:
#                         continue
                
#                 # 检查是否成功跳转到支付页面
#                 if 'cashier' in current_url or 'pay' in current_url or 'payment' in current_url:
#                     print("🎉 成功进入支付页面！")
#                 elif 'checkout' in current_url:
#                     print("⚠️ 仍然在结算页面，可能点击未成功")
#                 else:
#                     print(f"ℹ️  页面跳转到: {current_url}")
                
#             except Exception as e:
#                 print(f"❌ 访问支付页面时出错: {e}")
            
#             finally:
#                 # 保持页面打开
#                 try:
#                     pages = context.pages
#                     print(f"📑 当前上下文中有 {len(pages)} 个页面")
#                 except:
#                     pass
    
#     except Exception as e:
#         print(f"❌ 连接调试浏览器失败: {e}")
#         print("💡 请确保已启动Chrome浏览器并启用远程调试:")
#         print("    Windows: chrome.exe --remote-debugging-port=9222")

# if __name__ == "__main__":
#     access_payment_page_with_debug_port('https://trade.m.jd.com/checkout?commlist=100215568441,,1#/index')

def access_payment_page_with_debug_port(pay_url):
    """使用Playwright连接调试端口9222访问支付页面"""
    try:
        # 连接已运行的浏览器实例（端口9222）
        with sync_playwright() as p:
            # 连接到已运行的Chrome实例
            browser = p.chromium.connect_over_cdp('http://localhost:9222')
            
            # 获取所有可用的上下文
            contexts = browser.contexts
            if not contexts:
                # 如果没有上下文，创建一个新的
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                    extra_http_headers={
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    }
                )
            else:
                # 使用第一个可用的上下文
                context = contexts[0]
            
            # 创建一个新页面
            page = context.new_page()
            
            try:
                # 导航到支付页面
                print(f"🌐 正在加载支付页面: {pay_url}")
                page.goto(pay_url, timeout=30000, wait_until='networkidle')
                
                # 等待页面加载
                time.sleep(3)
                
                # 尝试查找并点击在线支付按钮
                print("🔍 正在查找在线支付按钮...")
                
                # 根据错误信息，实际需要点击的是taro-button-core元素
                payment_selectors = [
                    "taro-button-core.ActionBar_submit_LiQOa",
                    ".ActionBar_submit_LiQOa",
                    "taro-button-core[class*='submit']",
                    "taro-button-core:has-text('在线支付')",
                    "taro-text-core:has-text('在线支付')",
                    "text=在线支付 >> visible=true",
                    ".ActionBar_text_Hv_Ml",
                    ".ActionBar_actionBar_8mJ27 .ActionBar_submit_LiQOa",
                    "button:has-text('在线支付')",
                    ".pay-online",
                    "#onlinePay",
                    "input[value='在线支付']",
                ]
                
                clicked = False
                for selector in payment_selectors:
                    try:
                        if page.locator(selector).count() > 0:
                            print(f"✅ 找到元素: {selector}")
                            
                            # 方法1: 直接点击
                            page.locator(selector).first.click(timeout=5000)
                            clicked = True
                            print(f"✅ 已点击在线支付按钮")
                            break
                                
                    except Exception as e:
                        print(f"⚠️ 点击失败: {e}")
                        continue

                if not clicked:
                    print("❌ 未找到支付按钮，尝试查找提交订单按钮...")
                    
                    # 尝试查找提交订单按钮
                    submit_selectors = [
                        "text=提交订单",
                        "button:has-text('提交订单')",
                        "#orderSubmit",
                        ".submit-btn",
                        "input[type='submit']",
                        "taro-button-core:has-text('提交订单')"
                    ]
                    
                    for selector in submit_selectors:
                        try:
                            if page.locator(selector).count() > 0:
                                print(f"✅ 找到提交订单按钮: {selector}")
                                page.locator(selector).first.click(force=True)
                                clicked = True
                                print(f"✅ 已点击提交订单按钮")
                                break
                        except:
                            continue
                
                if clicked:
                    print("✅ 成功触发点击操作")
                else:
                    print("❌ 未能成功点击任何按钮")
                
                # 等待一段时间观察结果
                time.sleep(3)
                
                # 获取页面标题和内容摘要
                page_title = page.title()
                print(f"📄 页面标题: {page_title}")
                
                # 检查当前URL是否变化
                current_url = page.url
                print(f"📍 当前URL: {current_url}")
                
                # 检查是否成功跳转到支付页面
                if 'cashier' in current_url or 'pay' in current_url or 'payment' in current_url:
                    print("🎉 成功进入支付页面！")
                
            except Exception as e:
                print(f"❌ 访问支付页面时出错: {e}")
            
            finally:
                # 保持页面打开
                try:
                    pages = context.pages
                    print(f"📑 当前上下文中有 {len(pages)} 个页面")
                except:
                    pass
    
    except Exception as e:
        print(f"❌ 连接调试浏览器失败: {e}")
        print("💡 请确保已启动Chrome浏览器并启用远程调试")

if __name__ == "__main__":
    access_payment_page_with_debug_port('https://trade.m.jd.com/checkout?commlist=100215568441,,1#/index')
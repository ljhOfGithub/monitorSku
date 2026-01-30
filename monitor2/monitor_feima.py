from playwright.sync_api import sync_playwright
import time
import re
import json
import csv
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from urllib.parse import parse_qs, urlparse
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import schedule
import threading
import signal
import sys
from urllib.parse import quote
import subprocess
import random

PROXY_CONFIG = {
    "server": "q865.kdltps.com:15818",
    "username": "t16612090902574",
    "password": "2ow56b24"
}
chrome_dirs = []
root_dir = "C:\\data"
user_dir = "C:\\Users\\yuhua\\Desktop\\rpa\\feishu\\monitor2"

class JDSKUMonitor:
    def __init__(self, keywords_config_file, webhook_urls=None, alert_webhook_url=None):
        self.keywords_config_file = keywords_config_file
        self.cookies_source = "none"
        self.webhook_urls = webhook_urls or []
        self.alert_webhook_url = alert_webhook_url
        
        self.all_skus_dir = os.path.join(root_dir, "all_skus")
        self.all_history_dir = os.path.join(root_dir, "all_history_with_brand")
        self.new_skus_records_dir = os.path.join(root_dir, "new_skus_records")
        self.monitor_results_file = os.path.join(root_dir, "monitor_results.json")
        
        self.monitor_type = "所有类"
        self.init_monitor_results()
        
        self.cookies_dicts = [{}]
        
        self.create_directories()
        
        self.is_running = True
        self.is_shutting_down = False  
        self.current_monitor_data = {}  
        self.has_sent_summary = False  

        self.cached_historical_skus = set()
        self.sku_lock = threading.Lock()
        
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        self.executor = ThreadPoolExecutor(max_workers=1)
    
    def load_keywords_config(self):
        if not os.path.exists(self.keywords_config_file):
            print(f"❌ JSON文件不存在: {self.keywords_config_file}")
            return []
        
        try:
            with open(self.keywords_config_file, 'r', encoding='utf-8') as f:
                keywords_config = json.load(f)
            print(f"✅ 从JSON文件加载 {len(keywords_config)} 个关键词配置")
            return keywords_config
        except Exception as e:
            print(f"❌ 加载JSON文件时出错: {e}")
            return []
    
    def load_cookies(self):
        return [{}]
    
    def load_cookies_from_browsers(self, user_data_dirs):
        return [{}]
    
    def load_cookies_from_file(self, cookies_file):
        return {}
    
    def parse_cookies_string(self, cookies_string):
        cookies_dict = {}
        try:
            cookies_list = cookies_string.split(';')
            for cookie in cookies_list:
                cookie = cookie.strip()
                if '=' in cookie:
                    key, value = cookie.split('=', 1)
                    cookies_dict[key.strip()] = value.strip()
            
            print(f"✅ 成功解析 {len(cookies_dict)} 个cookies")
            
            if 'pt_key' in cookies_dict:
                print(f"🔑 pt_key: {cookies_dict['pt_key'][:20]}...")
            if 'pt_pin' in cookies_dict:
                print(f"🔑 pt_pin: {cookies_dict['pt_pin']}")
            
            return cookies_dict
            
        except Exception as e:
            print(f"❌ 解析cookies字符串时出错: {e}")
            return {}

    def generate_jd_deep_link(self, sku_id):
        target_url = f"https://item.m.jd.com/product/{sku_id}.html"
        params_dict = {"category": "jump", "des": "m", "url": target_url}
        encoded_params = quote(json.dumps(params_dict, separators=(',', ':')))
        deep_link_url = f"openapp.jdmobile://virtual?params={encoded_params}"
        return [{"tag": "a", "text": "点击立即购买", "href": deep_link_url}]
    
    def signal_handler(self, signum, frame):
        if self.is_shutting_down:
            print("\n🛑 强制退出...")
            os._exit(1)
            
        print(f"\n\n⚠️  收到退出信号，正在保存数据...")
        self.is_running = False
        self.is_shutting_down = True
        
        print("🛑 停止所有任务...")
        self.executor.shutdown(wait=False)
        
        if not self.has_sent_summary and hasattr(self, 'current_monitor_data') and self.current_monitor_data:
            print("📤 发送格式化的中断监控总结报告...")
            
            data = self.current_monitor_data
            total_new = len(data.get('total_new_skus', set()))
            timestamp = data.get('process_timestamp', '未知')
            
            msg = f"🛑 监控程序已中断（手动停止或系统信号）\n"
            msg += f"⏰ 中断时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            msg += f"📦 本轮已发现新SKU总数: {total_new} 个\n"
            msg += f"📅 批次时间戳: {timestamp}\n\n"
            
            details = data.get('keyword_new_skus_details', {})
            if details:
                msg += "🎯 部分关键词扫描结果:\n"
                for kw, detail in list(details.items()):  
                    new_count = len(detail.get('new_skus', []))
                    msg += f"- {kw}: 发现 {new_count} 个新商品\n"
            
            self.send_alert_notification(msg)
            self.has_sent_summary = True
        
        print("💡 再次按 Ctrl+C 强制退出")
        
        threading.Timer(3.0, os._exit, [0]).start()
    
    def create_directories(self):
        directories = [
            os.path.join(root_dir, "monitor_data"),
            os.path.join(root_dir, "monitor_logs"), 
            os.path.join(root_dir, "product_details"),
            os.path.join(root_dir, "new_skus_records"),
            self.all_skus_dir,
            self.all_history_dir,
        ]
        
        for directory in directories:
            if not os.path.exists(directory):
                os.makedirs(directory)
                print(f"📁 创建文件夹: {directory}")
    
    def load_all_existing_skus(self):
        all_skus = set()
        
        history_main_dir = os.path.join(root_dir, "all_history_with_brand")
        if os.path.exists(history_main_dir):
            for filename in os.listdir(history_main_dir):
                if filename.endswith(".json"):
                    filepath = os.path.join(history_main_dir, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            details = data.get('skus_detail', [])
                            for item in details:
                                if 'sku_id' in item:
                                    all_skus.add(str(item['sku_id']))
                    except Exception as e:
                        print(f"❌ 加载 history 详情文件 {filename} 时出错: {e}")

        if os.path.exists(self.all_skus_dir):
            for filename in os.listdir(self.all_skus_dir):
                if filename.endswith("all_history.json"):
                    filepath = os.path.join(self.all_skus_dir, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            skus = data.get('skus', [])
                            for s in skus:
                                all_skus.add(str(s))
                    except Exception as e:
                        print(f"❌ 加载 SKU 历史文件 {filename} 时出错: {e}")

        return all_skus
    
    def save_keyword_skus(self, keyword_config, skus, timestamp):
        keyword = keyword_config['keyword']
        min_price = keyword_config['min_price']
        max_price = keyword_config['max_price']
        brand = keyword_config.get('brand', 'default')

        safe_keyword = re.sub(r'[^\w\u4e00-\u9fa5]', '_', keyword)
        filename = f"{safe_keyword}_all_history.json"
        filepath = os.path.join(self.all_skus_dir, filename)
        
        with self.sku_lock:
            existing_skus = set()
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        old_data = json.load(f)
                        existing_skus = set(old_data.get('skus', []))
                except Exception:
                    pass
            
            new_set = set(skus)
            all_skus_merged = existing_skus.union(new_set)
            
            self.cached_historical_skus.update(new_set)
            
            data = {
                'keyword': keyword,
                'brand': brand,           
                'min_price': min_price,   
                'max_price': max_price,   
                'skus': list(all_skus_merged),
                'last_update_time': datetime.now().isoformat(),
                'total_skus': len(all_skus_merged)
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        
    def save_new_skus_record(self, keyword_config, new_skus, timestamp):
        keyword = keyword_config['keyword']
        min_price = keyword_config['min_price']
        max_price = keyword_config['max_price']
        brand = keyword_config.get('brand', 'default')
        safe_keyword = re.sub(r'[^\w\u4e00-\u9fa5]', '_', keyword)
        
        filename = f"new_skus_{safe_keyword}_{brand}_{min_price}_{max_price}.json"
        filepath = os.path.join(self.new_skus_records_dir, filename)
        
        existing_new_skus = set()
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    old_data = json.load(f)
                    existing_new_skus = set(old_data.get('new_skus', []))
            except Exception:
                pass

        all_new_skus_merged = existing_new_skus.union(set(new_skus))
        
        data = {
            'keyword': keyword,
            'brand': brand,
            'min_price': min_price,
            'max_price': max_price,
            'last_found_time': datetime.now().isoformat(),
            'total_new_skus_count': len(all_new_skus_merged),
            'new_skus': list(all_new_skus_merged),
            'has_new_skus': len(all_new_skus_merged) > 0
        }
    
    def get_keyword_historical_skus(self, keyword):
        return self.cached_historical_skus
    
    def save_search_page(self, keyword, min_price, max_price, html_content, timestamp):
        safe_keyword = re.sub(r'[^\w\u4e00-\u9fa5]', '_', keyword)
        
        if min_price > 0 or max_price > 0:
            filename = f"search_{safe_keyword}_{min_price}_{max_price}_{timestamp}.html"
        else:
            filename = f"search_{safe_keyword}_{timestamp}.html"
        
        search_pages_dir = os.path.join(root_dir, "search_pages")
        filepath = os.path.join(search_pages_dir, filename)
        
        return filepath
    
    def save_product_details(self, keyword_config, product_links, all_skus, new_skus, timestamp):
        keyword = keyword_config['keyword']
        min_price = keyword_config['min_price']
        max_price = keyword_config['max_price']
        brand = keyword_config.get('brand', 'default')
        safe_keyword = re.sub(r'[^\w\u4e00-\u9fa5]', '_', keyword)
        
        details_filename = f"products_{safe_keyword}_{brand}_{min_price}_{max_price}.json"
        details_filepath = os.path.join(os.path.join(root_dir, "product_details"), details_filename)
        
        existing_products_map = {}
        existing_all_skus = set()
        existing_new_skus_history = set()
        
        if os.path.exists(details_filepath):
            try:
                with open(details_filepath, 'r', encoding='utf-8') as f:
                    old_data = json.load(f)
                    for prod in old_data.get('products', []):
                        sku_id = prod.get('sku_id')
                        if sku_id:
                            existing_products_map[sku_id] = prod
                    existing_all_skus = set(old_data.get('all_skus', []))
                    existing_new_skus_history = set(old_data.get('new_skus_list', []))
            except Exception:
                pass

        for prod in product_links:
            sku_id = prod.get('sku_id')
            if sku_id:
                existing_products_map[sku_id] = prod
        
        merged_all_skus = existing_all_skus.union(set(all_skus))
        merged_new_skus_history = existing_new_skus_history.union(set(new_skus))
        
        details_data = {
            'keyword': keyword,
            'brand': brand,
            'min_price': min_price,
            'max_price': max_price,
            'last_update_time': datetime.now().isoformat(),
            'total_products': len(existing_products_map),
            'total_skus': len(merged_all_skus),
            'total_new_skus_count': len(merged_new_skus_history),
            'products': list(existing_products_map.values()),
            'all_skus': list(merged_all_skus),
            'new_skus_list': list(merged_new_skus_history)
        }
        
        return product_links
    
    def load_monitor_results(self):
        if os.path.exists(self.monitor_results_file):
            try:
                with open(self.monitor_results_file, 'r', encoding='utf-8') as f:
                    self.monitor_results = json.load(f)
                print(f"📊 已加载历史监控结果")
            except Exception as e:
                print(f"❌ 加载监控结果时出错: {e}")
                self.init_monitor_results()
        else:
            self.init_monitor_results()
    
    def save_monitor_results(self):
        with open(self.monitor_results_file, 'w', encoding='utf-8') as f:
            json.dump(self.monitor_results, f, ensure_ascii=False, indent=2)
    
    def send_feishu_notification(self, message, webhook_url, is_post=False):
        if not webhook_url:
            return False
        
        if is_post:
            data = {
                "msg_type": "post",
                "content": {
                    "post": {
                        "zh_cn": {
                            "title": "京东监控系统通知",
                            "content": message
                        }
                    }
                }
            }
        else:
            data = {
                "msg_type": "text",
                "content": {
                    "text": message
                }
            }
        
        headers = {
            'Content-Type': 'application/json; charset=utf-8'
        }
        
        try:
            response = requests.post(webhook_url, headers=headers, json=data, timeout=10)
            if response.status_code == 200:
                return True
            else:
                print(f"❌ 飞书通知发送失败: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ 飞书通知发送异常: {e}")
            return False
    
    def send_to_all_webhooks(self, message, is_post=False):
        if not self.webhook_urls:
            print("❌ 未配置飞书webhook URL")
            return False
        
        success_count = 0
        for i, webhook_url in enumerate(self.webhook_urls, 1):
            if self.send_feishu_notification(message, webhook_url, is_post=is_post):
                success_count += 1
                print(f"✅ 机器人 {i} 发送成功")
            else:
                print(f"❌ 机器人 {i} 发送失败")
            time.sleep(1)  
        
        print(f"📊 通知发送完成: {success_count}/{len(self.webhook_urls)} 个机器人成功")
        return success_count > 0
    
    def send_alert_notification(self, message):
        if not self.alert_webhook_url:
            print("❌ 未配置警报webhook URL")
            return False
        
        alert_message = f"{message}"
        return self.send_feishu_notification(alert_message, self.alert_webhook_url)
    
    def print_new_skus_to_console(self, keyword_config, new_products):
        if not new_products:
            return
        
        keyword = keyword_config['keyword']
        min_price = keyword_config['min_price']
        max_price = keyword_config['max_price']
        
        print(f"🎯 关键词 '{keyword}' 发现 {len(new_products)} 个新SKU:")
        for i, product in enumerate(new_products, 1):
            sku = product['sku_id']
            title = product.get('title', '未知')
            
            print(f"   {i}. SKU: {sku}")
            print(f"       链接: https://item.m.jd.com/product/{sku}.html")
            print(f"       标题: {title}")
    
    def send_immediate_new_sku_notification(self, keyword_config, new_products):
        if not new_products:
            return
        
        keyword = keyword_config['keyword']
        min_price = keyword_config['min_price']
        max_price = keyword_config['max_price']
        
        for product in new_products:
            sku = product['sku_id']
            title = product.get('title', '未知')
            deep_link_tag = self.generate_jd_deep_link(sku)
            
            post_content = [
                [{"tag": "text", "text": "🚨 发现新SKU！\n"}],
                [{"tag": "text", "text": f"📊 关键词: {keyword}\n"}],
            ]
            
            if min_price > 0 or max_price > 0:
                post_content.append([{"tag": "text", "text": f"💰 价格范围: {min_price}-{max_price}元\n"}])
            
            post_content.extend([
                [{"tag": "text", "text": f"🆕 新SKU: {sku}\n"}],
                [{"tag": "text", "text": f"📦 标题: {title}\n"}],
                [{"tag": "text", "text": "🔗 "}] + deep_link_tag + [{"tag": "text", "text": "\n"}],
                [{"tag": "text", "text": f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"}]
            ])
            
            time.sleep(2)
    
    def send_keyword_new_skus_notification(self, keyword_config, new_products):
        if not new_products:
            return
        
        self.print_new_skus_to_console(keyword_config, new_products)
        self.send_immediate_new_sku_notification(keyword_config, new_products)
        
        keyword = keyword_config['keyword']
        min_price = keyword_config['min_price']
        max_price = keyword_config['max_price']
        
        post_content = [
            [{"tag": "text", "text": f"⚠️⚠️⚠️ {self.monitor_type}京东商品监控通知\n"}],
            [{"tag": "text", "text": f"📊 关键词: {keyword}\n"}]
        ]
        
        if min_price > 0 or max_price > 0:
            post_content.append([{"tag": "text", "text": f"💰 价格范围: {min_price}-{max_price}元\n"}])
            
        post_content.extend([
            [{"tag": "text", "text": f"🆕 发现新SKU: {len(new_products)} 个\n"}],
            [{"tag": "text", "text": f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"}]
        ])
        
        for i, product in enumerate(new_products, 1):
            sku = product['sku_id']
            title = product.get('title', '未知')
            deep_link_tag = self.generate_jd_deep_link(sku)
            
            post_content.append([{"tag": "text", "text": f"{i}. 标题: {title}\n"}])
            post_content.append([{"tag": "text", "text": f"   SKU: {sku}\n"}])
            post_content.append([{"tag": "text", "text": "   "}] + deep_link_tag + [{"tag": "text", "text": "\n\n"}])
        
        print(f"📤 发送关键词 '{keyword}' 批量通知到 {len(self.webhook_urls)} 个机器人...")
        self.send_to_all_webhooks(post_content, is_post=True)
    
    def check_login_status(self, page_content):
        user_indicators = [
            '我的京东', '我的订单', '用户中心', '个人中心', '我的资产',
            'class="user"', 'id="user"', '会员中心', 'nickname', 'user-info'
        ]
        
        has_user_info = any(indicator in page_content for indicator in user_indicators)
        return has_user_info
    
    def check_cookies_validity(self, page, browser_index=1):
        return True
    
    def create_browser_context(self, playwright, browser_index=1):
        endpoint_url = "http://127.0.0.1:9222"
        
        try:
            print(f"🔗 正在接管本地 Chrome (127.0.0.1:9222)...")
            browser = playwright.chromium.connect_over_cdp(endpoint_url)
            
            if browser.contexts:
                context = browser.contexts[0]
            else:
                context = browser.new_context()
                
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
                Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });
                Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
            """)
            
            return context
        except Exception as e:
            print(f"❌ 连接失败！请确保 Chrome 已通过 --remote-debugging-port=9222 启动。")
            raise e

    def remove_hot_sale_products(self, html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        
        hot_sale_sections = soup.find_all('div', class_=['jHotSale', 'hot-sale', 'hot-product'])
        for section in hot_sale_sections:
            section.decompose()
        
        return str(soup)
    
    def extract_main_product_links(self, html_content):
        cleaned_html = self.remove_hot_sale_products(html_content)
        soup = BeautifulSoup(cleaned_html, 'html.parser')
        
        product_links = []
        seen_skus = set()
        
        main_products = soup.find_all('div', class_='jItem')
        
        for product in main_products:
            try:
                pic_div = product.find('div', class_='jPic')
                if not pic_div:
                    continue
                    
                pic_link = pic_div.find('a')
                if pic_link and pic_link.get('href'):
                    main_url = pic_link['href']
                    
                    if main_url.startswith('//'):
                        full_url = 'https:' + main_url
                    elif main_url.startswith('/'):
                        full_url = 'https://item.jd.com' + main_url
                    else:
                        full_url = main_url
                    
                    sku_match = re.search(r'/(\d+)\.html', full_url)
                    if sku_match:
                        sku_id = sku_match.group(1)
                        
                        if sku_id not in seen_skus:
                            seen_skus.add(sku_id)
                            
                            desc_div = product.find('div', class_='jDesc')
                            title = "未知商品"
                            if desc_div and desc_div.find('a'):
                                title = desc_div.find('a').get_text(strip=True)
                            
                            title_lower = title.lower()
                            hot_keywords = ['热销', '热卖', '爆款', '热门', 'hot', '平板', '笔记本', '显示屏', '电脑', '键盘', 'pad', '路由', '手表', '鞋', '耳机', '音响', '音箱', '充电器', '保护套', '保护壳', '手机壳', '充电线', '数据线', 'MateBook', 'WATCH', 'Mate X7 典藏版']
                            is_hot_title = any(keyword in title_lower for keyword in hot_keywords)
                            if(is_hot_title):
                                continue
                            product_links.append({
                                'sku_id': sku_id,
                                'url': full_url,
                                'title': title[:100] + '...' if len(title) > 100 else title,
                                'is_main': True,
                                'extract_time': datetime.now().isoformat()
                            })
            
            except Exception as e:
                print(f"❌ 提取商品信息时出错: {e}")
                continue
        
        return product_links
    
    def search_jd_products(self, keyword_config, timestamp, browser_index=1):
        if not self.is_running:
            return []
            
        keyword = keyword_config['keyword']
        min_price = keyword_config['min_price']
        max_price = keyword_config['max_price']
        brand = keyword_config['brand']

        if brand == 'huawei':
            brand_str = '%25E5%258D%258E%25E4%25B8%25BA%25EF%25BC%2588HUAWEI%25EF%25BC%2589'
        elif brand == 'honor':
            brand_str = '%25E8%258D%25A3%25E8%2580%2580%25EF%25BC%2588HONOR%25EF%25BC%2589'
        elif brand == 'xiaomi':
            brand_str = '%25E5%25B0%258F%25E7%25B1%25B3%25EF%25BC%2588MI%25EF%25BC%2589'
        elif brand == 'oppo':
            brand_str = 'OPPO'
        elif brand == 'oneplus':
            brand_str = '%25E4%25B8%2580%25E5%258A%2580'
        elif brand == 'realme':
            brand_str = '%25E7%259C%259F%25E6%2588%2591%25EF%25BC%2588realme%25EF%25BC%2589'
        elif brand == 'vivo' or brand == 'iqoo':
            brand_str = 'vivo'
            
        if min_price > 0 or max_price > 0:
            search_url = f"https://mall.jd.com/view_search-652812-1000080442-1000080442-0-1-{min_price}-{max_price}-1-1-60.html?keyword={quote(quote(keyword, encoding='utf-8'), encoding='utf-8')}&ext_attr=5522:90100&exp_brand={brand_str}"
            safe_keyword = re.sub(r'[^\w\u4e00-\u9fa5]', '_', keyword)
            original_url = f"https://mall.jd.com/view_search-652812-1000080442-1000080442-0-1-{min_price}-{max_price}-1-1-60.html?keyword={safe_keyword}&ext_attr=5522:90100&exp_brand={brand_str}"
        else:
            search_url = f"https://mall.jd.com/view_search-652812-1000080442-1000080442-0-0-0-0-1-1-60.html?keyword={quote(keyword, encoding='utf-8')}"
            safe_keyword = re.sub(r'[^\w\u4e00-\u9fa5]', '_', keyword)
            original_url = f"https://mall.jd.com/view_search-652812-1000080442-1000080442-0-1-0-0-1-1-60.html?keyword={safe_keyword}&ext_attr=5522:90100&exp_brand={brand_str}"
        
        with sync_playwright() as p:
            context = self.create_browser_context(p, browser_index)
            page = context.new_page()
            
            try:
                page.goto(search_url, timeout=60000, wait_until='networkidle')
                
                try:
                    page.wait_for_selector('.jSearchList-792077 li.jSubObject', timeout=30000)
                    has_empty_message = False
                    try:
                        empty_selector = '.jMessageError'
                        has_empty_message = page.locator(empty_selector).count() > 0
                    except:
                        pass
                    
                    if has_empty_message:
                        html_content = page.content()
                        self.save_search_page(keyword, min_price, max_price, html_content, timestamp)
                        return [], search_url, original_url
                except:
                    pass
                                    
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2)
                
                html_content = page.content()
                self.save_search_page(keyword, min_price, max_price, html_content, timestamp)
                product_links = self.extract_main_product_links(html_content)
                return product_links, search_url, original_url
                
            except Exception as e:
                raise Exception(f"搜索执行异常: {e}")
            finally:
                try:
                    if 'page' in locals():
                        page.close()
                        print(f"🧹 [Debug] 已关闭关键词 '{keyword}' 的标签页")
                except:
                    pass
    
    def process_single_keyword(self, keyword_config, timestamp, browser_index=1):
        if not self.is_running:
            return set(), [], set(), []
            
        keyword = keyword_config['keyword']
        min_price = keyword_config['min_price']
        max_price = keyword_config['max_price']
        
        search_result = self.search_jd_products(keyword_config, timestamp, browser_index)
        if not search_result:
            raise Exception("未获取到有效的搜索结果")
        
        product_links, search_url, original_url = search_result
        
        if not product_links:
            print(f"❌ 浏览器 {browser_index} 搜索关键词 '{keyword}' (价格: {min_price}-{max_price}元) 在时间点 {datetime.now().isoformat(' ')} 未找到商品 搜索URL: {search_url}")
            return set(), [], set(), []
        
        all_skus = set(product['sku_id'] for product in product_links)
        historical_skus = self.get_keyword_historical_skus(keyword)
        
        new_skus_for_keyword = all_skus - historical_skus
        new_products_for_keyword = [p for p in product_links if p['sku_id'] in new_skus_for_keyword]
        
        self.save_keyword_skus(keyword_config, all_skus, timestamp)
        self.save_new_skus_record(keyword_config, new_skus_for_keyword, timestamp)
        self.save_product_details(keyword_config, product_links, all_skus, new_skus_for_keyword, timestamp)
        
        if new_skus_for_keyword:
            print(f"🔔  浏览器 {browser_index} 搜索关键词 '{keyword}' 在时间点 {datetime.now().isoformat(' ')} 找到 {len(all_skus)} 个SKU 发现 {len(new_skus_for_keyword)} 个新SKU，立即发送通知... 搜索URL: {search_url}")
            self.send_keyword_new_skus_notification(keyword_config, new_products_for_keyword)
            self.update_keyword_stats(keyword_config, len(new_skus_for_keyword))

            print(f"🚀 [即时触发] 关键词 '{keyword}' 发现新SKU，正在运行过滤脚本...")
            self.run_filter_by_history_script()
        else:
            print(f"ℹ️  浏览器 {browser_index} 搜索关键词 '{keyword}' (价格: {min_price}-{max_price}元) 在时间点 {datetime.now().isoformat(' ')} 找到 {len(all_skus)} 个SKU 没有新SKU 搜索URL: {search_url}")
        
        return all_skus, product_links, new_skus_for_keyword, new_products_for_keyword
    
    def process_keyword_with_browser(self, args):
        if not self.is_running:
            return set(), [], set(), []
            
        keyword_config, timestamp, browser_index = args
        return self.process_single_keyword(keyword_config, timestamp, browser_index)
    
    def send_monitor_summary_notification(self, monitor_data):
        if not monitor_data.get('total_new_skus'):
            self.send_alert_notification(f"ℹ️  {self.monitor_type}本轮监控没有发现新SKU")
            print("ℹ️  没有新SKU，不发送总结通知")
            return
        
        keyword_details_with_new_skus = {}
        for keyword, details in monitor_data.get('keyword_new_skus_details', {}).items():
            if details['new_skus']:
                keyword_details_with_new_skus[keyword] = details
        
        if not keyword_details_with_new_skus:
            self.send_alert_notification(f"ℹ️  {self.monitor_type}没有包含新SKU的关键词")
            print("ℹ️  没有包含新SKU的关键词，不发送总结通知")
            return
        
        post_content = [
            [{"tag": "text", "text": f"{self.monitor_type}监控任务完成总结\n"}],
            [{"tag": "text", "text": f"⏰ 开始时间: {monitor_data.get('process_timestamp')}\n"}],
            [{"tag": "text", "text": f"⏰ 结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"}],
            [{"tag": "text", "text": f"📊 处理关键词: {len(self.keywords_config)} 个\n"}],
            [{"tag": "text", "text": f"🆕 发现新SKU的关键词: {len(keyword_details_with_new_skus)} 个\n"}],
            [{"tag": "text", "text": f"🆕 总共发现新SKU: {len(monitor_data['total_new_skus'])} 个\n\n"}],
            [{"tag": "text", "text": f"📁 历史SKU数量: {monitor_data.get('all_existing_skus_count', 0)} 个\n"}]
        ]
        post_content.append([{"tag": "text", "text": "📋 发现新SKU的关键词详情:\n"}])
        for keyword, details in keyword_details_with_new_skus.items():
            post_content.append([{"tag": "text", "text": f"   - {keyword}({details['min_price']}-{details['max_price']}元): {len(details['new_skus'])}个新SKU\n"}])
            
            if details['new_skus']:
                for sku in details['new_skus']:
                    product_info = None
                    for product in details.get('new_products', []):
                        if product['sku_id'] == sku:
                            product_info = product
                            break
                    
                    title = product_info.get('title', '未知商品') if product_info else '未知商品'
                    deep_link_tag = self.generate_jd_deep_link(sku)
                    
                    post_content.append([{"tag": "text", "text": f"     - {title} ({sku}) "}] + deep_link_tag + [{"tag": "text", "text": "\n"}])
        
        print("📤 发送监控总结通知...")
        self.send_feishu_notification(post_content, self.alert_webhook_url, is_post=True)
        self.has_sent_summary = True
    
    def get_interval_minutes(self):
        now = datetime.now()
        current_hour = now.hour
        
        if (7 <= current_hour <= 24):
            return random.randint(5, 10)  
        else:
            return 2 * 60  
    
    def run_filter_by_history_script(self):
        script_path = r"C:\Users\yuhua\Desktop\rpa\proxy\filter_by_history_with_brand.py"
        
        if not os.path.exists(script_path):
            print(f"❌ 找不到脚本文件: {script_path}")
            return False
        
        print(f"🚀 开始运行过滤脚本: {script_path}")
        try:
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                errors='replace'  
            )
            
            if result.returncode == 0:
                print("✅ 过滤脚本执行成功")
                return True
            else:
                print(f"❌ 过滤脚本执行失败，返回码: {result.returncode}")
                print(f"错误输出: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print("❌ 过滤脚本执行超时")
            return False
        except Exception as e:
            print(f"❌ 运行过滤脚本时出错: {e}")
            return False
    
    def monitor_keywords_concurrent(self):
        keywords_config = self.load_keywords_config()
        if not keywords_config:
            print("❌ 没有加载到关键词配置，跳过本次监控")
            return
        
        self.keywords_config = keywords_config
        process_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        print("\n" + "="*60)
        print("🕒 开始并发监控任务")
        print(f"⏰ 执行时间戳: {process_timestamp}")
        print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📝 配置关键词: {len(self.keywords_config)} 个")
        print("="*60)
        
        with self.sku_lock:
            print("📁 正在加载历史 SKU 记录...")
            self.cached_historical_skus = self.load_all_existing_skus()
            print(f"✅ 历史 SKU 加载完成，共 {len(self.cached_historical_skus)} 个")
        
        total_new_skus = set()
        total_new_products = []
        keyword_new_skus_details = {}
        monitor_start_time = datetime.now()
        
        pending_tasks = []
        for i, config in enumerate(self.keywords_config):
            pending_tasks.append((config, i + 1))
            
        while pending_tasks and self.is_running:
            print(f"🔄 当前池子剩余任务数: {len(pending_tasks)}")
            current_futures = {}
            
            for config, browser_idx in pending_tasks:
                task_args = (config, process_timestamp, browser_idx)
                future = self.executor.submit(self.process_keyword_with_browser, task_args)
                current_futures[future] = (config, browser_idx)
                time.sleep(60 * random.randint(5, 7)) 
            
            pending_tasks = []
            
            for future in concurrent.futures.as_completed(current_futures):
                config_info, idx = current_futures[future]
                keyword = config_info['keyword']
                try:
                    result = future.result(timeout=180)
                    if result and len(result) == 4:
                        all_skus, product_links, new_skus_for_keyword, new_products_for_keyword = result
                        
                        keyword_new_skus_details[keyword] = {
                            'new_skus': list(new_skus_for_keyword),
                            'new_products': new_products_for_keyword,
                            'total_skus': len(all_skus),
                            'min_price': config_info['min_price'],
                            'max_price': config_info['max_price'],
                        }
                        total_new_skus.update(new_skus_for_keyword)
                        total_new_products.extend(new_products_for_keyword)
                    else:
                        print(f"⚠️ 关键词 '{keyword}' 返回空结果，重新放入池子")
                        pending_tasks.append((config_info, idx))
                except Exception as e:
                    print(f"❌ 关键词 '{keyword}' 处理异常: {e}。即将重新尝试...")
                    pending_tasks.append((config_info, idx))
            
            if pending_tasks:
                time.sleep(5) 
        
        self.current_monitor_data = {
            'total_new_skus': total_new_skus,
            'all_existing_skus_count': len(self.cached_historical_skus),
            'keyword_new_skus_details': keyword_new_skus_details,
            'monitor_start_time': monitor_start_time,
            'process_timestamp': process_timestamp
        }
        
        if self.is_running:
            self.send_monitor_summary_notification(self.current_monitor_data)
        
        print(f"\n✅ 本轮并发监控任务全部完成，共发现 {len(total_new_skus)} 个新SKU")
        self.log_detailed_monitoring_result(total_new_skus, process_timestamp, keyword_new_skus_details)
    
    def update_keyword_stats(self, keyword_config, new_skus_count):
        keyword = keyword_config['keyword']
        if keyword not in self.monitor_results['keyword_stats']:
            self.monitor_results['keyword_stats'][keyword] = {
                'total_new_skus': 0,
                'monitor_count': 0,
                'price_range': f"{keyword_config['min_price']}-{keyword_config['max_price']}",
                'first_monitor_time': datetime.now().isoformat(),
                'last_monitor_time': datetime.now().isoformat()
            }
        
        stats = self.monitor_results['keyword_stats'][keyword]
        stats['total_new_skus'] += new_skus_count
        stats['monitor_count'] += 1
        stats['last_monitor_time'] = datetime.now().isoformat()
    
    def init_monitor_results(self):
        self.monitor_results = {
            "total_monitor_count": 0,
            "total_new_skus": 0,
            "keyword_stats": {},
            "last_monitor_time": None,
            "monitor_history": []
        }
        print("📊 创建新的监控结果")

    def update_monitor_results(self, total_new_skus, start_time, process_timestamp, keyword_new_skus_details):
        self.monitor_results['total_monitor_count'] += 1
        self.monitor_results['total_new_skus'] += len(total_new_skus)
        self.monitor_results['last_monitor_time'] = datetime.now().isoformat()
        
        monitor_record = {
            'timestamp': datetime.now().isoformat(),
            'process_timestamp': process_timestamp,
            'new_skus_count': len(total_new_skus),
            'duration_seconds': (datetime.now() - start_time).total_seconds(),
            'keywords_count': len(self.keywords_config),
            'keyword_details': keyword_new_skus_details
        }
        self.monitor_results['monitor_history'].append(monitor_record)
        
        if len(self.monitor_results['monitor_history']) > 100:
            self.monitor_results['monitor_history'] = self.monitor_results['monitor_history'][-100:]
    
    def log_detailed_monitoring_result(self, total_new_skus, process_timestamp, keyword_new_skus_details):
        log_file = os.path.join(root_dir, "monitor_logs", f"monitor_{datetime.now().strftime('%Y%m%d')}.log")
        
        log_entry = f"\n{'='*80}\n"
        log_entry += f"监控执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        log_entry += f"执行时间戳: {process_timestamp}\n"
        log_entry += f"处理关键词: {len(self.keywords_config)} 个\n"
        log_entry += f"总共发现新SKU: {len(total_new_skus)} 个\n"
        
        log_entry += "各关键词详情:\n"
        for keyword, details in keyword_new_skus_details.items():
            log_entry += f"  - {keyword}: {len(details['new_skus'])} 个新SKU\n"
            if details['new_skus']:
                log_entry += f"    新SKU列表: {', '.join(details['new_skus'])}\n"
        
        log_entry += f"{'='*80}\n"
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)
        
    def start_scheduled_monitoring(self):
        interval_minutes = self.get_interval_minutes()
        current_hour = datetime.now().hour
        
        print(f"⏰ 启动定时监控")
        print(f"📝 配置关键词文件: {self.keywords_config_file}")
        print(f"⏱️  当前时间段 ({current_hour}点): 执行间隔 {interval_minutes} 分钟")
        print(f"💾 按 Ctrl+C 可以安全退出程序")
        print(f"🛑 再次按 Ctrl+C 强制退出所有进程")
        
        print("\n🚀 开始第一次并发监控...")
        self.monitor_keywords_concurrent()
        
        schedule.every(interval_minutes).minutes.do(self.monitor_keywords_concurrent)
        
        print(f"\n🔄 定时任务已启动，下次执行在 {interval_minutes} 分钟后...")
        
        while self.is_running:
            try:
                schedule.run_pending()
                time.sleep(1)  
                
                if datetime.now().minute == 0:
                    new_interval = self.get_interval_minutes()
                    current_jobs = schedule.get_jobs()
                    if current_jobs and current_jobs[0].interval != timedelta(minutes=new_interval):
                        print(f"🕒 检测到时间段变化，调整执行间隔为 {new_interval} 分钟")
                        schedule.clear()
                        schedule.every(new_interval).minutes.do(self.monitor_keywords_concurrent)
                
            except KeyboardInterrupt:
                if self.is_shutting_down:
                    print("\n🛑 强制退出...")
                    break
                else:
                    self.signal_handler(signal.SIGINT, None)
            except Exception as e:
                print(f"❌ 调度器错误: {e}")
                time.sleep(1)


def main():
    keywords_config_file = os.path.join(user_dir, "keywords_config_simple.json")
    
    if not os.path.exists(keywords_config_file):
        print(f"❌ 关键词配置文件不存在: {keywords_config_file}")
        print("💡 请创建关键词文件")
        return
    
    webhook_urls = [
        "https://open.feishu.cn/open-apis/bot/v2/hook/72c2024f-8606-4813-984e-12793d3579a3",
        "https://open.feishu.cn/open-apis/bot/v2/hook/6de1d76f-278b-4b1d-bb68-d940a1a17da7"
    ]
    
    alert_webhook_url = "https://open.feishu.cn/open-apis/bot/v2/hook/72c2024f-8606-4813-984e-12793d3579a3"
    
    monitor = JDSKUMonitor(
        keywords_config_file, 
        webhook_urls=webhook_urls,
        alert_webhook_url=alert_webhook_url
    )
    
    monitor.start_scheduled_monitoring()

if __name__ == "__main__":
    print("京东SKU监控系统 - 即时通知及重试优化版")
    print("=" * 50)
    
    main()
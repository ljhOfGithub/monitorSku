from flask import Flask, request, jsonify
from flask_cors import CORS
from playwright.sync_api import sync_playwright
import time
import re
import json
import csv
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from urllib.parse import parse_qs, urlparse, quote
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import schedule
import threading
import signal
import sys
import subprocess
import random

app = Flask(__name__)
CORS(app)  # 允许跨域请求，以便油猴脚本可以调用

# ================= 配置区 =================
MONITOR_CONFIGS = [
    {
        "name": "22",
        "venderId": "10317338",
        "shopId": "10180819",
        "type": "2",
        "keywords_file": "C:\\Users\\yuhua\\Desktop\\rpa\\feishu\\monitor2\\keywords_config_simple.json",
        "root_dir": "C:\\data\\test\\2",
        "port": 9223,
        "webhook_urls": ["https://open.feishu.cn/open-apis/bot/v2/hook/422c57a3-6b1a-4372-98f4-64ffaae3550a"],
        "alert_webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/422c57a3-6b1a-4372-98f4-64ffaae3550a",
        "flask_port": 5001  # Flask服务端口
    },
    # {
    #     "name": "33",
    #     "venderId": "13303382",
    #     "shopId": "12594287",
    #     "type": "3",
    #     "keywords_file": "C:\\Users\\yuhua\\Desktop\\rpa\\feishu\\monitor2\\keywords_config_simple.json",
    #     "root_dir": "C:\\data\\test\\3",
    #     "port": 9223,
    #     "webhook_urls": ["https://open.feishu.cn/open-apis/bot/v2/hook/422c57a3-6b1a-4372-98f4-64ffaae3550a"],
    #     "alert_webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/422c57a3-6b1a-4372-98f4-64ffaae3550a",
    #     "flask_port": 5001  # Flask服务端口
    # }
]

PROXY_CONFIG = {
    "server": "q865.kdltps.com:15818",
    "username": "t16612090902574",
    "password": "2ow56b24"
}

# 存储各实例的监控器对象
monitor_instances = {}

class JDSKUMonitor:
    def __init__(self, config):
        self.config = config
        self.name = config['name']
        self.venderId = config['venderId']
        self.shopId = config['shopId']
        self.type_str = config['type']
        self.port = config['port']
        self.root_dir = config['root_dir']
        self.flask_port = config.get('flask_port', 5000)
        
        self.keywords_config_file = config['keywords_file']
        self.cookies_source = "none"
        self.webhook_urls = config['webhook_urls']
        self.alert_webhook_url = config['alert_webhook_url']
        
        self.all_skus_dir = os.path.join(self.root_dir, "all_skus")
        self.all_history_dir = os.path.join(self.root_dir, "all_history_with_brand")
        self.new_skus_records_dir = os.path.join(self.root_dir, "new_skus_records")
        self.monitor_results_file = os.path.join(self.root_dir, "monitor_results.json")
        
        self.monitor_type = self.name
        self.init_monitor_results()
        
        self.cookies_dicts = [{}]
        
        self.create_directories()
        
        self.is_running = True
        self.is_shutting_down = False
        self.current_monitor_data = {}
        self.has_sent_summary = False

        self.cached_historical_skus = set()
        self.sku_lock = threading.Lock()
        
        self.executor = ThreadPoolExecutor(max_workers=1)
        
        # 存储从油猴脚本接收的HTML内容
        self.html_cache = {}
        self.html_lock = threading.Lock()
        
        print(f"✅ [{self.name}] 监控器初始化完成，Flask端口: {self.flask_port}")
    
    def load_keywords_config(self):
        if not os.path.exists(self.keywords_config_file):
            print(f"❌ [{self.name}] JSON文件不存在: {self.keywords_config_file}")
            return []
        
        try:
            with open(self.keywords_config_file, 'r', encoding='utf-8') as f:
                keywords_config = json.load(f)
            print(f"✅ [{self.name}] 从JSON文件加载 {len(keywords_config)} 个关键词配置")
            return keywords_config
        except Exception as e:
            print(f"❌ [{self.name}] 加载JSON文件时出错: {e}")
            return []
    
    def create_directories(self):
        directories = [
            os.path.join(self.root_dir, "monitor_data"),
            os.path.join(self.root_dir, "monitor_logs"),
            os.path.join(self.root_dir, "product_details"),
            os.path.join(self.root_dir, "new_skus_records"),
            self.all_skus_dir,
            self.all_history_dir,
        ]
        
        for directory in directories:
            if not os.path.exists(directory):
                os.makedirs(directory)
                print(f"📁 [{self.name}] 创建文件夹: {directory}")
    
    def load_all_existing_skus(self):
        all_skus = set()
        
        history_main_dir = os.path.join(self.root_dir, "all_history_with_brand")
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
                        print(f"❌ [{self.name}] 加载 history 详情文件 {filename} 时出错: {e}")

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
                        print(f"❌ [{self.name}] 加载 SKU 历史文件 {filename} 时出错: {e}")

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
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ [{self.name}] 已保存新SKU记录到: {filename}")
    
    def get_keyword_historical_skus(self, keyword):
        return self.cached_historical_skus
    
    def save_product_details(self, keyword_config, product_links, all_skus, new_skus, timestamp):
        keyword = keyword_config['keyword']
        min_price = keyword_config['min_price']
        max_price = keyword_config['max_price']
        brand = keyword_config.get('brand', 'default')
        safe_keyword = re.sub(r'[^\w\u4e00-\u9fa5]', '_', keyword)
        
        details_filename = f"products_{safe_keyword}_{brand}_{min_price}_{max_price}.json"
        details_filepath = os.path.join(os.path.join(self.root_dir, "product_details"), details_filename)
        
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
        
        # with open(details_filepath, 'w', encoding='utf-8') as f:
        #     json.dump(details_data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ [{self.name}] 已保存商品详情到: {details_filename}")
        return product_links
    
    def load_monitor_results(self):
        if os.path.exists(self.monitor_results_file):
            try:
                with open(self.monitor_results_file, 'r', encoding='utf-8') as f:
                    self.monitor_results = json.load(f)
                print(f"📊 [{self.name}] 已加载历史监控结果")
            except Exception as e:
                print(f"❌ [{self.name}] 加载监控结果时出错: {e}")
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
                            "title": f"京东监控系统通知 - {self.name}",
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
                print(f"❌ [{self.name}] 飞书通知发送失败: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ [{self.name}] 飞书通知发送异常: {e}")
            return False
    
    def send_to_all_webhooks(self, message, is_post=False):
        if not self.webhook_urls:
            print(f"❌ [{self.name}] 未配置飞书webhook URL")
            return False
        
        success_count = 0
        for i, webhook_url in enumerate(self.webhook_urls, 1):
            if self.send_feishu_notification(message, webhook_url, is_post=is_post):
                success_count += 1
                print(f"✅ [{self.name}] 机器人 {i} 发送成功")
            else:
                print(f"❌ [{self.name}] 机器人 {i} 发送失败")
            time.sleep(1)
        
        print(f"📊 [{self.name}] 通知发送完成: {success_count}/{len(self.webhook_urls)} 个机器人成功")
        return success_count > 0
    
    def send_alert_notification(self, message):
        if not self.alert_webhook_url:
            print(f"❌ [{self.name}] 未配置警报webhook URL")
            return False
        
        alert_message = f"{message}"
        return self.send_feishu_notification(alert_message, self.alert_webhook_url)
    
    def generate_jd_deep_link(self, sku_id):
        target_url = f"https://item.m.jd.com/product/{sku_id}.html"
        params_dict = {"category": "jump", "des": "m", "url": target_url}
        encoded_params = quote(json.dumps(params_dict, separators=(',', ':')))
        deep_link_url = f"openapp.jdmobile://virtual?params={encoded_params}"
        return [{"tag": "a", "text": "点击立即购买", "href": deep_link_url}]
    
    def print_new_skus_to_console(self, keyword_config, new_products):
        if not new_products:
            return
        
        keyword = keyword_config['keyword']
        min_price = keyword_config['min_price']
        max_price = keyword_config['max_price']
        
        print(f"🎯 [{self.name}] 关键词 '{keyword}' 发现 {len(new_products)} 个新SKU:")
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
        
        print(f"📤 [{self.name}] 发送关键词 '{keyword}' 批量通知到 {len(self.webhook_urls)} 个机器人...")
        self.send_to_all_webhooks(post_content, is_post=True)
    
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
                            if is_hot_title:
                                continue
                            product_links.append({
                                'sku_id': sku_id,
                                'url': full_url,
                                'title': title[:100] + '...' if len(title) > 100 else title,
                                'is_main': True,
                                'extract_time': datetime.now().isoformat()
                            })
            
            except Exception as e:
                print(f"❌ [{self.name}] 提取商品信息时出错: {e}")
                continue
        
        return product_links
    
    # Flask端点：接收油猴脚本发送的HTML
    def setup_flask_endpoints(self):
        @app.route(f'/{self.name}/receive_html', methods=['POST'])
        def receive_html():
            data = request.json
            search_id = data.get('search_id')
            html_content = data.get('html_content')
            url = data.get('url')
            keyword = data.get('keyword')
            
            if not html_content or not search_id:
                return jsonify({'status': 'error', 'message': '缺少必要参数'}), 400
            
            with self.html_lock:
                self.html_cache[search_id] = {
                    'html': html_content,
                    'url': url,
                    'keyword': keyword,
                    'timestamp': datetime.now().isoformat()
                }
            
            print(f"✅ [{self.name}] 收到油猴脚本HTML，搜索ID: {search_id}, 关键词: {keyword}")
            return jsonify({'status': 'success', 'message': 'HTML接收成功'})
        
        @app.route(f'/{self.name}/get_search_task', methods=['GET'])
        def get_search_task():
            # 这里可以返回下一个要搜索的任务
            # 实际实现需要根据任务队列来
            return jsonify({'status': 'waiting', 'message': '暂无任务'})
        
        @app.route(f'/{self.name}/health', methods=['GET'])
        def health():
            return jsonify({'status': 'healthy', 'name': self.name, 'timestamp': datetime.now().isoformat()})
        
        # 新增端点：获取任务文件内容
        @app.route(f'/{self.name}/get_task_file', methods=['GET'])
        def get_task_file():
            task_file = os.path.join(self.root_dir, "search_task.json")
            
            if not os.path.exists(task_file):
                return jsonify({'status': 'error', 'message': '任务文件不存在'}), 404
            
            try:
                with open(task_file, 'r', encoding='utf-8') as f:
                    task_data = json.load(f)
                return jsonify(task_data)
            except Exception as e:
                return jsonify({'status': 'error', 'message': str(e)}), 500
        
        # 新增端点：删除任务文件
        @app.route(f'/{self.name}/delete_task_file', methods=['POST'])
        def delete_task_file():
            task_file = os.path.join(self.root_dir, "search_task.json")
            
            try:
                if os.path.exists(task_file):
                    os.remove(task_file)
                    print(f"🗑️  [{self.name}] 已删除任务文件")
                    return jsonify({'status': 'success', 'message': '文件已删除'})
                else:
                    return jsonify({'status': 'success', 'message': '文件不存在'})
            except Exception as e:
                print(f"❌ [{self.name}] 删除任务文件失败: {e}")
                return jsonify({'status': 'error', 'message': str(e)}), 500
        
        # 新增端点：获取任务（供油猴脚本使用）
        @app.route(f'/{self.name}/get_task', methods=['GET'])
        def get_task():
            """获取搜索任务"""
            task_file = os.path.join(self.root_dir, "search_task.json")
            
            if not os.path.exists(task_file):
                return jsonify({'status': 'waiting', 'message': '暂无任务'})
            
            try:
                with open(task_file, 'r', encoding='utf-8') as f:
                    task_data = json.load(f)
                
                # 检查任务是否过期（超过10分钟）
                request_time = datetime.fromisoformat(task_data.get('request_time', '2000-01-01'))
                if (datetime.now() - request_time).total_seconds() > 600:
                    print(f"⚠️  [{self.name}] 任务过期，删除: {task_file}")
                    os.remove(task_file)
                    return jsonify({'status': 'waiting', 'message': '任务已过期'})
                
                return jsonify({
                    'status': 'ready',
                    'search_id': task_data['search_id'],
                    'url': task_data['url'],
                    'keyword': task_data['keyword'],
                    'min_price': task_data['min_price'],
                    'max_price': task_data['max_price'],
                    'timestamp': task_data['timestamp']
                })
                
            except Exception as e:
                print(f"❌ [{self.name}] 读取任务文件失败: {e}")
                return jsonify({'status': 'error', 'message': str(e)})
    
    # 修改的搜索方法：使用油猴脚本获取HTML
    def search_jd_products(self, keyword_config, timestamp, browser_index=1):
        if not self.is_running:
            return []
            
        keyword = keyword_config['keyword']
        min_price = keyword_config['min_price']
        max_price = keyword_config['max_price']
        brand = keyword_config['brand']

        # 构建品牌字符串（与原始代码相同）
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

        ext_str = "&ext_attr=5522:90100"

        if self.type_str == "":
            suffix = ext_str
        else:
            suffix = ""
        
        # 构建搜索URL
        if min_price > 0 or max_price > 0:
            search_url = f"https://mall.jd.com/view_search-0-{self.venderId}-{self.shopId}-0-1-{min_price}-{max_price}-1-1-60.html?keyword={quote(quote(keyword, encoding='utf-8'), encoding='utf-8')}{suffix}&exp_brand={brand_str}"
            safe_keyword = re.sub(r'[^\w\u4e00-\u9fa5]', '_', keyword)
            original_url = f"https://mall.jd.com/view_search-0-{self.venderId}-{self.shopId}-0-1-{min_price}-{max_price}-1-1-60.html?keyword={safe_keyword}{suffix}&exp_brand={brand_str}"
        else:
            search_url = f"https://mall.jd.com/view_search-0-{self.venderId}-{self.shopId}-0-0-0-0-1-1-60.html?keyword={quote(keyword, encoding='utf-8')}{suffix}"
            safe_keyword = re.sub(r'[^\w\u4e00-\u9fa5]', '_', keyword)
            original_url = f"https://mall.jd.com/view_search-0-{self.venderId}-{self.shopId}-0-1-0-0-1-1-60.html?keyword={safe_keyword}{suffix}&exp_brand={brand_str}"
        
        # 生成唯一的搜索ID
        search_id = f"{self.name}_{keyword}_{min_price}_{max_price}_{timestamp}"
        
        print(f"🔍 [{self.name}] 请求油猴脚本搜索: {keyword}, ID: {search_id}")
        print(f"🌐 URL: {search_url}")
        
        # 清空旧的缓存
        with self.html_lock:
            if search_id in self.html_cache:
                del self.html_cache[search_id]
        
        # 通过本地文件传递任务（简单可靠）
        task_file = os.path.join(self.root_dir, "search_task.json")
        task_data = {
            'search_id': search_id,
            'url': search_url,
            'keyword': keyword,
            'min_price': min_price,
            'max_price': max_price,
            'timestamp': timestamp,
            'request_time': datetime.now().isoformat()
        }
        
        with open(task_file, 'w', encoding='utf-8') as f:
            json.dump(task_data, f, ensure_ascii=False, indent=2)
        
        print(f"📝 [{self.name}] 已写入搜索任务到文件: {task_file}")
        
        # 等待油猴脚本执行并返回HTML
        max_wait_time = 180  # 最大等待90秒
        wait_interval = 5
        total_wait = 0
        
        while total_wait < max_wait_time and self.is_running:
            with self.html_lock:
                if search_id in self.html_cache:
                    html_data = self.html_cache[search_id]
                    html_content = html_data['html']
                    
                    # 从缓存中移除
                    del self.html_cache[search_id]
                    
                    print(f"✅ [{self.name}] 成功获取HTML内容，长度: {len(html_content)} 字符")
                    
                    # 解析HTML获取商品链接
                    product_links = self.extract_main_product_links(html_content)
                    return product_links, search_url, original_url
            
            print(f"⏳ [{self.name}] 等待油猴脚本返回HTML... ({total_wait}/{max_wait_time}秒)")
            time.sleep(wait_interval)
            total_wait += wait_interval
        
        print(f"❌ [{self.name}] 等待油猴脚本超时，搜索ID: {search_id}")
        return [], search_url, original_url
    
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
            print(f"❌ [{self.name}] 搜索关键词 '{keyword}' (价格: {min_price}-{max_price}元) 在时间点 {datetime.now().isoformat(' ')} 未找到商品 搜索URL: {search_url}")
            return set(), [], set(), []
        
        all_skus = set(product['sku_id'] for product in product_links)
        historical_skus = self.get_keyword_historical_skus(keyword)
        
        new_skus_for_keyword = all_skus - historical_skus
        new_products_for_keyword = [p for p in product_links if p['sku_id'] in new_skus_for_keyword]
        
        self.save_keyword_skus(keyword_config, all_skus, timestamp)
        self.save_new_skus_record(keyword_config, new_skus_for_keyword, timestamp)
        self.save_product_details(keyword_config, product_links, all_skus, new_skus_for_keyword, timestamp)
        
        if new_skus_for_keyword:
            print(f"🔔  [{self.name}] 搜索关键词 '{keyword}' 在时间点 {datetime.now().isoformat(' ')} 找到 {len(all_skus)} 个SKU 发现 {len(new_skus_for_keyword)} 个新SKU，立即发送通知... 搜索URL: {search_url}")
            self.send_keyword_new_skus_notification(keyword_config, new_products_for_keyword)
            self.update_keyword_stats(keyword_config, len(new_skus_for_keyword))

            print(f"🚀 [即时触发] [{self.name}] 关键词 '{keyword}' 发现新SKU，正在运行过滤脚本...")
            # self.run_filter_by_history_script()
        else:
            print(f"ℹ️  [{self.name}] 搜索关键词 '{keyword}' (价格: {min_price}-{max_price}元) 在时间点 {datetime.now().isoformat(' ')} 找到 {len(all_skus)} 个SKU 没有新SKU 搜索URL: {search_url}")
        
        return all_skus, product_links, new_skus_for_keyword, new_products_for_keyword
    
    def process_keyword_with_browser(self, args):
        if not self.is_running:
            return set(), [], set(), []
            
        keyword_config, timestamp, browser_index = args
        return self.process_single_keyword(keyword_config, timestamp, browser_index)
    
    def send_monitor_summary_notification(self, monitor_data):
        if not monitor_data.get('total_new_skus'):
            self.send_alert_notification(f"ℹ️  {self.monitor_type}本轮监控没有发现新SKU")
            print(f"ℹ️  [{self.name}] 没有新SKU，不发送总结通知")
            return
        
        keyword_details_with_new_skus = {}
        for keyword, details in monitor_data.get('keyword_new_skus_details', {}).items():
            if details['new_skus']:
                keyword_details_with_new_skus[keyword] = details
        
        if not keyword_details_with_new_skus:
            self.send_alert_notification(f"ℹ️  {self.monitor_type}没有包含新SKU的关键词")
            print(f"ℹ️  [{self.name}] 没有包含新SKU的关键词，不发送总结通知")
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
        
        print(f"📤 [{self.name}] 发送监控总结通知...")
        self.send_feishu_notification(post_content, self.alert_webhook_url, is_post=True)
        self.has_sent_summary = True
    
    def get_interval_minutes(self):
        now = datetime.now()
        current_hour = now.hour
        
        if (7 <= current_hour <= 24):
            return random.randint(5, 10)
        else:
            return 1 * 60
    
    def run_filter_by_history_script(self):
        script_path = r"C:\Users\yuhua\Desktop\rpa\proxy\filter_by_history_with_brand.py"
        
        if not os.path.exists(script_path):
            print(f"❌ [{self.name}] 找不到脚本文件: {script_path}")
            return False
        
        print(f"🚀 [{self.name}] 开始运行过滤脚本: {script_path}")
        try:
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                errors='replace'
            )
            
            if result.returncode == 0:
                print(f"✅ [{self.name}] 过滤脚本执行成功")
                return True
            else:
                print(f"❌ [{self.name}] 过滤脚本执行失败，返回码: {result.returncode}")
                print(f"错误输出: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print(f"❌ [{self.name}] 过滤脚本执行超时")
            return False
        except Exception as e:
            print(f"❌ [{self.name}] 运行过滤脚本时出错: {e}")
            return False
    
    def monitor_keywords_concurrent(self):
        keywords_config = self.load_keywords_config()
        if not keywords_config:
            print(f"❌ [{self.name}] 没有加载到关键词配置，跳过本次监控")
            return
        
        self.keywords_config = keywords_config
        process_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        print("\n" + "="*60)
        print(f"🕒 [{self.name}] 开始并发监控任务")
        print(f"⏰ 执行时间戳: {process_timestamp}")
        print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📝 配置关键词: {len(self.keywords_config)} 个")
        print("="*60)
        
        with self.sku_lock:
            print(f"📁 [{self.name}] 正在加载历史 SKU 记录...")
            self.cached_historical_skus = self.load_all_existing_skus()
            print(f"✅ [{self.name}] 历史 SKU 加载完成，共 {len(self.cached_historical_skus)} 个")
        
        total_new_skus = set()
        total_new_products = []
        keyword_new_skus_details = {}
        monitor_start_time = datetime.now()
        
        pending_tasks = []
        for i, config in enumerate(self.keywords_config):
            pending_tasks.append((config, i + 1))
            
        while pending_tasks and self.is_running:
            print(f"🔄 [{self.name}] 当前池子剩余任务数: {len(pending_tasks)}")
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
                        print(f"⚠️ [{self.name}] 关键词 '{keyword}' 返回空结果，重新放入池子")
                        pending_tasks.append((config_info, idx))
                except Exception as e:
                    print(f"❌ [{self.name}] 关键词 '{keyword}' 处理异常: {e}。即将重新尝试...")
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
        
        print(f"\n✅ [{self.name}] 本轮并发监控任务全部完成，共发现 {len(total_new_skus)} 个新SKU")
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
        print(f"📊 [{self.name}] 创建新的监控结果")
    
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
        log_file = os.path.join(self.root_dir, "monitor_logs", f"monitor_{datetime.now().strftime('%Y%m%d')}.log")
        
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
        
        print(f"⏰ [{self.name}] 启动定时监控")
        print(f"📝 [{self.name}] 配置关键词文件: {self.keywords_config_file}")
        print(f"⏱️  [{self.name}] 当前时间段 ({current_hour}点): 执行间隔 {interval_minutes} 分钟")
        print(f"💾 [{self.name}] 按 Ctrl+C 可以安全退出程序")
        print(f"🛑 [{self.name}] 再次按 Ctrl+C 强制退出所有进程")
        
        print(f"\n🚀 [{self.name}] 开始第一次并发监控...")
        self.monitor_keywords_concurrent()
        
        schedule.every(interval_minutes).minutes.do(self.monitor_keywords_concurrent)
        
        print(f"\n🔄 [{self.name}] 定时任务已启动，下次执行在 {interval_minutes} 分钟后...")
        
        while self.is_running:
            try:
                schedule.run_pending()
                time.sleep(1)
                
                if datetime.now().minute == 0:
                    new_interval = self.get_interval_minutes()
                    current_jobs = schedule.get_jobs()
                    instance_jobs = [job for job in current_jobs if job.job_func.__name__ == 'monitor_keywords_concurrent']
                    if instance_jobs and instance_jobs[0].interval != timedelta(minutes=new_interval):
                        print(f"🕒 [{self.name}] 检测到时间段变化，调整执行间隔为 {new_interval} 分钟")
                        schedule.clear()
                        schedule.every(new_interval).minutes.do(self.monitor_keywords_concurrent)
                
            except Exception as e:
                print(f"❌ [{self.name}] 调度器错误: {e}")
                time.sleep(1)

def run_flask_server(monitor):
    """运行Flask服务器"""
    print(f"🌐 [{monitor.name}] 启动Flask服务器，端口: {monitor.flask_port}")
    app.run(host='127.0.0.1', port=monitor.flask_port, threaded=True, debug=False, use_reloader=False)

def run_monitor_instance(config):
    """运行监控实例"""
    monitor = JDSKUMonitor(config)
    
    # 设置Flask端点
    monitor.setup_flask_endpoints()
    
    # 将监控器存储到全局字典
    monitor_instances[config['name']] = monitor
    
    # 在新线程中启动Flask服务器
    flask_thread = threading.Thread(target=run_flask_server, args=(monitor,), daemon=True)
    flask_thread.start()
    
    # 等待Flask服务器启动
    time.sleep(3)
    
    # 启动定时监控
    monitor.start_scheduled_monitoring()

def main():
    # 注册全局信号处理
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    
    threads = []
    
    for config in MONITOR_CONFIGS:
        if not os.path.exists(config['keywords_file']):
            print(f"⚠️  警告: [{config['name']}] 关键词文件不存在: {config['keywords_file']}，跳过此配置")
            continue
        
        t = threading.Thread(target=run_monitor_instance, args=(config,), name=config['name'])
        t.daemon = True
        threads.append(t)
        t.start()
        print(f"🚀 已启动监控实例: {config['name']} (Flask端口: {config.get('flask_port', 5000)})")
        time.sleep(5)  # 间隔启动
    
    # 保持主线程运行
    try:
        while True:
            time.sleep(1)
            if not any(t.is_alive() for t in threads):
                break
    except KeyboardInterrupt:
        print("\n👋 主程序被用户中断")

if __name__ == "__main__":
    print("京东SKU监控系统 - 油猴脚本 + Python后端版")
    print("=" * 60)
    main()
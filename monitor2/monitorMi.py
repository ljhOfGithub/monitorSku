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

# 修改：去掉了本地chrome目录列表，改为空配置
chrome_dirs = []
root_dir = "/Volumes/data"
user_dir = "/Volumes/Users/yuhua/Desktop/rpa/feishu/monitor2"
class JDSKUMonitor:
    def __init__(self, keywords_config_file, webhook_urls=None, alert_webhook_url=None):
        """
        初始化监控器
        
        Args:
            keywords_config_file: 关键词配置JSON文件路径
            webhook_urls: 飞书机器人webhook URL列表
            alert_webhook_url: 警报机器人webhook URL
        """
        self.keywords_config_file = keywords_config_file
        # 固定使用内存浏览器模式，不再从本地读取cookies
        self.cookies_source = "none"
        self.webhook_urls = webhook_urls or []
        self.alert_webhook_url = alert_webhook_url
        
        # 使用 root_dir 格式配置路径
        self.all_skus_dir = os.path.join(root_dir, "all_skus")
        self.new_skus_records_dir = os.path.join(root_dir, "new_skus_records")
        self.monitor_results_file = os.path.join(root_dir, "monitor_results.json")
        
        self.monitor_type = "已赚钱类"
        # 先初始化监控结果，防止后续访问失败
        self.init_monitor_results()
        
        # 不再加载外部cookies
        self.cookies_dicts = [{}]
        
        # 创建数据文件夹
        self.create_directories()
        
        # # 然后加载监控结果（可能会覆盖初始化的结果）
        # self.load_monitor_results()
        
        # 设置信号处理，用于优雅退出
        self.is_running = True
        self.is_shutting_down = False  # 标记是否正在关闭
        self.current_monitor_data = {}  # 存储当前监控周期的数据
        self.has_sent_summary = False  # 标记是否已发送总结报告
        
        # 设置信号处理
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # 创建线程池执行器 - 使用默认并发数
        self.executor = ThreadPoolExecutor(max_workers=5)
    
    def load_keywords_config(self):
        """从JSON文件加载关键词配置"""
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
        """根据配置加载cookies"""
        return [{}]
    
    def load_cookies_from_browsers(self, user_data_dirs):
        """从多个浏览器用户数据目录获取cookies"""
        return [{}]
    
    def load_cookies_from_file(self, cookies_file):
        """从文件加载cookies字符串并解析为字典"""
        return {}
    
    def parse_cookies_string(self, cookies_string):
        """解析cookies字符串为字典"""
        cookies_dict = {}
        try:
            # 分割cookies字符串
            cookies_list = cookies_string.split(';')
            for cookie in cookies_list:
                cookie = cookie.strip()
                if '=' in cookie:
                    key, value = cookie.split('=', 1)
                    cookies_dict[key.strip()] = value.strip()
            
            print(f"✅ 成功解析 {len(cookies_dict)} 个cookies")
            
            # 打印关键cookies信息
            if 'pt_key' in cookies_dict:
                print(f"🔑 pt_key: {cookies_dict['pt_key'][:20]}...")
            if 'pt_pin' in cookies_dict:
                print(f"🔑 pt_pin: {cookies_dict['pt_pin']}")
            
            return cookies_dict
            
        except Exception as e:
            print(f"❌ 解析cookies字符串时出错: {e}")
            return {}
    
    def signal_handler(self, signum, frame):
        """处理退出信号"""
        if self.is_shutting_down:
            print("\n🛑 强制退出...")
            os._exit(1)
            
        print(f"\n\n⚠️  收到退出信号，正在保存数据...")
        self.is_running = False
        self.is_shutting_down = True
        
        # 关闭线程池
        print("🛑 停止所有任务...")
        self.executor.shutdown(wait=False)
        
        # 只有在没有发送总结报告时才发送
        if not self.has_sent_summary and hasattr(self, 'current_monitor_data') and self.current_monitor_data:
            print("📤 发送未完成的监控总结通知...")
            self.send_alert_notification(self.current_monitor_data)
            self.has_sent_summary = True
        
        # self.save_monitor_results()
        # print("✅ 数据保存完成，程序退出")
        
        # 给用户一次正常退出的机会
        print("💡 再次按 Ctrl+C 强制退出")
        
        # 设置3秒后强制退出
        threading.Timer(3.0, os._exit, [0]).start()
    
    def create_directories(self):
        """创建所有必要的文件夹"""
        # 使用 root_dir 格式配置路径
        root_dir = "/Volumes/data"
        directories = [
            os.path.join(root_dir, "monitor_data"),
            os.path.join(root_dir, "monitor_logs"), 
            # os.path.join(root_dir, "search_pages"),
            os.path.join(root_dir, "product_details"),
            os.path.join(root_dir, "new_skus_records"),
            self.all_skus_dir,
        ]
        
        for directory in directories:
            if not os.path.exists(directory):
                os.makedirs(directory)
                print(f"📁 创建文件夹: {directory}")
    
    def load_all_existing_skus(self):
        """加载所有已存在的SKU（从文件夹中扫描）"""
        all_skus = set()
        
        for filename in os.listdir(self.all_skus_dir):
            if filename.endswith(".json"):
                filepath = os.path.join(self.all_skus_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        skus = data.get('skus', [])
                        all_skus.update(skus)
                except Exception as e:
                    print(f"❌ 加载SKU文件 {filename} 时出错: {e}")

        for filename in os.listdir(self.new_skus_records_dir):
            if filename.endswith(".json"):
                filepath = os.path.join(self.new_skus_records_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        skus = data.get('new_skus', [])
                        all_skus.update(skus)
                except Exception as e:
                    print(f"❌ 加载SKU文件 {filename} 时出错: {e}")
        # print(f"📁 已加载 {len(all_skus)} 个现有SKU")
        return all_skus
    
    def save_keyword_skus(self, keyword, skus, timestamp):
        """保存关键词的SKU到文件"""
        safe_keyword = re.sub(r'[^\w\u4e00-\u9fa5]', '_', keyword)
        filename = f"{safe_keyword}_{timestamp}.json"
        filepath = os.path.join(self.all_skus_dir, filename)
        
        data = {
            'keyword': keyword,
            'skus': list(skus),
            'search_time': datetime.now().isoformat(),
            'timestamp': timestamp,
            'total_skus': len(skus)
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # print(f"💾 关键词 '{keyword}' 的SKU已保存: {filename}")
    
    def save_new_skus_record(self, keyword_config, new_skus, timestamp):
        """保存新发现的SKU记录（即使没有找到）"""
        keyword = keyword_config['keyword']
        min_price = keyword_config['min_price']
        max_price = keyword_config['max_price']
        safe_keyword = re.sub(r'[^\w\u4e00-\u9fa5]', '_', keyword)
        
        if min_price > 0 or max_price > 0:
            filename = f"new_skus_{safe_keyword}_{min_price}_{max_price}_{timestamp}.json"
        else:
            filename = f"new_skus_{safe_keyword}_{timestamp}.json"
        
        filepath = os.path.join(self.new_skus_records_dir, filename)
        
        data = {
            'keyword': keyword,
            'min_price': min_price,
            'max_price': max_price,
            'search_time': datetime.now().isoformat(),
            'timestamp': timestamp,
            'new_skus_count': len(new_skus),
            'new_skus': list(new_skus),
            'has_new_skus': len(new_skus) > 0
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # print(f"💾 新SKU记录已保存: {filename}")
    
    def get_keyword_historical_skus(self, keyword):
        # """获取关键词的历史SKU（扫描所有相关文件）"""
        # safe_keyword = re.sub(r'[^\w\u4e00-\u9fa5]', '_', keyword)
        # historical_skus = set()
        
        # for filename in os.listdir(self.all_skus_dir):
        #     if filename.endswith(".json"):
        #         filepath = os.path.join(self.all_skus_dir, filename)
        #         try:
        #             with open(filepath, 'r', encoding='utf-8') as f:
        #                 data = json.load(f)
        #                 skus = data.get('skus', [])

        #                 historical_skus.update(skus)
        #         except Exception as e:
        #             print(f"❌ 加载历史SKU文件 {filename} 时出错: {e}")
        
        # return historical_skus
        return self.load_all_existing_skus()
    
    def save_search_page(self, keyword, min_price, max_price, html_content, timestamp):
        """保存搜索页面HTML"""
        safe_keyword = re.sub(r'[^\w\u4e00-\u9fa5]', '_', keyword)
        
        if min_price > 0 or max_price > 0:
            filename = f"search_{safe_keyword}_{min_price}_{max_price}_{timestamp}.html"
        else:
            filename = f"search_{safe_keyword}_{timestamp}.html"
        
        # 使用 root_dir 格式配置路径
        root_dir = "/Volumes/data"
        search_pages_dir = os.path.join(root_dir, "search_pages")
        # if not os.path.exists(search_pages_dir):
        #     os.makedirs(search_pages_dir)
        
        filepath = os.path.join(search_pages_dir, filename)
        
        # with open(filepath, 'w', encoding='utf-8') as f:
        #     f.write(html_content)
        
        # print(f"💾 搜索页面已保存: {filename}")
        return filepath
    
    def save_product_details(self, keyword_config, product_links, all_skus, new_skus, timestamp):
        """保存商品详细信息"""
        keyword = keyword_config['keyword']
        min_price = keyword_config['min_price']
        max_price = keyword_config['max_price']
        safe_keyword = re.sub(r'[^\w\u4e00-\u9fa5]', '_', keyword)
        
        # 保存商品详情JSON
        if min_price > 0 or max_price > 0:
            details_filename = f"products_{safe_keyword}_{min_price}_{max_price}_{timestamp}.json"
        else:
            details_filename = f"products_{safe_keyword}_{timestamp}.json"
        
        # 使用 root_dir 格式配置路径
        root_dir = "/Volumes/data"
        product_details_dir = os.path.join(root_dir, "product_details")
        if not os.path.exists(product_details_dir):
            os.makedirs(product_details_dir)
        
        details_filepath = os.path.join(product_details_dir, details_filename)
        
        details_data = {
            'keyword': keyword,
            'min_price': min_price,
            'max_price': max_price,
            'search_time': datetime.now().isoformat(),
            'timestamp': timestamp,
            'total_products': len(product_links),
            'total_skus': len(all_skus),
            'new_skus': len(new_skus),
            'products': product_links,
            'all_skus': list(all_skus),
            'new_skus_list': list(new_skus)
        }
        
        with open(details_filepath, 'w', encoding='utf-8') as f:
            json.dump(details_data, f, ensure_ascii=False, indent=2)
        
        # print(f"💾 商品详情已保存: {details_filename}")
        return product_links
    
    def load_monitor_results(self):
        """加载监控结果"""
        if os.path.exists(self.monitor_results_file):
            try:
                with open(self.monitor_results_file, 'r', encoding='utf-8') as f:
                    self.monitor_results = json.load(f)
                print(f"📊 已加载历史监控结果")
            except Exception as e:
                print(f"❌ 加载监控结果时出错: {e}")
                # 如果加载失败，使用初始化结果
                self.init_monitor_results()
        else:
            self.init_monitor_results()
    
    def save_monitor_results(self):
        """保存监控结果"""
        with open(self.monitor_results_file, 'w', encoding='utf-8') as f:
            json.dump(self.monitor_results, f, ensure_ascii=False, indent=2)
        # print("💾 监控结果已保存")
    
    def send_feishu_notification(self, message, webhook_url):
        """发送飞书通知到指定机器人"""
        if not webhook_url:
            return False
        
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
    
    def send_to_all_webhooks(self, message):
        """发送通知到所有机器人"""
        if not self.webhook_urls:
            print("❌ 未配置飞书webhook URL")
            return False
        
        success_count = 0
        for i, webhook_url in enumerate(self.webhook_urls, 1):
            if self.send_feishu_notification(message, webhook_url):
                success_count += 1
                print(f"✅ 机器人 {i} 发送成功")
            else:
                print(f"❌ 机器人 {i} 发送失败")
            time.sleep(1)  # 机器人间延迟
        
        print(f"📊 通知发送完成: {success_count}/{len(self.webhook_urls)} 个机器人成功")
        return success_count > 0
    
    def send_alert_notification(self, message):
        """发送警报通知到专门的警报机器人"""
        if not self.alert_webhook_url:
            print("❌ 未配置警报webhook URL")
            return False
        
        # alert_message = f"🚨 京东监控系统警报\n\n{message}"
        alert_message = f"{message}"
        return self.send_feishu_notification(alert_message, self.alert_webhook_url)
    
    def print_new_skus_to_console(self, keyword_config, new_products):
        """将新SKU信息打印到控制台"""
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
        """立即发送新SKU通知（每发现一个就发送）"""
        if not new_products:
            return
        
        keyword = keyword_config['keyword']
        min_price = keyword_config['min_price']
        max_price = keyword_config['max_price']
        
        # 为每个新SKU发送单独的通知
        for product in new_products:
            sku = product['sku_id']
            title = product.get('title', '未知')
            
            message = f"🚨 发现新SKU！\n\n"
            message += f"📊 关键词: {keyword}\n"
            if min_price > 0 or max_price > 0:
                message += f"💰 价格范围: {min_price}-{max_price}元\n"
            message += f"🆕 新SKU: {sku}\n"
            message += f"📦 标题: {title}\n"
            message += f"💰 支付链接: https://trade.m.jd.com/checkout?commlist={sku},,1#/index\n"
            message += f"🔗 详情链接: https://item.m.jd.com/product/{sku}.html\n"
            message += f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            # print(f"📤 立即发送新SKU通知: {sku}")
            # self.send_to_all_webhooks(message)
            
            # 单个SKU通知间短暂延迟
            time.sleep(2)
    
    def send_keyword_new_skus_notification(self, keyword_config, new_products):
        """发送关键词级别的新SKU通知"""
        if not new_products:
            return
        
        # 先打印到控制台
        self.print_new_skus_to_console(keyword_config, new_products)
        
        # 立即发送每个新SKU的单独通知
        self.send_immediate_new_sku_notification(keyword_config, new_products)
        
        # 同时发送该关键词的批量通知
        keyword = keyword_config['keyword']
        min_price = keyword_config['min_price']
        max_price = keyword_config['max_price']
        
        message = f"⚠️⚠️⚠️ {self.monitor_type}京东商品监控通知\n"
        message += f"📊 关键词: {keyword}\n"
        if min_price > 0 or max_price > 0:
            message += f"💰 价格范围: {min_price}-{max_price}元\n"
        message += f"🆕 发现新SKU: {len(new_products)} 个\n"
        message += f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        # 添加所有新商品链接和详情
        # message += "📦 所有新商品详情:\n"
        for i, product in enumerate(new_products, 1):
            sku = product['sku_id']
            title = product.get('title', '未知')
            
            message += f"{i}. 支付链接: https://trade.m.jd.com/checkout?commlist={sku},,1#/index\n"
            message += f"     详情链接: https://item.m.jd.com/product/{sku}.html\n"
            message += f"标题: {title}\n"
            message += f"SKU: {sku}\n"
            message += "\n"
        
        print(f"📤 发送关键词 '{keyword}' 批量通知到 {len(self.webhook_urls)} 个机器人...")
        self.send_to_all_webhooks(message)
    
    def check_login_status(self, page_content):
        """检查用户登录状态"""
        user_indicators = [
            '我的京东', '我的订单', '用户中心', '个人中心', '我的资产',
            'class="user"', 'id="user"', '会员中心', 'nickname', 'user-info'
        ]
        
        has_user_info = any(indicator in page_content for indicator in user_indicators)
        return has_user_info
    
    def check_cookies_validity(self, page, browser_index=1):
        """检查cookies是否过期"""
        return True
    
    def create_browser_context(self, playwright, browser_index=1):
        """创建浏览器上下文"""
        # 统一使用无状态浏览器模式
        browser = playwright.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-features=VizDisplayCompositor',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding'
            ]
        )
        
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            extra_http_headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            }
        )
        
        # 隐藏自动化特征
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });
        """)
        
        return context
    
    def remove_hot_sale_products(self, html_content):
        """从HTML中移除热销商品部分"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 移除热销商品容器
        hot_sale_sections = soup.find_all('div', class_=['jHotSale', 'hot-sale', 'hot-product'])
        for section in hot_sale_sections:
            section.decompose()
        
        return str(soup)
    
    def extract_main_product_links(self, html_content):
        """提取主商品链接和价格信息"""
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
                            
                            # 检查是否热销商品
                            desc_div = product.find('div', class_='jDesc')
                            title = "未知商品"
                            if desc_div and desc_div.find('a'):
                                title = desc_div.find('a').get_text(strip=True)
                            
                            title_lower = title.lower()
                            hot_keywords = ['热销', '热卖', '爆款', '热门', 'hot', '平板', '笔记本', '显示屏', '电脑', '键盘', 'pad', '路由']
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
        """搜索京东商品并提取SKU"""
        # 检查是否正在关闭
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
            brand_str = '%25E4%25B8%2580%25E5%258A%25A0'
        elif brand == 'realme':
            brand_str = '%25E7%259C%259F%25E6%2588%2591%25EF%25BC%2588realme%25EF%25BC%2589'
        elif brand == 'vivo' or brand == 'iqoo':
            brand_str = 'vivo'
        # 构建搜索URL
        if min_price > 0 or max_price > 0:
            search_url = f"https://mall.jd.com/view_search-652812-1000080442-1000080442-0-1-{min_price}-{max_price}-1-1-60.html?keyword={quote(quote(keyword, encoding='utf-8'), encoding='utf-8')}&ext_attr=5522:90100&exp_brand={brand_str}"
            safe_keyword = re.sub(r'[^\w\u4e00-\u9fa5]', '_', keyword)
            original_url = f"https://mall.jd.com/view_search-652812-1000080442-1000080442-0-1-{min_price}-{max_price}-1-1-60.html?keyword={safe_keyword}&ext_attr=5522:90100&exp_brand={brand_str}"
        else:
            search_url = f"https://mall.jd.com/view_search-652812-1000080442-1000080442-0-0-0-0-1-1-60.html?keyword={quote(keyword, encoding='utf-8')}"
            safe_keyword = re.sub(r'[^\w\u4e00-\u9fa5]', '_', keyword)
            original_url = f"https://mall.jd.com/view_search-652812-1000080442-1000080442-0-1-0-0-1-1-60.html?keyword={safe_keyword}&ext_attr=5522:90100&exp_brand={brand_str}"
        
        # print(f"🌐 浏览器 {browser_index} 搜索关键词: {keyword} 搜索URL: {search_url}")
        
        with sync_playwright() as p:
            # 使用浏览器上下文
            context = self.create_browser_context(p, browser_index)
            page = context.new_page()
            
            try:
                # print(f"🔍 浏览器 {browser_index} 搜索关键词: {keyword} (价格: {min_price}-{max_price}元)\n")
                # if min_price > 0 or max_price > 0:
                #     print(f" (价格: {min_price}-{max_price}元)")
                # else:
                #     print()
                    
                page.goto(search_url, timeout=60000, wait_until='networkidle')
                
                # 等待商品列表加载
                try:
                    page.wait_for_selector('.jSearchList-792077 li.jSubObject', timeout=15000)
                    has_empty_message = False
                    try:
                        # 设置较短的超时时间快速检查
                        empty_selector = '.jMessageError'
                        has_empty_message = page.locator(empty_selector).count() > 0
                    except:
                        pass
                    
                    # 如果检测到空结果提示，直接返回空列表
                    if has_empty_message:
                        # print(f"ℹ️  浏览器 {browser_index} 关键词 '{keyword}' 没有找到相关商品，返回空结果")
                        # 保存搜索页面HTML
                        html_content = page.content()
                        self.save_search_page(keyword, min_price, max_price, html_content, timestamp)
                        return [], search_url, original_url
                except:
                    # page.wait_for_selector('.gl-item, .jSubObject', timeout=15000)
                    pass
                                    
                # 滚动页面
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2)
                
                # 获取页面内容
                html_content = page.content()
                
                # 保存搜索页面HTML
                self.save_search_page(keyword, min_price, max_price, html_content, timestamp)
                
                # 提取商品链接
                product_links = self.extract_main_product_links(html_content)
                
                # print(f"✅ 浏览器 {browser_index} 关键词 '{keyword}' 找到 {len(product_links)} 个商品")
                return product_links, search_url, original_url
                
            except Exception as e:
                print(f"❌ 浏览器 {browser_index} 搜索关键词 '{keyword}' 搜索URL: {search_url} 时出错: {e}")
                return []
            finally:
                context.close()
    
    def process_single_keyword(self, keyword_config, timestamp, browser_index=1):
        """处理单个关键词并立即发送通知"""
        # 检查是否正在关闭
        if not self.is_running:
            return set(), []
            
        keyword = keyword_config['keyword']
        min_price = keyword_config['min_price']
        max_price = keyword_config['max_price']
        
        # print(f"\n🎯 浏览器 {browser_index} 开始处理关键词: {keyword}", end="")
        # if min_price > 0 or max_price > 0:
        #     print(f" (价格: {min_price}-{max_price}元)")
        # else:
        #     print()
        
        # 搜索商品
        search_result = self.search_jd_products(keyword_config, timestamp, browser_index)
        if not search_result:
            return set(), [], set(), []
        
        product_links, search_url, original_url = search_result
        
        if not product_links:
            print(f"❌ 浏览器 {browser_index} 搜索关键词 '{keyword}' (价格: {min_price}-{max_price}元) 在时间点 {datetime.now().isoformat(' ')} 未找到商品 搜索URL: {search_url}")
            return set(), [], set(), []
        
        # 提取主商品SKU
        all_skus = set(product['sku_id'] for product in product_links)
        # print(f"📦 浏览器 {browser_index} 搜索关键词: '{keyword}' (价格: {min_price}-{max_price}元) 在时间点 {datetime.now().isoformat(' ')} 找到 {len(all_skus)} 个SKU 搜索URL: {search_url}")
        
        # 获取该关键词的历史SKU
        historical_skus = self.get_keyword_historical_skus(keyword)
        # print(f"📊 关键词 '{keyword}' 历史SKU数量: {len(historical_skus)}")
        
        # 计算新SKU（相对于该关键词的历史数据）
        new_skus_for_keyword = all_skus - historical_skus
        new_products_for_keyword = [p for p in product_links if p['sku_id'] in new_skus_for_keyword]
        
        # 保存当前搜索的SKU
        self.save_keyword_skus(keyword, all_skus, timestamp)
        
        # 保存新SKU记录（即使没有找到）
        self.save_new_skus_record(keyword_config, new_skus_for_keyword, timestamp)
        
        # 保存商品详细信息
        self.save_product_details(keyword_config, product_links, all_skus, new_skus_for_keyword, timestamp)
        
        # 使用关键词级别的新SKU进行通知（立即发送）
        if new_skus_for_keyword:
            print(f"🔔  浏览器 {browser_index} 搜索关键词 '{keyword}' 在时间点 {datetime.now().isoformat(' ')} 找到 {len(all_skus)} 个SKU 发现 {len(new_skus_for_keyword)} 个新SKU，立即发送通知... 搜索URL: {search_url}")
            # 立即发送通知
            self.send_keyword_new_skus_notification(keyword_config, new_products_for_keyword)
            
            # 更新监控统计
            self.update_keyword_stats(keyword_config, len(new_skus_for_keyword))
        else:
            print(f"ℹ️  浏览器 {browser_index} 搜索关键词 '{keyword}' (价格: {min_price}-{max_price}元) 在时间点 {datetime.now().isoformat(' ')} 找到 {len(all_skus)} 个SKU 没有新SKU 搜索URL: {search_url}")
        
        return all_skus, product_links, new_skus_for_keyword, new_products_for_keyword
    
    def process_keyword_with_browser(self, args):
        """使用指定浏览器处理关键词"""
        # 检查是否正在关闭
        if not self.is_running:
            return set(), [], set(), []
            
        keyword_config, timestamp, browser_index = args
        return self.process_single_keyword(keyword_config, timestamp, browser_index)
    
    def send_monitor_summary_notification(self, monitor_data):
        """发送监控总结通知"""
        if not monitor_data.get('total_new_skus'):
            self.send_alert_notification(f"ℹ️  {self.monitor_type}本轮监控没有发现新SKU")
            print("ℹ️  没有新SKU，不发送总结通知")
            return
        
        # 过滤掉没有新SKU的关键词
        keyword_details_with_new_skus = {}
        for keyword, details in monitor_data.get('keyword_new_skus_details', {}).items():
            if details['new_skus']:
                keyword_details_with_new_skus[keyword] = details
        
        if not keyword_details_with_new_skus:
            # self.send_to_all_webhooks(f"ℹ️  {self.monitor_type}没有包含新SKU的关键词")
            self.send_alert_notification(f"ℹ️  {self.monitor_type}没有包含新SKU的关键词")
            print("ℹ️  没有包含新SKU的关键词，不发送总结通知")
            return
        
        message = f"{self.monitor_type}监控任务完成总结\n"
        message += f"⏰ 开始时间: {monitor_data.get('process_timestamp')}\n"
        message += f"⏰ 结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        # message += f"📊 处理关键词: {len(self.keywords_config)} 个\n"
        message += f"🆕 发现新SKU的关键词: {len(keyword_details_with_new_skus)} 个\n"
        message += f"🆕 总共发现新SKU: {len(monitor_data['total_new_skus'])} 个\n"
        # message += f"📁 历史SKU数量: {monitor_data.get('all_existing_skus_count', 0)} 个\n"
        
        # 添加每个有新SKU的关键词的详细统计和新SKU链接
        message += "📋 发现新SKU的关键词详情:\n"
        for keyword, details in keyword_details_with_new_skus.items():
            message += f"   - {keyword}({details['min_price']}-{details['max_price']}元): {len(details['new_skus'])}个新SKU (总共: {details['total_skus']} 个)\n"
            
            # 显示新SKU的具体链接
            if details['new_skus']:
                message += f"     新SKU链接: "
                for sku in details['new_skus']:
                    # 查找对应的商品信息
                    product_info = None
                    for product in details.get('new_products', []):
                        if product['sku_id'] == sku:
                            product_info = product
                            break
                    
                    if product_info:
                        title = product_info.get('title', '未知商品')
                        message += f"支付链接:   https://trade.m.jd.com/checkout?commlist={sku},,1#/index - {title}\n"
                        message += f"详情页面:   https://item.m.jd.com/product/{sku}.html - {title}\n"
                    else:
                        message += f"https://item.m.jd.com/product/{sku}.html\n"
        
        print("📤 发送监控总结通知...")
        self.send_feishu_notification(message, self.alert_webhook_url)
        
        # 标记已发送总结报告
        self.has_sent_summary = True
    
    def get_interval_minutes(self):
        """根据当前时间获取执行间隔"""
        now = datetime.now()
        current_hour = now.hour
        
        # 早上9点-11点或晚上6点-8点，使用15分钟间隔
        # if (9 <= current_hour <= 15) or (17 <= current_hour <= 20) or (22 <= current_hour <= 24) or (0 <= current_hour <= 2):
        #     return 1
        # else:
        #     return 5
        return 1
    
    def monitor_keywords_concurrent(self):
        """并发监控所有关键词"""
        # 每次执行重新读取关键词配置文件
        keywords_config = self.load_keywords_config()
        if not keywords_config:
            print("❌ 没有加载到关键词配置，跳过本次监控")
            return
        
        self.keywords_config = keywords_config  # 更新当前的关键词配置
        
        # 每次执行使用新的时间戳
        process_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        print("\n" + "="*60)
        print("🕒 开始并发监控任务")
        print(f"⏰ 执行时间戳: {process_timestamp}")
        print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📝 配置关键词: {len(self.keywords_config)} 个")
        print("="*60)
        
        # 重置总结标记
        self.has_sent_summary = False
        
        # 加载所有现有SKU
        all_existing_skus = self.load_all_existing_skus()
        
        total_new_skus = set()
        total_new_products = []
        keyword_new_skus_details = {}  # 记录每个关键词的新SKU详情
        monitor_start_time = datetime.now()
        
        # 准备任务参数，同时记录关键词配置
        tasks = []
        keyword_tasks = []  # 记录每个任务对应的关键词配置
        for i, keyword_config in enumerate(self.keywords_config):
            # 检查是否正在关闭
            if not self.is_running:
                print("🛑 检测到关闭信号，停止分配新任务")
                break
                
            browser_index = i + 1
            task_args = (keyword_config, process_timestamp, browser_index)
            tasks.append(task_args)
            keyword_tasks.append((keyword_config, task_args))
        
        # 并发执行任务
        print(f"🚀 开始并发执行 {len(tasks)} 个任务...")
        
        # 创建未来任务和结果的映射
        future_to_keyword = {}
        for keyword_config, task_args in keyword_tasks:
            # 检查是否正在关闭
            if not self.is_running:
                print("🛑 检测到关闭信号，停止提交新任务")
                break
                
            future = self.executor.submit(self.process_keyword_with_browser, task_args)
            future_to_keyword[future] = keyword_config
        
        # 收集结果并立即处理每个关键词
        for future in concurrent.futures.as_completed(future_to_keyword):
            # 检查是否正在关闭
            if not self.is_running:
                print("🛑 检测到关闭信号，停止等待任务完成")
                break
                
            try:
                result = future.result(timeout=120)  # 超时设置
                
                # 获取对应的关键词配置
                keyword_config = future_to_keyword[future]
                keyword = keyword_config['keyword']
                
                # 处理结果
                if len(result) == 4:  # 确保有完整的结果
                    all_skus, product_links, new_skus_for_keyword, new_products_for_keyword = result
                    
                    # 记录关键词的新SKU详情
                    keyword_new_skus_details[keyword] = {
                        'new_skus': list(new_skus_for_keyword),
                        'new_products': new_products_for_keyword,
                        'total_skus': len(all_skus),
                        'historical_skus': len(self.get_keyword_historical_skus(keyword)),
                        'min_price': keyword_config['min_price'],
                        'max_price': keyword_config['max_price'],
                    }
                    
                    # 更新总的新SKU
                    total_new_skus.update(new_skus_for_keyword)
                    total_new_products.extend(new_products_for_keyword)
                    
            except Exception as e:
                print(f"❌ 任务执行失败: {e}")
                # 可以记录是哪个关键词失败了
                if future in future_to_keyword:
                    keyword_config = future_to_keyword[future]
                    print(f"❌ 关键词 '{keyword_config['keyword']}' 处理失败: {e}")
        
        # 存储当前监控数据（用于退出时发送总结）
        self.current_monitor_data = {
            'total_new_skus': total_new_skus,
            'all_existing_skus_count': len(all_existing_skus),
            'keyword_new_skus_details': keyword_new_skus_details,
            'monitor_start_time': monitor_start_time,
            'process_timestamp': process_timestamp
        }
        
        # # 更新监控结果
        # self.update_monitor_results(total_new_skus, monitor_start_time, process_timestamp, keyword_new_skus_details)
        
        # 发送总结通知（只有在正常完成时才发送）
        if self.is_running:
            print("📤 发送监控总结通知...")
            self.send_monitor_summary_notification(self.current_monitor_data)
        
        print(f"\n✅ 并发监控任务完成，发现 {len(total_new_skus)} 个新SKU")
        
        # 记录详细日志
        self.log_detailed_monitoring_result(total_new_skus, process_timestamp, keyword_new_skus_details)
        
        # # 保存监控结果
        # self.save_monitor_results()
    
    def update_keyword_stats(self, keyword_config, new_skus_count):
        """更新关键词统计"""
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
        """初始化监控结果"""
        self.monitor_results = {
            "total_monitor_count": 0,
            "total_new_skus": 0,
            "keyword_stats": {},
            "last_monitor_time": None,
            "monitor_history": []
        }
        print("📊 创建新的监控结果")

    def update_monitor_results(self, total_new_skus, start_time, process_timestamp, keyword_new_skus_details):
        """更新监控结果"""
        self.monitor_results['total_monitor_count'] += 1
        self.monitor_results['total_new_skus'] += len(total_new_skus)
        self.monitor_results['last_monitor_time'] = datetime.now().isoformat()
        
        # 添加监控历史记录
        monitor_record = {
            'timestamp': datetime.now().isoformat(),
            'process_timestamp': process_timestamp,
            'new_skus_count': len(total_new_skus),
            'duration_seconds': (datetime.now() - start_time).total_seconds(),
            'keywords_count': len(self.keywords_config),
            'keyword_details': keyword_new_skus_details
        }
        self.monitor_results['monitor_history'].append(monitor_record)
        
        # 只保留最近100条记录
        if len(self.monitor_results['monitor_history']) > 100:
            self.monitor_results['monitor_history'] = self.monitor_results['monitor_history'][-100:]
    
    def log_detailed_monitoring_result(self, total_new_skus, process_timestamp, keyword_new_skus_details):
        """记录详细监控结果到日志文件"""
        # 使用 root_dir 格式配置路径
        root_dir = "/Volumes/data"
        log_file = os.path.join(root_dir, "monitor_logs", f"monitor_{datetime.now().strftime('%Y%m%d')}.log")
        
        log_entry = f"\n{'='*80}\n"
        log_entry += f"监控执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        log_entry += f"执行时间戳: {process_timestamp}\n"
        log_entry += f"处理关键词: {len(self.keywords_config)} 个\n"
        log_entry += f"总共发现新SKU: {len(total_new_skus)} 个\n"
        
        # 添加每个关键词的详细统计
        log_entry += "各关键词详情:\n"
        for keyword, details in keyword_new_skus_details.items():
            log_entry += f"  - {keyword}: {len(details['new_skus'])} 个新SKU\n"
            if details['new_skus']:
                log_entry += f"    新SKU列表: {', '.join(details['new_skus'])}\n"
        
        log_entry += f"{'='*80}\n"
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)
        
        # print(f"📝 详细日志已记录")
    
    def start_scheduled_monitoring(self):
        """启动定时监控"""
        # 获取当前执行间隔
        interval_minutes = self.get_interval_minutes()
        current_hour = datetime.now().hour
        
        print(f"⏰ 启动定时监控")
        print(f"📝 配置关键词文件: {self.keywords_config_file}")
        print(f"⏱️  当前时间段 ({current_hour}点): 执行间隔 {interval_minutes} 分钟")
        print(f"💾 按 Ctrl+C 可以安全退出程序")
        print(f"🛑 再次按 Ctrl+C 强制退出所有进程")
        
        # 立即执行一次监控
        print("\n🚀 开始第一次并发监控...")
        self.monitor_keywords_concurrent()
        
        # 设置定时任务
        schedule.every(interval_minutes).minutes.do(self.monitor_keywords_concurrent)
        
        print(f"\n🔄 定时任务已启动，下次执行在 {interval_minutes} 分钟后...")
        
        # 运行调度器
        while self.is_running:
            try:
                schedule.run_pending()
                time.sleep(1)  # 每秒检查一次，提高响应速度
                
                # 检查是否需要调整执行间隔
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
    # 关键词配置文件路径
    keywords_config_file = os.path.join(user_dir, "keywords_config_jie_mi.json")
    
    # 检查关键词配置文件是否存在
    if not os.path.exists(keywords_config_file):
        print(f"❌ 关键词配置文件不存在: {keywords_config_file}")
        print("💡 请创建关键词文件")
        return
    
    # 配置飞书机器人
    webhook_urls = [
        "https://open.feishu.cn/open-apis/bot/v2/hook/e2a55623-6e69-4bcf-9dd8-de1909dca6ea",
        "https://open.feishu.cn/open-apis/bot/v2/hook/ce4e3ffa-a142-43d3-89b0-9c0871c8255b",
        "https://open.feishu.cn/open-apis/bot/v2/hook/41d87188-11b6-4268-ae4e-578dc614df4f",
        "https://open.feishu.cn/open-apis/bot/v2/hook/2fec3d16-d00b-4674-b2b4-62e8774d7228",
        "https://open.feishu.cn/open-apis/bot/v2/hook/8d287153-d77e-4333-9e90-7a0a245abf1a"
    ]
    
    # 配置专门的警报机器人
    alert_webhook_url = "https://open.feishu.cn/open-apis/bot/v2/hook/c4c5c426-056c-4141-af3e-5e2d4b775fcd"
    
    # 修改：直接初始化，不再提示选择获取方式
    monitor = JDSKUMonitor(
        keywords_config_file, 
        webhook_urls=webhook_urls,
        alert_webhook_url=alert_webhook_url
    )
    
    # 启动定时监控
    monitor.start_scheduled_monitoring()

if __name__ == "__main__":
    print("京东SKU监控系统 - 即时通知版本 (云端优化版)")
    print("=" * 50)
    
    # 直接启动定时监控
    main()
import requests
import json
import os
import time
import base64
import urllib.parse
import re
import multiprocessing
import logging
import lark_oapi as lark
from lark_oapi import EventDispatcherHandler, ws, JSON, im, LogLevel
from lark_oapi.api.im.v1 import GetMessageResourceRequest, GetMessageResourceResponse, CreateImageRequest, CreateImageRequestBody

# 全局Webhook配置
NOTIFICATION_WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/a37f056a-d003-4733-8807-cbbc9daa0736"

# 机器人配置
ROBOT_CONFIGS = {
    'huawei': {
        'APP_ID': 'cli_a99551173af8dcd5',
        'APP_SECRET': 'NbfEX7gsuajHQmRIzUTUXdFjMP6w0j23',
        'brand': 'huawei'
    },
    'honor': {
        'APP_ID': 'cli_a9aadf07b8f8dcdd',
        'APP_SECRET': 'TBVyiDrbCU97C5Oh6ZpXogXfbTveOSFp',
        'brand': 'honor'
    },
    'xiaomi': {
        'APP_ID': 'cli_a9aad9df96b85cc5',
        'APP_SECRET': '72Hhr7fZsGlVVnwhp5D5YcgEvf1XCRzD',
        'brand': 'xiaomi'
    },
    'oppo': {
        'APP_ID': 'cli_a9aad45314785cdc',
        'APP_SECRET': '2gVQdYFTcJBAg4dJoE4n0tLmIjXaUaOw',
        'brand': 'oppo'
    },
    'realme': {
        'APP_ID': 'cli_a9aacadfe0b89cc6',
        'APP_SECRET': '4OhcUsX1YvJMFXJ6jtKbWdF131wDL2gx',
        'brand': 'realme'
    },
    'vivo': {
        'APP_ID': 'cli_a9aac4095838dcca',
        'APP_SECRET': '2yrhLp4G07a4sQoSvkh6Jg1QqhKcofD5',
        'brand': 'vivo'
    }
}

class DeviceQueryConfig:
    '''设备查询配置'''
    API_KEY = "39298081f644727e467e6496182391c0"
    QUERY_URL = "https://data.06api.com/api.php"

class BaiduOCRConfig:
    '''百度OCR配置信息'''
    # 主账号
    # API_KEY = "B2WT4jGOnJ7V0kq7nRKtJVw4"
    # SECRET_KEY = "SjRXsgpiaUfL1onSb4Z3w6RkqUeatlfs"
    API_KEY_BACKUP1 = "B2WT4jGOnJ7V0kq7nRKtJVw4"
    SECRET_KEY_BACKUP1 = "SjRXsgpiaUfL1onSb4Z3w6RkqUeatlfs"
    
    # 备用账号1
    # API_KEY_BACKUP1 = "isVf2aoX7BPaptjqJAet8KH3"
    # SECRET_KEY_BACKUP1 = "F4kIUlsEhUlJVLFjJhPJYFppTB7oV9GQ"
    API_KEY = "isVf2aoX7BPaptjqJAet8KH3"
    SECRET_KEY = "F4kIUlsEhUlJVLFjJhPJYFppTB7oV9GQ"
    
    # 备用账号2
    API_KEY_BACKUP2 = "ypa6lyhMoIxj5rgX6RUQ1ABW"
    SECRET_KEY_BACKUP2 = "zZxx9BfBFIWkG28t1cl2GNMEl2ikAO0o"
    
    # OCR_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic"
    OCR_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic"

class WebhookNotifier:
    '''Webhook通知类'''
    
    @staticmethod
    def send_notification(message, image_key=None):
        '''发送通知到Webhook群聊'''
        try:
            if image_key:
                # 发送图片消息
                data = {
                    "msg_type": "image",
                    "content": {
                        "image_key": image_key
                    }
                }
            else:
                # 发送文本消息
                data = {
                    "msg_type": "text",
                    "content": {
                        "text": message
                    }
                }
            
            headers = {
                'Content-Type': 'application/json; charset=utf-8'
            }
            
            response = requests.post(NOTIFICATION_WEBHOOK_URL, headers=headers, json=data)
            response.raise_for_status()
            logging.info("Webhook通知发送成功")
            return True
        except Exception as e:
            logging.error(f"Webhook通知发送失败: {e}")
            return False

    @staticmethod
    def send_error_notification(error_message, image_path=None, brand=None):
        '''发送错误通知到Webhook群聊'''
        try:
            # 构建错误消息
            error_parts = []
            error_parts.append("🚨 系统发生异常")
            error_parts.append("")
            if brand:
                error_parts.append(f"🏷️ 品牌: {brand.upper()}")
            error_parts.append(f"⏰ 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            error_parts.append(f"📛 错误信息: {error_message}")
            error_parts.append("")
            error_parts.append("请及时检查系统状态！")
            
            notification_message = "\n".join(error_parts)
            
            # 发送文本错误通知
            WebhookNotifier.send_notification(notification_message)
            
            # 如果有图片，上传并发送
            if image_path and os.path.exists(image_path):
                feishu = None
                for config in ROBOT_CONFIGS.values():
                    try:
                        feishu = FeishuApi(config['APP_ID'], config['APP_SECRET'], brand or 'unknown')
                        break
                    except:
                        continue
                
                if feishu:
                    uploaded_image_key = feishu.upload_image(image_path)
                    if uploaded_image_key:
                        WebhookNotifier.send_notification(None, uploaded_image_key)
                        logging.info("错误图片已发送到Webhook")
            
            return True
        except Exception as e:
            logging.error(f"发送错误通知失败: {e}")
            return False

class MessageIdManager:
    '''消息ID管理器，持久化存储已处理的消息ID'''
    
    def __init__(self, brand):
        self.brand = brand
        self.processed_file = f"{brand}_processed_messages.json"
        self.processed_messages = self.load_processed_messages()
    
    def load_processed_messages(self):
        '''从文件加载已处理的消息ID'''
        try:
            if os.path.exists(self.processed_file):
                with open(self.processed_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 只保留最近7天的消息ID，避免文件过大
                    current_time = time.time()
                    one_week_ago = current_time - 7 * 24 * 3600
                    filtered_data = {msg_id: timestamp for msg_id, timestamp in data.items() 
                                   if timestamp > one_week_ago}
                    
                    # 如果过滤后数据变化，保存更新后的文件
                    if len(filtered_data) != len(data):
                        self.save_processed_messages(filtered_data)
                    
                    logging.info(f"[{self.brand}] 已加载 {len(filtered_data)} 个历史消息ID")
                    return set(filtered_data.keys())
            else:
                logging.info(f"[{self.brand}] 无历史消息ID文件，创建新文件")
                return set()
        except Exception as e:
            logging.error(f"[{self.brand}] 加载消息ID文件失败: {e}")
            return set()
    
    def save_processed_messages(self, data=None):
        '''保存已处理的消息ID到文件'''
        try:
            if data is None:
                # 将set转换为dict，记录时间戳
                data = {msg_id: time.time() for msg_id in self.processed_messages}
            
            with open(self.processed_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"[{self.brand}] 保存消息ID文件失败: {e}")
    
    def add_message(self, message_id):
        '''添加已处理的消息ID'''
        self.processed_messages.add(message_id)
        # 异步保存，避免频繁IO
        if len(self.processed_messages) % 10 == 0:  # 每10条保存一次
            self.save_processed_messages()
    
    def is_processed(self, message_id):
        '''检查消息是否已处理'''
        return message_id in self.processed_messages
    
    def __del__(self):
        '''析构时保存数据'''
        try:
            self.save_processed_messages()
        except:
            pass

class ImeiQueryManager:
    '''IMEI查询管理器，检查IMEI是否已经查询过'''
    
    @staticmethod
    def get_query_count(brand, product_code):
        '''获取IMEI码的查询次数'''
        try:
            brand_dir = brand
            if not os.path.exists(brand_dir):
                return 0
            
            # 查找该IMEI码的所有查询记录
            pattern = f"{product_code}_*.json"
            matching_files = []
            
            for filename in os.listdir(brand_dir):
                if filename.startswith(f"{product_code}_") and filename.endswith('_result.json'):
                    matching_files.append(filename)
            
            return len(matching_files)
            
        except Exception as e:
            logging.error(f"[{brand}] 获取IMEI查询次数失败: {e}")
            return 0
    
    @staticmethod
    def is_first_query(brand, product_code):
        '''检查是否是第一次查询'''
        return ImeiQueryManager.get_query_count(brand, product_code) == 0

class FeishuApi:
    '''FeishuApi类用于处理与飞书API的交互'''
    
    def __init__(self, app_id, app_secret, brand):
        self.app_id = app_id
        self.app_secret = app_secret
        self.brand = brand
        
        # 创建 Lark client
        self.client = lark.Client.builder() \
            .app_id(app_id) \
            .app_secret(app_secret) \
            .log_level(lark.LogLevel.INFO) \
            .build()
        
        self.session = requests.Session()
        self.token = None
        self.token_expire_time = 0
        self.TOKEN_URL = 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal'
        self.REPLY_MESSAGE_URL_TEMPLATE = 'https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply'
        self.HEADERS = {'Content-Type': 'application/json; charset=utf-8'}
        self.refresh_token()

    def refresh_token(self):
        '''刷新token'''
        try:
            data = {'app_id': self.app_id, 'app_secret': self.app_secret}
            response = self.session.post(self.TOKEN_URL, headers=self.HEADERS, json=data)
            response.raise_for_status()
            result = response.json()
            self.token = result.get('tenant_access_token')
            self.token_expire_time = time.time() + 5400
            logging.info(f"[{self.brand}] Token刷新成功")
        except Exception as e:
            logging.error(f"[{self.brand}] 刷新token失败: {e}")
            self.token = None

    def get_token(self):
        '''获取有效的token'''
        if not self.token or time.time() >= self.token_expire_time:
            self.refresh_token()
        return self.token

    def reply_message(self, message_id, message, chat_type="p2p"):
        '''回复飞书消息'''
        try:
            token = self.get_token()
            if not token:
                logging.error(f"[{self.brand}] 无法获取有效token")
                return None

            url = self.REPLY_MESSAGE_URL_TEMPLATE.format(message_id=message_id)
            
            content = {
                "text": message
            }
            
            data = {
                "content": json.dumps(content, ensure_ascii=False),
                "msg_type": "text"
            }
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json; charset=utf-8'
            }
            
            response = self.session.post(url, headers=headers, json=data)
            response.raise_for_status()
            logging.info(f"[{self.brand}] 消息回复成功")
            return response.json()
        except Exception as e:
            logging.error(f"[{self.brand}] 回复消息失败: {e}")
            if "401" in str(e) or "token" in str(e).lower():
                self.refresh_token()
            return None

    def download_image(self, message_id, image_key, save_path):
        '''使用正确的API下载图片'''
        try:
            # 构造请求对象
            request: GetMessageResourceRequest = GetMessageResourceRequest.builder() \
                .message_id(message_id) \
                .file_key(image_key) \
                .type("image") \
                .build()

            # 发起请求
            response: GetMessageResourceResponse = self.client.im.v1.message_resource.get(request)

            # 处理失败返回
            if not response.success():
                logging.error(f"[{self.brand}] 下载图片失败, code: {response.code}, msg: {response.msg}")
                return None

            # 确保目录存在
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            
            # 保存图片
            with open(save_path, "wb") as f:
                f.write(response.file.read())
            
            logging.info(f"[{self.brand}] 图片下载成功: {save_path}")
            return save_path
            
        except Exception as e:
            logging.error(f"[{self.brand}] 下载图片时出错: {e}")
            return None

    def upload_image(self, image_path):
        '''上传图片到飞书并获取image_key'''
        try:
            # 确保图片文件存在
            if not os.path.exists(image_path):
                logging.error(f"[{self.brand}] 图片文件不存在: {image_path}")
                return None

            # 打开图片文件
            with open(image_path, "rb") as file:
                # 构造请求对象
                request: CreateImageRequest = CreateImageRequest.builder() \
                    .request_body(CreateImageRequestBody.builder()
                        .image_type("message")
                        .image(file)
                        .build()) \
                    .build()

                # 发起请求
                response = self.client.im.v1.image.create(request)

                # 处理失败返回
                if not response.success():
                    logging.error(f"[{self.brand}] 上传图片失败, code: {response.code}, msg: {response.msg}")
                    return None

                # 返回图片key
                image_key = response.data.image_key
                logging.info(f"[{self.brand}] 图片上传成功，image_key: {image_key}")
                return image_key

        except Exception as e:
            logging.error(f"[{self.brand}] 上传图片时出错: {e}")
            return None

class BaiduOCR:
    '''百度OCR识别类'''
    
    def __init__(self):
        self.current_account_index = 0
        self.access_token = None
        self.access_token_expire_time = 0
        self.disabled_accounts = set()  # 记录当天已禁用的账号
        self.last_reset_date = time.localtime().tm_yday  # 记录当前日期
        self.refresh_access_token()
    
    def check_date_reset(self):
        '''检查是否需要重置禁用账号列表（新的一天）'''
        current_date = time.localtime().tm_yday
        if current_date != self.last_reset_date:
            self.disabled_accounts.clear()
            self.last_reset_date = current_date
            logging.info("新的一天，重置禁用账号列表")
    
    def get_current_account(self):
        '''获取当前使用的账号配置'''
        accounts = [
            (BaiduOCRConfig.API_KEY, BaiduOCRConfig.SECRET_KEY),
            (BaiduOCRConfig.API_KEY_BACKUP1, BaiduOCRConfig.SECRET_KEY_BACKUP1),
            (BaiduOCRConfig.API_KEY_BACKUP2, BaiduOCRConfig.SECRET_KEY_BACKUP2)
        ]
        return accounts[self.current_account_index]
    
    def switch_to_next_account(self):
        '''切换到下一个可用的账号'''
        original_index = self.current_account_index
        max_attempts = 3
        
        for attempt in range(max_attempts):
            self.current_account_index = (self.current_account_index + 1) % 3
            
            # 如果这个账号当天已被禁用，继续尝试下一个
            if self.current_account_index in self.disabled_accounts:
                logging.info(f"账号 {self.current_account_index + 1} 当天已被禁用，跳过")
                continue
                
            logging.info(f"切换到百度OCR账号 {self.current_account_index + 1}")
            self.refresh_access_token()
            return True
        
        # 如果所有账号都被禁用，重置并使用第一个
        logging.warning("所有账号当天都被禁用，重置并使用第一个账号")
        self.disabled_accounts.clear()
        self.current_account_index = 0
        self.refresh_access_token()
        return True
    
    def disable_current_account(self):
        '''禁用当前账号（当天不再使用）'''
        if self.current_account_index not in self.disabled_accounts:
            self.disabled_accounts.add(self.current_account_index)
            logging.info(f"禁用百度OCR账号 {self.current_account_index + 1}（当天不再使用）")
    
    def refresh_access_token(self):
        '''刷新百度OCR的access_token'''
        try:
            # 检查当前账号是否已被禁用
            if self.current_account_index in self.disabled_accounts:
                logging.info(f"当前账号 {self.current_account_index + 1} 已被禁用，切换到下一个")
                self.switch_to_next_account()
                return
                
            api_key, secret_key = self.get_current_account()
            url = "https://aip.baidubce.com/oauth/2.0/token"
            params = {
                "grant_type": "client_credentials", 
                "client_id": api_key, 
                "client_secret": secret_key
            }
            response = requests.post(url, params=params)
            result = response.json()
            
            if 'access_token' in result:
                self.access_token = str(result.get("access_token"))
                self.access_token_expire_time = time.time() + 25 * 24 * 3600
                logging.info(f"百度OCR账号 {self.current_account_index + 1} Token刷新成功")
            else:
                error_msg = result.get('error_description', '未知错误')
                logging.error(f"百度OCR账号 {self.current_account_index + 1} Token刷新失败: {error_msg}")
                # 如果当前账号失败，禁用并切换到下一个账号
                self.disable_current_account()
                self.switch_to_next_account()
                
        except Exception as e:
            logging.error(f"刷新百度OCR Token失败: {e}")
            # 如果当前账号失败，禁用并切换到下一个账号
            self.disable_current_account()
            self.switch_to_next_account()
    
    def get_access_token(self):
        '''获取有效的百度OCR access_token'''
        self.check_date_reset()  # 检查日期重置
        if not self.access_token or time.time() >= self.access_token_expire_time:
            self.refresh_access_token()
        return self.access_token
    
    def recognize_text(self, image_path):
        '''识别图片中的文字'''
        max_retries = 3  # 最多重试3次（包括切换账号）
        
        for attempt in range(max_retries):
            try:
                access_token = self.get_access_token()
                if not access_token:
                    logging.error("无法获取百度OCR access_token")
                    continue

                # 读取图片并编码为base64
                with open(image_path, 'rb') as f:
                    image_data = base64.b64encode(f.read()).decode()
                
                # 对base64数据进行urlencode
                image_data_encoded = urllib.parse.quote_plus(image_data)
                
                # 构建payload
                payload = f'image={image_data_encoded}&detect_direction=false&paragraph=false&probability=false'
                
                # 调用百度OCR API
                url = BaiduOCRConfig.OCR_URL + "?access_token=" + access_token
                
                headers = {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Accept': 'application/json'
                }
                
                logging.info(f"开始OCR识别 (尝试 {attempt + 1}/{max_retries})")
                
                response = requests.request("POST", url, headers=headers, data=payload.encode("utf-8"))
                
                logging.info(f"OCR响应状态码: {response.status_code}")
                
                result = response.json()
                
                if 'error_code' in result:
                    error_code = result.get('error_code')
                    error_msg = result.get('error_msg', '未知错误')
                    print('access_token')
                    print(access_token)
                    print('API_KEY')
                    print(BaiduOCRConfig.API_KEY)
                    logging.error(f"OCR识别错误: {error_code} - {error_msg}")
                    
                    # 如果是额度不足错误，禁用当前账号并切换到下一个
                    if error_code in [17, 18, 19]:  # 常见的额度相关错误码
                        logging.warning("当前OCR账号额度不足，禁用并切换到下一个账号")
                        self.disable_current_account()
                        self.switch_to_next_account()
                        continue
                    else:
                        return None
                
                if 'words_result' in result:
                    words_list = [item['words'] for item in result['words_result']]
                    text = '\n'.join(words_list)
                    logging.info(f"OCR识别成功，识别到 {len(words_list)} 行文字")
                    return text
                else:
                    logging.error(f"OCR识别失败，返回结果中没有words_result")
                    return None
                    
            except Exception as e:
                logging.error(f"OCR识别时出错 (尝试 {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    # 禁用当前账号并切换到下一个
                    self.disable_current_account()
                    self.switch_to_next_account()
                else:
                    return None
        
        return None

class DeviceQuery:
    '''设备查询类'''
    
    @staticmethod
    def extract_product_code(text):
        '''从OCR识别结果中提取商品唯一码'''
        # 首先尝试直接匹配15-20位连续数字
        product_code_pattern = r'(?<![\w\d])\d{15,20}(?![\d])'
        direct_matches = re.findall(product_code_pattern, text)
        
        if direct_matches:
            logging.info(f"直接匹配到商品唯一码: {direct_matches[0]}")
            return direct_matches[0]
        
        # 如果没有直接匹配到，尝试处理换行情况
        # 查找"商品唯一码："关键词
        product_code_keyword_pattern = r'商品唯一码[：:\s]*(\d{1,20})'
        keyword_matches = re.findall(product_code_keyword_pattern, text)
        
        if keyword_matches:
            base_code = keyword_matches[0]
            logging.info(f"找到商品唯一码基础部分: {base_code}")
            
            # 查找可能被分割到下一行的剩余部分
            # 在基础部分后面查找可能的连续数字
            remaining_pattern = rf'{re.escape(base_code)}\s*(\d{{1,5}})'
            remaining_matches = re.findall(remaining_pattern, text.replace('\n', ' '))
            
            if remaining_matches:
                full_code = base_code + remaining_matches[0]
                logging.info(f"组合完整商品唯一码: {full_code}")
                return full_code
            else:
                # 如果没有找到剩余部分，检查基础部分长度
                if len(base_code) >= 15:
                    logging.info(f"使用基础部分作为商品唯一码: {base_code}")
                    return base_code
        
        # 最后尝试：查找所有数字序列，合并相邻的短数字序列
        all_digits = re.findall(r'\d+', text)
        if all_digits:
            # 尝试合并相邻的数字序列
            merged_digits = []
            i = 0
            while i < len(all_digits):
                current = all_digits[i]
                # 如果当前数字序列长度在15-20之间，直接使用
                if 15 <= len(current) <= 20:
                    logging.info(f"找到合适长度的数字序列: {current}")
                    return current
                
                # 尝试合并后续的数字序列
                j = i + 1
                while j < len(all_digits) and len(current) < 20:
                    next_digit = all_digits[j]
                    if len(current) + len(next_digit) <= 20:
                        current += next_digit
                        j += 1
                    else:
                        break
                
                if 15 <= len(current) <= 20:
                    logging.info(f"合并后得到商品唯一码: {current}")
                    return current
                
                i = j
            
        logging.warning("未找到有效的商品唯一码")
        return None
    
    @staticmethod
    def query_device_info(product_code, brand):
        '''查询设备信息'''
        try:
            params = {
                'key': DeviceQueryConfig.API_KEY,
                'type': brand,
                'sn': product_code
            }
            
            logging.info(f"开始查询设备信息，品牌: {brand}, 商品码: {product_code}")
            response = requests.get(DeviceQueryConfig.QUERY_URL, params=params)
            logging.info(f"设备查询响应状态码: {response.status_code}")
            
            result = response.json()
            
            if result.get('code') == 0:
                # 查询成功
                data = result.get('data', {})
                return {
                    'success': True,
                    'product_code': product_code,
                    'device_info': data,
                    'raw_response': result
                }
            else:
                # 查询失败
                error_code = result.get('code')
                error_message = result.get('message', '未知错误')
                return {
                    'success': False,
                    'error_code': error_code,
                    'error_message': error_message,
                    'raw_response': result
                }
                
        except Exception as e:
            logging.error(f"设备查询时出错: {e}")
            return {
                'success': False,
                'error_code': '9999',
                'error_message': f'查询异常: {str(e)}',
                'raw_response': {'error': str(e)}
            }

def save_query_result(brand, product_code, query_result, image_path, query_count):
    '''保存查询结果（只保存JSON文件）'''
    try:
        # 确保品牌目录存在
        brand_dir = brand
        if not os.path.exists(brand_dir):
            os.makedirs(brand_dir)
        
        # 生成文件名前缀
        timestamp = int(time.time())
        filename_prefix = f"{product_code}_{timestamp}"
        
        # 保存完整的查询结果JSON
        json_filepath = os.path.join(brand_dir, f"{filename_prefix}_result.json")
        result_data = {
            'brand': brand,
            'product_code': product_code,
            'timestamp': timestamp,
            'query_time': time.strftime('%Y-%m-%d %H:%M:%S'),
            'query_count': query_count,
            'query_result': query_result
        }
        
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        
        # 重命名图片文件（只保存图片，不保存OCR文本）
        if os.path.exists(image_path):
            new_image_path = os.path.join(brand_dir, f"{filename_prefix}.jpg")
            # 如果目标文件已存在，先删除
            if os.path.exists(new_image_path):
                os.remove(new_image_path)
            os.rename(image_path, new_image_path)
            logging.info(f"[{brand}] 图片已重命名为: {new_image_path}")
        else:
            new_image_path = image_path
            logging.warning(f"[{brand}] 原始图片文件不存在: {image_path}")
        
        logging.info(f"[{brand}] 查询结果已保存: {json_filepath}")
        return json_filepath, new_image_path
    except Exception as e:
        logging.error(f"[{brand}] 保存查询结果失败: {e}")
        return None, None

def get_activation_status(brand, device_info):
    '''根据品牌获取激活状态'''
    try:
        if brand == 'vivo':
            # Vivo: activated字段为'未激活'表示未激活，为日期字符串表示已激活
            activated = device_info.get('activated')
            if activated == '未激活':
                return False, None  # 未激活
            elif activated and activated != '未激活':
                return True, activated  # 已激活，返回激活日期
            else:
                return None, None  # 状态未知
        
        elif brand == 'oppo':
            # OPPO: 根据purchase.date判断
            purchase = device_info.get('purchase', {})
            purchase_date = purchase.get('date')
            if purchase_date and purchase_date != 'null' and purchase_date is not None:
                return True, purchase_date  # 已激活，返回激活日期
            else:
                return False, None  # 未激活
        
        else:
            # 其他品牌：使用activated布尔字段
            activated = device_info.get('activated')
            if activated is True:
                activate_date = device_info.get('activateDate', '')
                return True, activate_date  # 已激活，返回激活日期
            elif activated is False:
                return False, None  # 未激活
            else:
                return None, None  # 状态未知
                
    except Exception as e:
        logging.error(f"获取激活状态时出错: {e}")
        return None, None

def check_meets_conditions(brand, device_info):
    '''检查设备是否符合条件'''
    try:
        # 获取激活状态
        is_activated, activate_date = get_activation_status(brand, device_info)
        
        # 华为和荣耀需要额外检查是否为官翻机
        if brand in ['huawei', 'honor']:
            type_info = device_info.get('type', {})
            refurbished = type_info.get('refurbished', False)
            
            # 华为/荣耀：必须未激活且不是官翻机
            if is_activated is False and refurbished is False:
                return True, "符合条件（未激活且非官翻机）"
            elif is_activated is True:
                return False, f"不符合条件（已激活，激活日期: {activate_date}）" if activate_date else "不符合条件（已激活）"
            elif refurbished is True:
                return False, "不符合条件（官翻机）"
            else:
                return False, "不符合条件（状态未知）"
        
        # 其他品牌只需要检查激活状态
        else:
            if is_activated is False:
                return True, "符合条件（未激活）"
            elif is_activated is True:
                return False, f"不符合条件（已激活，激活日期: {activate_date}）" if activate_date else "不符合条件（已激活）"
            else:
                return False, "不符合条件（状态未知）"
                
    except Exception as e:
        logging.error(f"检查条件时出错: {e}")
        return False, f"检查条件时出错: {str(e)}"

def start_robot_process(brand, config):
    '''在独立进程中启动机器人'''
    # 初始化消息ID管理器
    message_manager = MessageIdManager(brand)
    logger = logging.getLogger(brand)
    
    def should_process_message(message_data):
        '''判断是否应该处理该消息'''
        try:
            message_id = message_data["event"]["message"]["message_id"]
            
            if message_manager.is_processed(message_id):
                logger.info(f"消息 {message_id} 已处理过，跳过")
                return False
            
            sender_type = message_data["event"]["sender"]["sender_type"]
            if sender_type != "user":
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"判断消息处理条件时出错: {e}")
            return False

    def handle_p2_im_message(data: im.v1.P2ImMessageReceiveV1):
        '''处理接收消息事件'''
        downloaded_path = None
        try:
            data_dict = json.loads(JSON.marshal(data)) 
            message_id = data_dict["event"]["message"]["message_id"]
            chat_type = data_dict["event"]["message"]["chat_type"]
            
            logger.info(f"收到新消息: {message_id}, 类型: {data_dict['event']['message']['message_type']}")
            
            if not should_process_message(data_dict):
                return
            
            # 立即标记为已处理，避免重复处理
            message_manager.add_message(message_id)
            
            msg_type = data_dict["event"]["message"]["message_type"]
            
            feishu = FeishuApi(config['APP_ID'], config['APP_SECRET'], brand)

            if msg_type == "text":
                try:
                    content_dict = json.loads(data.event.message.content)
                    text = content_dict.get("text", "").strip() 
                except Exception as e:
                    logger.error(f"解析文本消息失败: {e}")
                    return
                
                logger.info(f"收到文本消息: {text}")

                #提取 IMEI 码
                product_code = DeviceQuery.extract_product_code(text)
                
                if not product_code:
                    return

                #执行查询逻辑
                logger.info(f"从文本提取到码: {product_code}")

                #查重
                is_first_query = ImeiQueryManager.is_first_query(brand, product_code)
                query_count = ImeiQueryManager.get_query_count(brand, product_code) + 1
                
                if not is_first_query:
                    feishu.reply_message(message_id, f'[{brand}] ❌ 该设备已查询过（第{query_count-1}次），禁止重复查询！', chat_type)
                    return
                
                #调用接口
                result = DeviceQuery.query_device_info(product_code, brand)
                
                save_query_result(brand, product_code, result, "", query_count)
                
                #检查条件 & 发送通知
                device_info = result.get('device_info', {})
                meets_conditions, condition_reason = check_meets_conditions(brand, device_info)
                
                #获取 IMEI 和 激活状态 
                imei = device_info.get('imei', '未知')
                is_activated, activate_date = get_activation_status(brand, device_info)

                if meets_conditions and result['success']:
                    notification_parts = []
                    notification_parts.append(f"🎯 发现符合条件的设备！ (文本录入)") # 稍微加个备注区分来源，保持格式一致
                    notification_parts.append("")
                    notification_parts.append(f"🏷️ 品牌: {brand.upper()}")
                    notification_parts.append(f"🔢 商品唯一码: {product_code}")
                    notification_parts.append(f"📊 查询次数: 第{query_count}次查询")
                    
                    notification_parts.append(f"📱 IMEI码: {imei}")
                    notification_parts.append(f"📄 设备型号: {device_info.get('model', '未知')}")
                    
                    if is_activated is True:
                        notification_parts.append("🟢 设备状态: 已激活")
                        if activate_date:
                            notification_parts.append(f"📅 激活日期: {activate_date}")
                    elif is_activated is False:
                        notification_parts.append("🟡 设备状态: 未激活")
                    else:
                        notification_parts.append("⚪ 设备状态: 未知")
                    
                    if brand in ['huawei', 'honor']:
                        type_info = device_info.get('type', {})
                        refurbished = type_info.get('refurbished')
                        retail = type_info.get('retail')
                        
                        if refurbished is True:
                            notification_parts.append("🔴 设备类型: 官翻机")
                        elif refurbished is False:
                            notification_parts.append("🟢 设备类型: 非官翻机")
                        
                        if retail is True:
                            notification_parts.append("🟢 销售类型: 零售机")
                        elif retail is False:
                            notification_parts.append("🟡 销售类型: 非零售机")

                    notification_parts.append("")
                    notification_parts.append("✅ 此设备符合条件，请及时处理！")
                    
                    #发送通知
                    WebhookNotifier.send_notification("\n".join(notification_parts))
                
                reply_parts = []
                reply_parts.append(f"📱 {brand.upper()}设备查询结果")
                reply_parts.append("")
                reply_parts.append(f"🔢 商品唯一码: {product_code}")
                reply_parts.append(f"📊 查询次数: 第{query_count}次查询")
                
                if result['success']:
                    if meets_conditions:
                        reply_parts.append("🟢 符合条件")
                        reply_parts.append(f"📄 设备型号: {device_info.get('model', '未知')}")
                    else:
                        reply_parts.append("🔴 不符合条件")
                else:
                    reply_parts.append("❌ 查询状态: 失败")
                    reply_parts.append(f"📛 失败原因: {result.get('error_message', '未知错误')}")
                
                feishu.reply_message(message_id, "\n".join(reply_parts), chat_type)
                return                        
            
            elif msg_type == "image":
                image_content = eval(data.event.message.content)
                image_key = image_content.get("image_key", "")
                
                if image_key:
                    logger.info(f"开始处理图片，image_key: {image_key}")
                    
                    timestamp = int(time.time())
                    # 使用绝对路径保存图片
                    current_dir = os.getcwd()
                    save_path = os.path.join(current_dir, brand, f"temp_{image_key}_{timestamp}.jpg")
                    downloaded_path = save_path
                    
                    downloaded_path = feishu.download_image(message_id, image_key, save_path)
                    
                    if downloaded_path:
                        logger.info(f"图片下载完成: {downloaded_path}")
                        
                        ocr = BaiduOCR()
                        recognized_text = ocr.recognize_text(downloaded_path)
                        
                        if recognized_text:
                            logger.info("OCR识别成功")
                            logger.info(f"OCR识别结果: {recognized_text}")
                            
                            product_code = DeviceQuery.extract_product_code(recognized_text)
                            
                            if product_code:
                                # 检查是否是第一次查询
                                is_first_query = ImeiQueryManager.is_first_query(brand, product_code)
                                query_count = ImeiQueryManager.get_query_count(brand, product_code) + 1
                                
                                # 如果不是第一次查询，阻止查询并返回提示
                                if not is_first_query:
                                    feishu.reply_message(
                                        message_id=message_id,
                                        message=f'[{brand}] ❌ 该设备已查询过（第{query_count-1}次），禁止重复查询！',
                                        chat_type=chat_type
                                    )
                                    logger.info(f"[{brand}] 阻止重复查询，IMEI: {product_code}")
                                    # 删除临时文件
                                    if os.path.exists(downloaded_path):
                                        os.remove(downloaded_path)
                                    return
                                
                                query_result = DeviceQuery.query_device_info(product_code, brand)
                                
                                json_filepath, final_image_path = save_query_result(brand, product_code, query_result, downloaded_path, query_count)
                                
                                # 检查是否符合条件
                                meets_conditions, _ = check_meets_conditions(brand, query_result.get('device_info', {}))
                                
                                # 如果符合条件，发送Webhook通知
                                if meets_conditions and query_result['success']:
                                    # 格式化Webhook通知消息
                                    notification_parts = []
                                    notification_parts.append(f"🎯 发现符合条件的设备！")
                                    notification_parts.append("")
                                    notification_parts.append(f"🏷️ 品牌: {brand.upper()}")
                                    notification_parts.append(f"🔢 商品唯一码: {product_code}")
                                    notification_parts.append(f"📊 查询次数: 第{query_count}次查询")
                                    
                                    device_info = query_result.get('device_info', {})
                                    imei = device_info.get('imei', '未知')
                                    
                                    notification_parts.append(f"📱 IMEI码: {imei}")
                                    notification_parts.append(f"📄 设备型号: {device_info.get('model', '未知')}")
                                    
                                    # 显示详细状态信息
                                    is_activated, activate_date = get_activation_status(brand, device_info)
                                    
                                    if is_activated is True:
                                        notification_parts.append("🟢 设备状态: 已激活")
                                        if activate_date:
                                            notification_parts.append(f"📅 激活日期: {activate_date}")
                                    elif is_activated is False:
                                        notification_parts.append("🟡 设备状态: 未激活")
                                    else:
                                        notification_parts.append("⚪ 设备状态: 未知")
                                    
                                    # 华为和荣耀显示官翻机信息
                                    if brand in ['huawei', 'honor']:
                                        type_info = device_info.get('type', {})
                                        refurbished = type_info.get('refurbished')
                                        retail = type_info.get('retail')
                                        
                                        if refurbished is True:
                                            notification_parts.append("🔴 设备类型: 官翻机")
                                        elif refurbished is False:
                                            notification_parts.append("🟢 设备类型: 非官翻机")
                                        
                                        if retail is True:
                                            notification_parts.append("🟢 销售类型: 零售机")
                                        elif retail is False:
                                            notification_parts.append("🟡 销售类型: 非零售机")
                                    
                                    notification_parts.append("")
                                    notification_parts.append("✅ 此设备符合条件，请及时处理！")
                                    
                                    notification_message = "\n".join(notification_parts)
                                    
                                    # 发送文本通知
                                    WebhookNotifier.send_notification(notification_message)
                                    
                                    # 上传图片并发送图片通知
                                    # 使用最终保存的图片路径
                                    image_to_upload = final_image_path if final_image_path and os.path.exists(final_image_path) else downloaded_path
                                    if image_to_upload and os.path.exists(image_to_upload):
                                        uploaded_image_key = feishu.upload_image(image_to_upload)
                                        if uploaded_image_key:
                                            WebhookNotifier.send_notification(None, uploaded_image_key)
                                            logger.info(f"[{brand}] 已发送符合条件的设备通知和图片到Webhook")
                                        else:
                                            logger.warning(f"[{brand}] 图片上传失败，仅发送文本通知")
                                    else:
                                        logger.warning(f"[{brand}] 图片文件不存在，无法上传: {image_to_upload}")
                                
                                # 格式化用户回复消息
                                reply_parts = []
                                reply_parts.append(f"📱 {brand.upper()}设备查询结果")
                                reply_parts.append("")
                                reply_parts.append(f"🔢 商品唯一码: {product_code}")
                                reply_parts.append(f"📊 查询次数: 第{query_count}次查询")
                                
                                if query_result['success']:
                                    device_info = query_result.get('device_info', {})
                                    
                                    # 检查是否符合条件
                                    meets_conditions, condition_reason = check_meets_conditions(brand, device_info)
                                    
                                    if meets_conditions:
                                        reply_parts.append("🟢 符合条件")
                                        reply_parts.append(f"📄 设备型号: {device_info.get('model', '未知')}")
                                    else:
                                        reply_parts.append("🔴 不符合条件")
                                    
                                    # reply_parts.append(f"📝 条件说明: {condition_reason}")
                                        
                                else:
                                    reply_parts.append("❌ 查询状态: 失败")
                                    reply_parts.append(f"📛 失败原因: {query_result.get('error_message', '未知错误')}")
                                
                                reply_message = "\n".join(reply_parts)
                                feishu.reply_message(
                                    message_id=message_id,
                                    message=reply_message,
                                    chat_type=chat_type
                                )
                                
                            else:
                                feishu.reply_message(
                                    message_id=message_id,
                                    message=f'[{brand}] ❌ 未识别到有效的商品唯一码（15-20位数字）',
                                    chat_type=chat_type
                                )
                                # 删除临时文件
                                if os.path.exists(downloaded_path):
                                    os.remove(downloaded_path)
                            
                        else:
                            feishu.reply_message(
                                message_id=message_id,
                                message=f'[{brand}] ❌ 文字识别失败，请确保图片清晰且包含商品条码。',
                                chat_type=chat_type
                            )
                            # 删除临时文件
                            if os.path.exists(downloaded_path):
                                os.remove(downloaded_path)
                            
                    else:
                        feishu.reply_message(
                            message_id=message_id,
                            message=f'[{brand}] ❌ 下载图片失败，请稍后重试。',
                            chat_type=chat_type
                        )
                
                logger.info(f"消息处理完成: {message_id}")
                    
        except Exception as e:
            logger.error(f"处理消息时出错: {e}")
            # 发送错误通知到Webhook
            error_message = f"品牌: {brand}\n错误类型: {type(e).__name__}\n错误详情: {str(e)}"
            WebhookNotifier.send_error_notification(error_message, downloaded_path, brand)
            
            # 删除临时文件
            if downloaded_path and os.path.exists(downloaded_path):
                try:
                    os.remove(downloaded_path)
                except:
                    pass
    
    # 带重试机制的机器人启动
    max_retries = 5
    retry_delay = 30
    
    for attempt in range(max_retries):
        try:
            logger.info(f"启动 {brand} 机器人 (尝试 {attempt + 1}/{max_retries})...")
            
            event_handler = EventDispatcherHandler.builder("", "") \
                .register_p2_im_message_receive_v1(handle_p2_im_message) \
                .build()

            cli = ws.Client(
                config['APP_ID'], 
                config['APP_SECRET'], 
                event_handler=event_handler, 
                log_level=LogLevel.INFO,
                auto_reconnect=True
            )
            
            cli.start()
            break
            
        except Exception as e:
            logger.error(f"启动 {brand} 机器人失败 (尝试 {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                logger.info(f"{retry_delay}秒后重试...")
                time.sleep(retry_delay)
            else:
                logger.error(f"启动 {brand} 机器人最终失败，已达到最大重试次数")

def main():
    '''使用多进程启动所有机器人'''
    logging.info("开始启动所有机器人...")
    
    processes = []
    
    for brand, config in ROBOT_CONFIGS.items():
        process = multiprocessing.Process(
            target=start_robot_process, 
            args=(brand, config),
            name=f"Robot-{brand}"
        )
        processes.append(process)
        process.start()
        logging.info(f"{brand} 机器人进程已启动 (PID: {process.pid})")
        time.sleep(3)
    
    logging.info("所有机器人进程已启动，按 Ctrl+C 停止")
    
    try:
        while True:
            time.sleep(60)
            for process in processes:
                if not process.is_alive():
                    logging.warning(f"进程 {process.name} 已停止，退出码: {process.exitcode}")
    except KeyboardInterrupt:
        logging.info("\n正在停止所有机器人...")
        for process in processes:
            if process.is_alive():
                process.terminate()
        for process in processes:
            process.join(timeout=10)
        logging.info("所有机器人已停止")

if __name__ == "__main__":
    multiprocessing.set_start_method('spawn')
    main()
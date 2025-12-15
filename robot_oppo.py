import requests
import json
import os
import time
import base64
import urllib.parse
import re
import lark_oapi as lark
from lark_oapi import EventDispatcherHandler, ws, JSON, im, LogLevel
from lark_oapi.api.im.v1 import GetMessageResourceRequest, GetMessageResourceResponse

class FeishuConfig:
    '''飞书API的配置信息'''
    APP_ID = 'cli_a9aad45314785cdc'
    APP_SECRET = '2gVQdYFTcJBAg4dJoE4n0tLmIjXaUaOw'

class DeviceQueryConfig:
    '''设备查询配置'''
    API_KEY = "39298081f644727e467e6496182391c0"
    QUERY_URL = "https://data.06api.com/api.php"

class BaiduOCRConfig:
    '''百度OCR配置信息'''
    API_KEY = "B2WT4jGOnJ7V0kq7nRKtJVw4"
    SECRET_KEY = "SjRXsgpiaUfL1onSb4Z3w6RkqUeatlfs"
    OCR_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic"

class FeishuApi:
    '''FeishuApi类用于处理与飞书API的交互'''
    TOKEN_URL = 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal'
    REPLY_MESSAGE_URL_TEMPLATE = 'https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply'
    HEADERS = {'Content-Type': 'application/json; charset=utf-8'}

    def __init__(self):
        # 创建 Lark client
        self.client = lark.Client.builder() \
            .app_id(FeishuConfig.APP_ID) \
            .app_secret(FeishuConfig.APP_SECRET) \
            .log_level(lark.LogLevel.DEBUG) \
            .build()
        
        self.session = requests.Session()
        self.token = None
        self.token_expire_time = 0
        self.refresh_token()

    def refresh_token(self):
        '''刷新token'''
        try:
            data = {'app_id': FeishuConfig.APP_ID, 'app_secret': FeishuConfig.APP_SECRET}
            response = self.session.post(self.TOKEN_URL, headers=self.HEADERS, json=data)
            response.raise_for_status()
            result = response.json()
            self.token = result.get('tenant_access_token')
            self.token_expire_time = time.time() + 5400
            print("Token刷新成功")
        except Exception as e:
            print(f"刷新token失败: {e}")
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
                print("无法获取有效token")
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
            print(f"消息回复成功")
            return response.json()
        except Exception as e:
            print(f"回复消息失败: {e}")
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
                print(f"下载图片失败, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}")
                return None

            # 确保目录存在
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            
            # 保存图片
            with open(save_path, "wb") as f:
                f.write(response.file.read())
            
            print(f"图片下载成功: {save_path}")
            return save_path
            
        except Exception as e:
            print(f"下载图片时出错: {e}")
            return None

class BaiduOCR:
    '''百度OCR识别类'''
    
    def __init__(self):
        self.access_token = None
        self.access_token_expire_time = 0
        self.refresh_access_token()
    
    def refresh_access_token(self):
        '''刷新百度OCR的access_token'''
        try:
            url = "https://aip.baidubce.com/oauth/2.0/token"
            params = {
                "grant_type": "client_credentials", 
                "client_id": BaiduOCRConfig.API_KEY, 
                "client_secret": BaiduOCRConfig.SECRET_KEY
            }
            response = requests.post(url, params=params)
            result = response.json()
            self.access_token = str(result.get("access_token"))
            self.access_token_expire_time = time.time() + 25 * 24 * 3600
            print("百度OCR Token刷新成功")
        except Exception as e:
            print(f"刷新百度OCR Token失败: {e}")
            self.access_token = None
    
    def get_access_token(self):
        '''获取有效的百度OCR access_token'''
        if not self.access_token or time.time() >= self.access_token_expire_time:
            self.refresh_access_token()
        return self.access_token
    
    def recognize_text(self, image_path):
        '''识别图片中的文字'''
        try:
            access_token = self.get_access_token()
            if not access_token:
                print("无法获取百度OCR access_token")
                return None

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
            
            print(f"开始OCR识别")
            
            response = requests.request("POST", url, headers=headers, data=payload.encode("utf-8"))
            
            print(f"OCR响应状态码: {response.status_code}")
            
            result = response.json()
            
            if 'error_code' in result:
                print(f"OCR识别错误: {result}")
                return None
            
            if 'words_result' in result:
                words_list = [item['words'] for item in result['words_result']]
                text = '\n'.join(words_list)
                print(f"OCR识别成功，识别到 {len(words_list)} 行文字")
                return text
            else:
                print(f"OCR识别失败，返回结果中没有words_result")
                return None
                
        except Exception as e:
            print(f"OCR识别时出错: {e}")
            return None

class DeviceQuery:
    '''设备查询类'''
    
    @staticmethod
    def extract_product_code(text):
        '''从OCR识别结果中提取商品唯一码'''
        # 商品唯一码通常是15-20位数字
        product_code_pattern = r'\b\d{15,20}\b'
        matches = re.findall(product_code_pattern, text)
        
        if matches:
            print(f"找到商品唯一码: {matches}")
            return matches[0]  # 返回第一个匹配的商品唯一码
        else:
            print("未找到有效的商品唯一码")
            return None
    
    @staticmethod
    def query_device_info(product_code, brand="oppo"):
        '''查询设备信息'''
        try:
            params = {
                'key': DeviceQueryConfig.API_KEY,
                'type': brand,  # 使用变量品牌
                'sn': product_code
            }
            
            print(f"开始查询设备信息，品牌: {brand}, 商品码: {product_code}")
            response = requests.get(DeviceQueryConfig.QUERY_URL, params=params)
            print(f"设备查询响应状态码: {response.status_code}")
            
            result = response.json()
            
            if result.get('code') == 0:
                # 查询成功
                data = result.get('data', {})
                return {
                    'success': True,
                    'product_code': product_code,
                    'device_info': data
                }
            else:
                # 查询失败
                error_code = result.get('code')
                error_message = result.get('message', '未知错误')
                return {
                    'success': False,
                    'error_code': error_code,
                    'error_message': error_message
                }
                
        except Exception as e:
            print(f"设备查询时出错: {e}")
            return {
                'success': False,
                'error_code': '9999',
                'error_message': f'查询异常: {str(e)}'
            }

# 全局变量，用于避免重复处理消息
processed_messages = set()

def should_process_message(message_data):
    '''判断是否应该处理该消息'''
    try:
        message_id = message_data["event"]["message"]["message_id"]
        
        # 检查是否已经处理过该消息
        if message_id in processed_messages:
            return False
        
        # 只处理用户发送的消息
        sender_type = message_data["event"]["sender"]["sender_type"]
        if sender_type != "user":
            return False
        
        return True
        
    except Exception as e:
        print(f"判断消息处理条件时出错: {e}")
        return False

def save_ocr_result(product_code, ocr_text, base_dir="oppo"):
    '''保存OCR识别结果到txt文件'''
    try:
        # 确保目录存在
        if not os.path.exists(base_dir):
            os.makedirs(base_dir)
        
        # 生成文件名
        timestamp = int(time.time())
        filename = f"{product_code}_{timestamp}.txt"
        filepath = os.path.join(base_dir, filename)
        
        # 保存内容
        content = f"商品唯一码: {product_code}\n识别时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\nOCR识别结果:\n{ocr_text}"
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"OCR结果已保存: {filepath}")
        return filepath
    except Exception as e:
        print(f"保存OCR结果失败: {e}")
        return None

def format_device_info(product_code, query_result):
    '''格式化设备信息回复'''
    # 构建回复消息
    message_parts = []
    message_parts.append("📱 设备信息查询结果")
    message_parts.append("")
    message_parts.append(f"🔢 商品唯一码: {product_code}")
    
    if query_result['success']:
        # 查询成功的情况
        device_info = query_result.get('device_info', {})
        imei = device_info.get('imei', '未知')
        
        message_parts.append("✅ 查询状态: 成功")
        message_parts.append(f"📱 IMEI码: {imei}")
        message_parts.append(f"📄 设备型号: {device_info.get('model', '未知')}")
        
        # 激活状态
        purchase_info = device_info.get('purchase', {})
        activate_date = purchase_info.get('activated', '')
        if activate_date:
            message_parts.append(f"🟢 设备状态: 已激活")
            message_parts.append(f"📅 激活日期: {activate_date}")
        else:
            message_parts.append("🟡 设备状态: 未激活")
            
    else:
        # 查询失败的情况
        message_parts.append("❌ 查询状态: 失败")
        message_parts.append(f"📛 失败原因: {query_result.get('error_message', '未知错误')}")
    
    return "\n".join(message_parts)

def handle_p2_im_message(data: im.v1.P2ImMessageReceiveV1):
    '''只处理接收消息事件'''
    try:
        data_dict = json.loads(JSON.marshal(data)) 
        message_id = data_dict["event"]["message"]["message_id"]
        chat_type = data_dict["event"]["message"]["chat_type"]
        
        print(f"收到新消息: {message_id}, 类型: {data_dict['event']['message']['message_type']}, 聊天类型: {chat_type}")
        
        # 检查是否应该处理该消息
        if not should_process_message(data_dict):
            return
        
        # 标记为已处理
        processed_messages.add(message_id)
        
        msg_type = data_dict["event"]["message"]["message_type"]
        
        feishu = FeishuApi()
        
        # 处理文本消息
        if msg_type == "text":
            content = eval(data.event.message.content).get("text", "")
            content = content.split(" ")[-1].replace('"}', '').strip()
            feishu.reply_message(
                message_id=message_id, 
                message=f'已收到消息，请发送设备条码图片进行查询',
                chat_type=chat_type
            )
            print(f"已回复文本消息")
        
        # 处理图片消息
        elif msg_type == "image":
            # 获取图片信息
            image_content = eval(data.event.message.content)
            image_key = image_content.get("image_key", "")
            
            if image_key:
                print(f"开始处理图片，image_key: {image_key}")
                
                # 创建保存目录
                download_dir = "oppo"
                if not os.path.exists(download_dir):
                    os.makedirs(download_dir)
                
                # 生成保存路径
                timestamp = int(time.time())
                save_path = os.path.join(download_dir, f"{image_key}_{timestamp}.jpg")
                
                try:
                    # 1. 先回复确认消息
                    feishu.reply_message(
                        message_id=message_id,
                        message='正在识别图片中的商品唯一码...',
                        chat_type=chat_type
                    )
                    
                    # 2. 下载图片
                    downloaded_path = feishu.download_image(message_id, image_key, save_path)
                    
                    if downloaded_path:
                        print(f"图片下载完成，保存路径: {downloaded_path}")
                        
                        # 3. 使用百度OCR识别文字
                        print("开始OCR文字识别...")
                        ocr = BaiduOCR()
                        recognized_text = ocr.recognize_text(downloaded_path)
                        
                        if recognized_text:
                            print(f"OCR识别成功")
                            
                            # 4. 提取商品唯一码
                            product_code = DeviceQuery.extract_product_code(recognized_text)
                            
                            if product_code:
                                # 保存OCR结果
                                save_ocr_result(product_code, recognized_text, "oppo")
                                
                                # 5. 查询设备信息
                                feishu.reply_message(
                                    message_id=message_id,
                                    message=f'已识别到商品唯一码: {product_code}，正在查询设备信息...',
                                    chat_type=chat_type
                                )
                                
                                query_result = DeviceQuery.query_device_info(product_code, "oppo")
                                
                                # 6. 格式化并返回结果
                                reply_message = format_device_info(product_code, query_result)
                                feishu.reply_message(
                                    message_id=message_id,
                                    message=reply_message,
                                    chat_type=chat_type
                                )
                                
                            else:
                                feishu.reply_message(
                                    message_id=message_id,
                                    message='❌ 未识别到有效的商品唯一码（15-20位数字）',
                                    chat_type=chat_type
                                )
                            
                        else:
                            feishu.reply_message(
                                message_id=message_id,
                                message='❌ 文字识别失败，请确保图片清晰且包含商品条码。',
                                chat_type=chat_type
                            )
                            
                    else:
                        feishu.reply_message(
                            message_id=message_id,
                            message='❌ 下载图片失败，请稍后重试。',
                            chat_type=chat_type
                        )
                    
                except Exception as e:
                    print(f"处理图片时出错: {e}")
                    feishu.reply_message(
                        message_id=message_id,
                        message='❌ 处理图片时出现错误，请稍后重试。',
                        chat_type=chat_type
                    )
            else:
                feishu.reply_message(
                    message_id=message_id,
                    message='❌ 未找到有效的图片信息。',
                    chat_type=chat_type
                )
        
        # 处理其他类型的消息
        else:
            feishu.reply_message(
                message_id=message_id,
                message=f'已收到消息，请发送设备条码图片进行查询。',
                chat_type=chat_type
            )
            
        print(f"消息处理完成: {message_id}")
            
    except Exception as e:
        print(f"处理消息时出错: {e}")

def main():
    '''启动飞书长连接 WebSocket客户端'''
    event_handler = EventDispatcherHandler.builder("", "") \
        .register_p2_im_message_receive_v1(handle_p2_im_message) \
        .build()

    cli = ws.Client(FeishuConfig.APP_ID, FeishuConfig.APP_SECRET, event_handler=event_handler, log_level=LogLevel.DEBUG)
    cli.start()

if __name__ == "__main__":
    main()
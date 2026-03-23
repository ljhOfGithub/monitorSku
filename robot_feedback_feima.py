import os
import json
import time
import re
import threading
import requests
import logging
import urllib.parse
import asyncio
import random
from datetime import datetime, timedelta
from urllib.parse import quote
import lark_oapi as lark
from lark_oapi.api.im.v1 import *

# --- 引入 Playwright 相关库 ---
from playwright.async_api import async_playwright
# --- 引入 Stealth 库 ---
from playwright_stealth import Stealth

# --- 配置区域 ---
APP_ID = "cli_a93523ed41b95cd3"
APP_SECRET = "rzcvBKwmBtymmDow2jeCbf2AXcUC5mLb"

# 监控结果通知 Webhook 数组 (发现可买时发送)
MONITOR_WEBHOOKS = [
    "https://open.feishu.cn/open-apis/bot/v2/hook/5c3f123d-6016-4eb1-b7f4-e4ea5bd1086b"
]

# 轮询总结报告 Webhook 数组 (每轮结束发送)
SUMMARY_WEBHOOKS = [
    "https://open.feishu.cn/open-apis/bot/v2/hook/4c5f4b84-02ae-484c-a15f-39ae9d918603"
]

DATA_FILE = "feedback.json"
PROCESSED_MSGS_FILE = "feedback_processed_messages.json" # 新增：已处理消息记录文件

# 代理配置 (Requests 格式)
PROXY_CONFIG = {
    "http": "http://t16930018764966:87qis953@y516.kdltps.com:15818",
    "https": "http://t16930018764966:87qis953@y516.kdltps.com:15818"
}

# Playwright 代理配置
PLAYWRIGHT_PROXY = {
    "server": "http://y516.kdltps.com:15818",
    "username": "t16930018764966",
    "password": "87qis953"
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 数据持久化 ---

def init_data_file():
    """初始化文件，确保即使为空也不会报错"""
    if not os.path.exists(DATA_FILE) or os.path.getsize(DATA_FILE) == 0:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f)
        logging.info(f"初始化空数据文件: {DATA_FILE}")
    
    # 初始化已处理消息文件
    if not os.path.exists(PROCESSED_MSGS_FILE) or os.path.getsize(PROCESSED_MSGS_FILE) == 0:
        with open(PROCESSED_MSGS_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f)
        logging.info(f"初始化已处理消息文件: {PROCESSED_MSGS_FILE}")

def load_processed_messages():
    """加载已处理的消息ID"""
    try:
        with open(PROCESSED_MSGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_processed_message(msg_id):
    """保存已处理的消息ID"""
    try:
        msgs = load_processed_messages()
        msgs[msg_id] = datetime.now().timestamp()
        # 限制记录数量，防止文件无限增大（保留最近500条）
        if len(msgs) > 500:
            sorted_keys = sorted(msgs.keys(), key=lambda k: msgs[k])
            for k in sorted_keys[:-500]:
                del msgs[k]
        with open(PROCESSED_MSGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(msgs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"保存消息状态失败: {e}")

def load_data():
    """从文件加载数据，增加对空文件和损坏文件的兼容性"""
    if not os.path.exists(DATA_FILE):
        return []
    try:
        # 检查文件大小，如果为0直接返回空列表
        if os.path.getsize(DATA_FILE) == 0:
            return []
            
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content: # 如果文件内容全是空格或为空字符串
                return []
            return json.loads(content)
    except (json.JSONDecodeError, Exception) as e:
        logging.error(f"加载数据失败: {e}，重置为空列表")
        return []

def save_data(data):
    """保存数据到文件"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"保存数据失败: {e}")

# --- 核心 logic ---

async def check_url_status(url):
    """使用 Stealth 增强版 Chrome 模拟访问检查链接，并提取价格"""
    
    ua_list = [
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 15_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.6 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36"
    ]

    async with Stealth().use_async(async_playwright()) as p:
        browser = None
        try:
            browser = await p.chromium.launch(
                channel="chrome", 
                headless=False, 
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-blink-features=AutomationControlled"]
            )
            
            context = await browser.new_context(
                user_agent=random.choice(ua_list),
                proxy=PLAYWRIGHT_PROXY,
                viewport={'width': 375, 'height': 812},
                is_mobile=True,
                has_touch=True
            )
            
            page = await context.new_page()
            await page.goto(url, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(10, 20))

            # 1. 检查是否失效 (已售出/下架)
            target_xpath = 'xpath=//*[@id="/ppinspect/jdReport?stamp=1"]//taro-text-core[contains(@class, "sellout")]'
            invalid_keywords = ["已下架", "已售出", "商品不存在", "已删除"]
            
            is_sold_out = False
            try:
                locator = page.locator(target_xpath)
                if await locator.count() > 0:
                    status_text = await locator.inner_text()
                    if any(kw in status_text for kw in ["已售出", "已下架"]):
                        is_sold_out = True
            except: pass

            page_content = await page.content()
            if any(kw in page_content for kw in invalid_keywords):
                is_sold_out = True

            if is_sold_out:
                return False, None

            # 2. 如果未售出，提取具体价格数值
            # XPath: //taro-view-core[contains(@class, "index-module__buy")]//taro-text-core[contains(@class, "index-module__num")]
            price_value = "未知"
            try:
                price_xpath = '//taro-view-core[contains(@class, "index-module__buy")]//taro-text-core[contains(@class, "index-module__num")]'
                price_locator = page.locator(price_xpath)
                if await price_locator.count() > 0:
                    # 获取文本内容并提取数字部分
                    raw_price = await price_locator.first.inner_text()
                    # 匹配数字和小数点
                    match = re.search(r'(\d+\.?\d*)', raw_price)
                    if match:
                        price_value = match.group(1)
            except Exception as e:
                logging.warning(f"价格抓取异常: {e}")

            return True, price_value

        except Exception as e:
            logging.error(f"Stealth 检查异常 {url}: {e}")
            return False, None
        finally:
            if browser:
                await browser.close()

def get_real_url(short_url):
    """解析京东短链接获取真实落地页 URL"""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        # response = requests.get(short_url, proxies=PROXY_CONFIG, timeout=10, headers=headers, allow_redirects=True)
        response = requests.get(short_url, timeout=10, headers=headers, allow_redirects=True)
        return response.url
    except Exception as e:
        logging.error(f"短链接解析失败 {short_url}: {e}")
        return None

def send_to_webhooks(webhook_list, payload):
    """通用 Webhook 发送函数"""
    for url in webhook_list:
        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            logging.error(f"Webhook {url} 发送失败: {e}")

def send_monitor_notification(task, price):
    """发送监控成功通知到 MONITOR_WEBHOOKS"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    inspect_id = task.get('inspectSkuId', '')
    target_url = f"https://paipai.m.jd.com/ppinspect/jdReport?inspectSkuId={inspect_id}"
    
    params_dict = {"category": "jump", "des": "m", "url": target_url}
    encoded_params = quote(json.dumps(params_dict, separators=(',', ':')))
    deep_link_url = f"openapp.jdmobile://virtual?params={encoded_params}"

    payload = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": "💰 发现可买单品！",
                    "content": [
                        [
                            {"tag": "text", "text": f"📋 质检单号: {inspect_id}\n"},
                            {"tag": "text", "text": f"💵 当前价格: {price} 元\n"},
                            {"tag": "text", "text": f"✅ 状态: 可访问/未售出\n"},
                            {"tag": "text", "text": f"🕐 发现时间: {now_str}\n\n"}
                        ],
                        [
                            {"tag": "a", "text": "🔗 点击购买 (京东APP)", "href": deep_link_url}
                        ]
                    ]
                }
            }
        }
    }
    send_to_webhooks(MONITOR_WEBHOOKS, payload)

# --- 消息接收回调 ---

def do_p2_im_message_receive_v1(data: P2ImMessageReceiveV1):
    msg_id = data.event.message.message_id
    processed_msgs = load_processed_messages()
    if msg_id in processed_msgs:
        return
    save_processed_message(msg_id)

    msg_content = json.loads(data.event.message.content)
    full_text = msg_content.get('text', str(msg_content))
    lines = full_text.split('\n')
    
    tasks = load_data()
    results_summary = []
    
    short_url_pattern = r'https?://3\.cn/[a-zA-Z0-9\-]+'
    paipai_url_pattern = r'https%3A//paipai\.m\.jd\.com[a-zA-Z0-9%._\-\[\]]+'

    added_new = 0
    for line in lines:
        line = line.strip()
        if not line: continue
        found_short = re.findall(short_url_pattern, line)
        found_paipai = re.findall(paipai_url_pattern, line)
        
        clean_url = ""
        if found_short: clean_url = get_real_url(found_short[0])
        elif found_paipai: clean_url = urllib.parse.unquote(found_paipai[0]).split('"')[0].split('}')[0]
        
        if clean_url:
            sku_match = re.search(r'inspectSkuId[%=](\d+)', clean_url)
            if sku_match: 
                inspect_sku_id = sku_match.group(1)
                if any(t['inspectSkuId'] == inspect_sku_id for t in tasks):
                    results_summary.append(f"🟡 {inspect_sku_id} (队列中)")
                else:
                    tasks.append({
                        "inspectSkuId": inspect_sku_id,
                        "url": clean_url,
                        "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "expire_at": (datetime.now() + timedelta(hours=12)).timestamp(),
                        "check_count": 0
                    })
                    added_new += 1
                    results_summary.append(f"🟢 {inspect_sku_id} (开始监控)")
    
    if added_new > 0:
        save_data(tasks)
        
    summary_text = f"📥 **导入总结**\n" + "\n".join(results_summary) + f"\n📈 总量: {len(tasks)}"
    send_to_webhooks(MONITOR_WEBHOOKS, {"msg_type": "text", "content": {"text": summary_text}})

# --- 定时轮询线程 (异步版) ---

async def scanner_loop():
    logging.info("监控轮询器启动...")
    while True:
        try:
            tasks = load_data()
            if not tasks:
                await asyncio.sleep(10)
                continue

            now_ts = datetime.now().timestamp()
            updated_tasks = []
            accessible_items = []

            for task in tasks:
                if now_ts > task['expire_at']: continue
                
                task['check_count'] += 1
                is_accessible, price = await check_url_status(task['url'])
                
                if is_accessible:
                    # 发送单品详细通知到监控频道
                    send_monitor_notification(task, price)
                    accessible_items.append(f"✅ {task['inspectSkuId']} | 价格: {price}")
                else:
                    updated_tasks.append(task)

            save_data(updated_tasks)
            
            # 发送一轮扫描总结报告到 SUMMARY_WEBHOOKS
            if accessible_items or len(updated_tasks) >= 0:
                summary_report = f"🔄 **自动扫描汇总报告** ({datetime.now().strftime('%H:%M:%S')})\n"
                summary_report += f"━━━━━━━━━━━━━━━\n"
                if accessible_items:
                    summary_report += "🎊 本轮发现可买:\n" + "\n".join(accessible_items) + "\n"
                else:
                    summary_report += "😴 本轮未发现可买单品\n"
                summary_report += f"━━━━━━━━━━━━━━━\n"
                summary_report += f"⏳ 维持监控: {len(updated_tasks)} 件"
                
                send_to_webhooks(SUMMARY_WEBHOOKS, {"msg_type": "text", "content": {"text": summary_report}})
            
        except Exception as e:
            logging.error(f"轮询异常: {e}")
            
        await asyncio.sleep(5)

def start_async_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(scanner_loop())

if __name__ == "__main__":
    init_data_file()
    threading.Thread(target=start_async_loop, daemon=True).start()

    event_handler = lark.EventDispatcherHandler.builder("", "") \
        .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1).build()

    cli = lark.ws.Client(APP_ID, APP_SECRET, event_handler=event_handler, log_level=lark.LogLevel.INFO)
    logging.info("=== 机器人服务已就绪 (价格抓取+多Webhook报告版) ===")
    cli.start()
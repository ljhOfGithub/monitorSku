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

LOG_DIR = "feedback_logs"
DATA_FILE = "feedback.json"
PROCESSED_MSGS_FILE = "feedback_processed_messages.json" 

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

# --- 数据持久化与日志管理 ---

def init_env():
    """初始化环境"""
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
        logging.info(f"创建日志文件夹: {LOG_DIR}")
    
    if not os.path.exists(DATA_FILE) or os.path.getsize(DATA_FILE) == 0:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f)
    
    if not os.path.exists(PROCESSED_MSGS_FILE) or os.path.getsize(PROCESSED_MSGS_FILE) == 0:
        with open(PROCESSED_MSGS_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f)

def write_task_log(sku_id, record):
    """为每个 SKU ID 记录独立的 JSON 日志"""
    file_path = os.path.join(LOG_DIR, f"{sku_id}.json")
    data = []
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except: data = []
    
    data.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        **record
    })
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_processed_messages():
    try:
        with open(PROCESSED_MSGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except: return {}

def save_processed_message(msg_id):
    try:
        msgs = load_processed_messages()
        msgs[msg_id] = datetime.now().timestamp()
        if len(msgs) > 500:
            sorted_keys = sorted(msgs.keys(), key=lambda k: msgs[k])
            for k in sorted_keys[:-500]: del msgs[k]
        with open(PROCESSED_MSGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(msgs, f, ensure_ascii=False, indent=2)
    except Exception as e: logging.error(f"保存消息状态失败: {e}")

def load_data():
    if not os.path.exists(DATA_FILE): return []
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except: return []

def save_data(data):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e: logging.error(f"保存数据失败: {e}")

# --- 核心逻辑 ---

async def process_single_task(browser, task):
    """独立处理单个 SKU 任务"""
    sku_id = task['inspectSkuId']
    ua_list = [
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36"
    ]

    # 按照并发推荐用法：创建独立 Context
    context = await browser.new_context(
        user_agent=random.choice(ua_list),
        proxy=PLAYWRIGHT_PROXY,
        viewport={'width': 375, 'height': 812},
        is_mobile=True,
        has_touch=True
    )
    
    page = await context.new_page()
    result = {"is_accessible": False, "price": "未知", "error": None}

    try:
        logging.info(f"任务 {sku_id} 正在启动独立窗口访问...")
        await page.goto(task['url'], timeout=60000, wait_until="domcontentloaded")
        
        # 默认每个页面加载 10-20 秒
        await asyncio.sleep(random.uniform(10, 20))

        # 1. 检查失效状态
        target_xpath = 'xpath=//*[@id="/ppinspect/jdReport?stamp=1"]//taro-text-core[contains(@class, "sellout")]'
        is_sold_out = False
        
        if await page.locator(target_xpath).count() > 0:
            status_text = await page.locator(target_xpath).inner_text()
            if any(kw in status_text for kw in ["已售出", "已下架"]):
                is_sold_out = True

        page_content = await page.content()
        if any(kw in page_content for kw in ["已下架", "已售出", "商品不存在"]):
            is_sold_out = True

        if not is_sold_out:
            result["is_accessible"] = True
            # 2. 抓取具体价格
            price_xpath = '//taro-view-core[contains(@class, "index-module__buy")]//taro-text-core[contains(@class, "index-module__num")]/text()[last()]'
            if await page.locator(price_xpath).count() > 0:
                raw_price = await page.locator(price_xpath).first.inner_text()
                match = re.search(r'(\d+\.?\d*)', raw_price)
                if match: result["price"] = match.group(1)

    except Exception as e:
        result["error"] = str(e)
        logging.error(f"处理任务 {sku_id} 时出错: {e}")
    finally:
        await context.close()
        # 记录到本地独立 JSON 文件
        write_task_log(sku_id, result)
        # 每个 SKU 冷却 5 秒
        await asyncio.sleep(5)
    
    return result

def send_to_webhooks(webhook_list, payload):
    for url in webhook_list:
        try: requests.post(url, json=payload, timeout=10)
        except Exception as e: logging.error(f"Webhook 发送失败: {e}")

def send_monitor_notification(task, price, notify_count):
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
                    "title": f"💰 发现可买单品！(提醒 {notify_count}/5)",
                    "content": [
                        [
                            {"tag": "text", "text": f"📋 质检单号: {inspect_id}\n"},
                            {"tag": "text", "text": f"💵 当前价格: {price} 元\n"},
                            {"tag": "text", "text": f"🕐 发现时间: {now_str}\n\n"}
                        ],
                        [{"tag": "a", "text": "🔗 点击购买 (京东APP)", "href": deep_link_url}]
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
    if msg_id in processed_msgs: return
    save_processed_message(msg_id)

    msg_content = json.loads(data.event.message.content)
    full_text = msg_content.get('text', str(msg_content))
    lines = full_text.split('\n')
    
    tasks = load_data()
    results_summary = []
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        # 简单的短链接与拍拍链接识别
        clean_url = ""
        if "3.cn/" in line:
            found = re.findall(r'https?://3\.cn/[a-zA-Z0-9\-]+', line)
            if found:
                # 获取真实 URL
                try:
                    res = requests.get(found[0], proxies=PROXY_CONFIG, timeout=10, allow_redirects=True)
                    clean_url = res.url
                except: pass
        elif "paipai.m.jd.com" in line:
            clean_url = urllib.parse.unquote(line)

        if clean_url:
            sku_match = re.search(r'inspectSkuId[%=](\d+)', clean_url)
            if sku_match: 
                inspect_sku_id = sku_match.group(1)
                if not any(t['inspectSkuId'] == inspect_sku_id for t in tasks):
                    tasks.append({
                        "inspectSkuId": inspect_sku_id,
                        "url": clean_url,
                        "expire_at": (datetime.now() + timedelta(hours=12)).timestamp(),
                        "notify_count": 0 # 记录可买提醒次数
                    })
                    results_summary.append(f"🟢 {inspect_sku_id} (监控中)")
    
    if results_summary:
        save_data(tasks)
        send_to_webhooks(MONITOR_WEBHOOKS, {"msg_type": "text", "content": {"text": "📥 批量导入成功\n" + "\n".join(results_summary)}})

# --- 轮询器 ---

async def scanner_loop():
    logging.info("定期检查器循环 (Stealth 推荐模式) 已启动...")
    
    # 按照推荐用法：所有 Page 共享 Stealth 应用
    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(headless=True) # 默认有头模式
        
        while True:
            try:
                tasks = load_data()
                if not tasks:
                    await asyncio.sleep(10)
                    continue

                updated_tasks = []
                accessible_items = []
                
                # 并发处理当前所有任务
                sem = asyncio.Semaphore(3) # 限制同时打开的窗口数，防止内存溢出
                async def sem_task(t):
                    async with sem:
                        return await process_single_task(browser, t)

                # 收集本轮结果
                futures = [sem_task(task) for task in tasks]
                results = await asyncio.gather(*futures)

                for i, res in enumerate(results):
                    task = tasks[i]
                    if res["is_accessible"]:
                        task['notify_count'] += 1
                        send_monitor_notification(task, res["price"], task['notify_count'])
                        accessible_items.append(f"✅ {task['inspectSkuId']} | 价格: {res['price']} (提醒{task['notify_count']}/5)")
                        
                        # 可买单品提醒五次后移除
                        if task['notify_count'] < 5:
                            updated_tasks.append(task)
                        else:
                            logging.info(f"任务 {task['inspectSkuId']} 已满5次提醒，移除监控。")
                    else:
                        # 未过期的继续监控
                        if datetime.now().timestamp() < task.get('expire_at', 0):
                            updated_tasks.append(task)

                save_data(updated_tasks)
                
                # 发送轮询总结报告
                summary_report = f"🔄 轮询报告 ({datetime.now().strftime('%H:%M:%S')})\n"
                summary_report += f"━━━━━━━━━━━━━━━\n"
                summary_report += "\n".join(accessible_items) if accessible_items else "😴 本轮未发现可买\n"
                summary_report += f"━━━━━━━━━━━━━━━\n"
                summary_report += f"⏳ 存活监控: {len(updated_tasks)} 件"
                send_to_webhooks(SUMMARY_WEBHOOKS, {"msg_type": "text", "content": {"text": summary_report}})
                
            except Exception as e:
                logging.error(f"轮询主循环异常: {e}")
            
            await asyncio.sleep(60)

def start_async_loop():
    asyncio.run(scanner_loop())

if __name__ == "__main__":
    init_env()
    threading.Thread(target=start_async_loop, daemon=True).start()

    event_handler = lark.EventDispatcherHandler.builder("", "") \
        .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1).build()

    cli = lark.ws.Client(APP_ID, APP_SECRET, event_handler=event_handler, log_level=lark.LogLevel.INFO)
    cli.start()
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
WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/5c3f123d-6016-4eb1-b7f4-e4ea5bd1086b"
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
    """使用 Stealth 增强版 Chrome 模拟访问检查链接"""
    
    # 定义随机 User-Agent 池 (模拟移动端设备)
    ua_list = [
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 15_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.6 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36"
    ]

    # 使用 Stealth().use_async() 作为推荐用法，应用到所有后续创建的 context 和 page
    async with Stealth().use_async(async_playwright()) as p:
        browser = None
        try:
            # 启动本地 Chrome 渠道
            browser = await p.chromium.launch(
                channel="chrome", 
                headless=True, # 这里根据用户提供的最新脚本改为True，如需调试可改False
                args=[
                    "--no-sandbox", 
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            
            # 随机化指纹配置
            random_ua = random.choice(ua_list)
            
            # 创建上下文
            context = await browser.new_context(
                user_agent=random_ua,
                proxy=PLAYWRIGHT_PROXY,
                viewport={'width': 375, 'height': 812}, # 模拟 iPhone X 尺寸
                is_mobile=True,
                has_touch=True
            )
            
            page = await context.new_page()
            
            logging.info(f"正在通过 Stealth-Chrome 访问: {url}")
            
            # 设置导航超时
            await page.goto(url, timeout=60000, wait_until="domcontentloaded")
            
            # 等待渲染并随机延迟模拟真人行为
            await asyncio.sleep(random.uniform(2, 4))

            # 目标 XPath 检查
            target_xpath = 'xpath=//*[@id="/ppinspect/jdReport?stamp=1"]//taro-text-core[contains(@class, "sellout")]'
            
            try:
                locator = page.locator(target_xpath)
                # 检查元素是否存在且可见
                if await locator.count() > 0:
                    status_text = await locator.inner_text()
                    status_text = status_text.strip()
                    
                    if "已售出" in status_text or "已下架" in status_text:
                        logging.info(f"❌ 监控发现已售出/下架: {url}")
                        return False
            except Exception as e:
                pass

            # 关键词兜底检查
            page_content = await page.content()
            invalid_keywords = ["已下架", "已售出", "商品不存在", "已删除"]
            for kw in invalid_keywords:
                if kw in page_content:
                    logging.info(f"❌ 关键字匹配失效 '{kw}': {url}")
                    return False

            if len(page_content) < 3000:
                logging.warning(f"⚠️ 页面内容异常过少: {url}")
                return False

            logging.info(f"✅ 监控链接依然有效: {url}")
            return True

        except Exception as e:
            logging.error(f"Stealth 检查异常 {url}: {e}")
            return False
        finally:
            if browser:
                await browser.close()

def get_real_url(short_url):
    """解析京东短链接获取真实落地页 URL"""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        # allow_redirects=True 会自动跟随 302 跳转
        response = requests.get(short_url, proxies=PROXY_CONFIG, timeout=10, headers=headers, allow_redirects=True)
        return response.url
    except Exception as e:
        logging.error(f"短链接解析失败 {short_url}: {e}")
        return None

def send_webhook_notification(task, is_success=True):
    """发送符合要求的格式化通知"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if not is_success:
        return

    # --- 构造 Deep Link ---
    # 判断是否为单品
    inspect_id = task.get('inspectSkuId', '')
    target_url = f"https://paipai.m.jd.com/ppinspect/jdReport?inspectSkuId={inspect_id}"
    
    # 构建京东协议跳转链接
    params_dict = {"category": "jump", "des": "m", "url": target_url}
    encoded_params = quote(json.dumps(params_dict, separators=(',', ':')))
    deep_link_url = f"openapp.jdmobile://virtual?params={encoded_params}"

    # --- 构造富文本 Payload ---
    payload = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": "🎉 链接可访问通知",
                    "content": [
                        [
                            {"tag": "text", "text": f"📋 主SKU: {task.get('main_sku', '未知')}\n"},
                            {"tag": "text", "text": f"🔍 质检单号: {inspect_id}\n"},
                            {"tag": "text", "text": f"✅ 检查结果: 可访问\n"},
                            {"tag": "text", "text": f"📊 检查次数: {task.get('check_count', 0)}\n"},
                            {"tag": "text", "text": f"🕐 检查时间: {now_str}\n\n"}
                        ],
                        [
                            {"tag": "a", "text": "🔗 点击购买 (京东APP)", "href": deep_link_url}
                        ]
                    ]
                }
            }
        }
    }

    try:
        requests.post(WEBHOOK_URL, json=payload, timeout=10)
    except Exception as e:
        logging.error(f"Webhook 发送失败: {e}")

# --- 消息接收回调 ---

def do_p2_im_message_receive_v1(data: P2ImMessageReceiveV1):
    # --- 新增：消息去重判断 ---
    msg_id = data.event.message.message_id
    processed_msgs = load_processed_messages()
    if msg_id in processed_msgs:
        return
    
    save_processed_message(msg_id)
    # -----------------------

    msg_content = json.loads(data.event.message.content)
    full_text = str(msg_content.get('text', '')) if 'text' in msg_content else str(msg_content)
    
    # 逐行读取逻辑
    lines = full_text.split('\n')
    added_count = 0
    results_summary = []

    tasks = load_data()
    
    short_url_pattern = r'https?://3\.cn/[a-zA-Z0-9\-]+'
    paipai_url_pattern = r'https%3A//paipai\.m\.jd\.com[a-zA-Z0-9%._\-\[\]]+'

    for line in lines:
        line = line.strip()
        if not line: continue
        
        found_short = re.findall(short_url_pattern, line)
        found_paipai = re.findall(paipai_url_pattern, line)
        
        clean_url = ""
        if found_short:
            clean_url = get_real_url(found_short[0])
        elif found_paipai:
            raw_url = found_paipai[0]
            clean_url = urllib.parse.unquote(raw_url).split('"')[0].split('}')[0].split(')')[0]
        
        if clean_url:
            inspect_sku_id = ""
            sku_match = re.search(r'inspectSkuId[%=](\d+)', clean_url)
            if sku_match: 
                inspect_sku_id = sku_match.group(1)
                
                if any(t['inspectSkuId'] == inspect_sku_id for t in tasks):
                    results_summary.append(f"🟡 {inspect_sku_id} (已在监控中)")
                    continue

                new_task = {
                    "inspectSkuId": inspect_sku_id,
                    "main_sku": "批量导入", 
                    "url": clean_url,
                    "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "expire_at": (datetime.now() + timedelta(hours=6)).timestamp(),
                    "check_count": 0,
                    "history_checks": []
                }
                tasks.append(new_task)
                added_count += 1
                results_summary.append(f"🟢 {inspect_sku_id} (成功添加)")
    
    if added_count > 0:
        save_data(tasks)
        
    # 反馈批量处理结果
    status_msg = "📊 **批量任务处理结果**\n" + "\n".join(results_summary)
    requests.post(WEBHOOK_URL, json={
        "msg_type": "text", 
        "content": {"text": status_msg}
    })

# --- 定时轮询线程 (异步版) ---

async def scanner_loop():
    logging.info("定期检查器循环 (Stealth Chrome) 已启动...")
    while True:
        try:
            tasks = load_data()
            if not tasks:
                await asyncio.sleep(10)
                continue

            now_ts = datetime.now().timestamp()
            updated_tasks = []
            
            monitored_list = []
            sold_out_list = []

            for task in tasks:
                if now_ts > task['expire_at']:
                    logging.info(f"任务过期移除: {task['inspectSkuId']}")
                    continue
                
                task['check_count'] += 1
                task['history_checks'].append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                
                is_accessible = await check_url_status(task['url'])
                
                if is_accessible:
                    # 仍然有效，发送通知并移除（符合原逻辑：一旦可买就通知并停止监控）
                    send_webhook_notification(task, is_success=True)
                    monitored_list.append(f"✅ {task['inspectSkuId']} (已恢复/可访问)")
                else:
                    # 依然失效，保留在任务列表中继续监控
                    updated_tasks.append(task)
                    sold_out_list.append(f"❌ {task['inspectSkuId']} (依然失效)")

            save_data(updated_tasks)
            
            # 打印当前轮询汇总到控制台
            if monitored_list or sold_out_list:
                logging.info(f"--- 轮询汇总 ---")
                for item in monitored_list: logging.info(item)
                for item in sold_out_list: logging.info(item)
                logging.info(f"正在监控总数: {len(updated_tasks)}")
            
        except Exception as e:
            logging.error(f"轮询异常: {e}")
            
        await asyncio.sleep(60) # 每分钟检查一次

def start_async_loop():
    """在独立线程中运行异步轮询器"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(scanner_loop())

# --- 启动 ---

if __name__ == "__main__":
    init_data_file()

    # 1. 启动异步检查线程
    t = threading.Thread(target=start_async_loop, daemon=True)
    t.start()

    # 2. 启动飞书长连接
    event_handler = lark.EventDispatcherHandler.builder("", "") \
        .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1) \
        .build()

    cli = lark.ws.Client(
        APP_ID, 
        APP_SECRET, 
        event_handler=event_handler, 
        log_level=lark.LogLevel.INFO
    )
    
    logging.info("=== 飞书机器人服务启动 (多行识别+Stealth+格式化输出) ===")
    cli.start()
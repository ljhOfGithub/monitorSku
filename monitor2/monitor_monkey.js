// ==UserScript==
// @name         京东监控助手 - 数据采集器
// @namespace    http://tampermonkey.net/
// @version      1.0
// @description  采集京东页面HTML并发送到本地Python服务
// @author       Your Name
// @match        https://mall.jd.com/*
// @grant        GM_xmlhttpRequest
// @grant        GM_addStyle
// @grant        GM_notification
// @connect      127.0.0.1
// @connect      localhost
// ==/UserScript==

(function () {
    'use strict';

    // 配置：Python服务地址和端口
    const PYTHON_SERVER = 'http://127.0.0.1:5001'; // 根据实际端口修改
    const MONITOR_NAME = '22'; // 监控实例名称

    // 任务文件路径（与Python约定的路径）
    const TASK_FILE_PATH = 'C:/data/test/2/search_task.json';

    // 状态变量
    let isProcessing = false;
    let currentSearchId = null;
    let taskCheckInterval = null;

    // 添加样式
    GM_addStyle(`
        .jd-monitor-ui {
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 999999;
            background: rgba(255, 255, 255, 0.95);
            border: 2px solid #e4393c;
            border-radius: 10px;
            padding: 15px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            font-family: Arial, sans-serif;
            min-width: 300px;
            max-width: 400px;
        }
        
        .jd-monitor-header {
            background: #e4393c;
            color: white;
            padding: 10px;
            border-radius: 5px 5px 0 0;
            margin: -15px -15px 15px -15px;
            text-align: center;
            font-weight: bold;
        }
        
        .jd-monitor-status {
            margin: 10px 0;
            padding: 10px;
            border-radius: 5px;
            background: #f5f5f5;
            border-left: 4px solid #e4393c;
        }
        
        .jd-monitor-btn {
            background: #e4393c;
            color: white;
            border: none;
            padding: 8px 15px;
            border-radius: 5px;
            cursor: pointer;
            margin: 5px;
            font-size: 14px;
        }
        
        .jd-monitor-btn:hover {
            background: #c1312e;
        }
        
        .jd-monitor-btn:disabled {
            background: #cccccc;
            cursor: not-allowed;
        }
        
        .jd-monitor-log {
            max-height: 200px;
            overflow-y: auto;
            margin-top: 10px;
            padding: 10px;
            background: #f9f9f9;
            border-radius: 5px;
            font-size: 12px;
            border: 1px solid #ddd;
        }
        
        .log-entry {
            margin: 3px 0;
            padding: 3px;
            border-bottom: 1px solid #eee;
        }
        
        .log-time {
            color: #666;
            font-size: 11px;
        }
        
        .log-info {
            color: #2c7;
        }
        
        .log-warning {
            color: #f90;
        }
        
        .log-error {
            color: #e33;
        }
    `);

    // 创建UI界面
    function createUI() {
        const ui = document.createElement('div');
        ui.id = 'jd-monitor-ui';
        ui.className = 'jd-monitor-ui';
        ui.innerHTML = `
            <div class="jd-monitor-header">
                🚀 京东监控助手 v1.0
            </div>
            <div>
                <div style="margin-bottom: 10px;">
                    <strong>监控实例:</strong> ${MONITOR_NAME}
                </div>
                <div class="jd-monitor-status" id="status-display">
                    状态: 等待任务...
                </div>
                <div>
                    <button class="jd-monitor-btn" id="btn-check-task">检查任务</button>
                    <button class="jd-monitor-btn" id="btn-manual-send">手动发送当前页</button>
                    <button class="jd-monitor-btn" id="btn-clear-log">清空日志</button>
                </div>
                <div class="jd-monitor-log" id="log-display">
                    <div class="log-entry"><span class="log-time">${getTime()}</span> <span class="log-info">系统初始化完成</span></div>
                </div>
            </div>
        `;

        document.body.appendChild(ui);

        // 添加事件监听
        document.getElementById('btn-check-task').addEventListener('click', checkTaskFile);
        document.getElementById('btn-manual-send').addEventListener('click', sendCurrentPage);
        document.getElementById('btn-clear-log').addEventListener('click', clearLog);

        // 使UI可拖动
        makeDraggable(ui);

        addLog('UI界面创建完成', 'info');
    }

    // 使元素可拖动
    function makeDraggable(element) {
        let pos1 = 0, pos2 = 0, pos3 = 0, pos4 = 0;
        const header = element.querySelector('.jd-monitor-header');

        if (header) {
            header.style.cursor = 'move';
            header.addEventListener('mousedown', dragMouseDown);
        } else {
            element.style.cursor = 'move';
            element.addEventListener('mousedown', dragMouseDown);
        }

        function dragMouseDown(e) {
            e = e || window.event;
            e.preventDefault();
            pos3 = e.clientX;
            pos4 = e.clientY;
            document.addEventListener('mouseup', closeDragElement);
            document.addEventListener('mousemove', elementDrag);
        }

        function elementDrag(e) {
            e = e || window.event;
            e.preventDefault();
            pos1 = pos3 - e.clientX;
            pos2 = pos4 - e.clientY;
            pos3 = e.clientX;
            pos4 = e.clientY;
            element.style.top = (element.offsetTop - pos2) + "px";
            element.style.left = (element.offsetLeft - pos1) + "px";
        }

        function closeDragElement() {
            document.removeEventListener('mouseup', closeDragElement);
            document.removeEventListener('mousemove', elementDrag);
        }
    }

    // 日志系统
    const logs = [];
    const maxLogs = 50;

    function addLog(message, type = 'info') {
        const time = getTime();
        logs.push({ time, message, type });

        if (logs.length > maxLogs) {
            logs.shift();
        }

        updateLogDisplay();
    }

    function updateLogDisplay() {
        const logDisplay = document.getElementById('log-display');
        if (!logDisplay) return;

        logDisplay.innerHTML = logs.map(log =>
            `<div class="log-entry">
                <span class="log-time">${log.time}</span> 
                <span class="log-${log.type}">${log.message}</span>
            </div>`
        ).join('');

        // 滚动到底部
        logDisplay.scrollTop = logDisplay.scrollHeight;
    }

    function clearLog() {
        logs.length = 0;
        updateLogDisplay();
        addLog('日志已清空', 'info');
    }

    function getTime() {
        const now = new Date();
        return `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`;
    }

    // 更新状态显示
    function updateStatus(message) {
        const statusDisplay = document.getElementById('status-display');
        if (statusDisplay) {
            statusDisplay.innerHTML = `状态: ${message}`;
        }
    }

    // 检查任务文件
    async function checkTaskFile() {
        if (isProcessing) {
            addLog('当前正在处理任务，请稍后', 'warning');
            return;
        }

        updateStatus('检查任务文件中...');
        addLog('开始检查任务文件', 'info');

        try {
            // 通过GM_xmlhttpRequest读取本地文件
            const taskData = await readLocalFile(TASK_FILE_PATH);

            if (!taskData) {
                addLog('未找到任务文件或文件为空', 'warning');
                updateStatus('无任务');
                return;
            }

            // 解析任务数据
            const task = JSON.parse(taskData);
            currentSearchId = task.search_id;

            addLog(`发现任务: ${task.keyword} (${task.min_price}-${task.max_price}元)`, 'info');
            addLog(`搜索ID: ${task.search_id}`, 'info');

            // 执行搜索任务
            await executeSearchTask(task);

        } catch (error) {
            addLog(`检查任务文件失败: ${error}`, 'error');
            updateStatus('检查失败');
        }
    }

    // 读取本地文件
    function readLocalFile(filePath) {
        return new Promise((resolve, reject) => {
            // 注意：GM_xmlhttpRequest 通常不能直接访问 file:// 协议
            // 这里需要将文件放在Web服务器或使用其他方法

            // 方案：使用fetch访问本地HTTP服务器（如果Python提供了文件访问接口）
            // 或者使用扩展API（如果可用）

            // 这里简化处理，假设Python服务提供了文件访问接口
            fetch(`${PYTHON_SERVER}/${MONITOR_NAME}/get_task_file`)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}`);
                    }
                    return response.text();
                })
                .then(data => resolve(data))
                .catch(error => {
                    console.warn('通过HTTP读取文件失败，尝试其他方法:', error);

                    // 尝试直接使用GM_xmlhttpRequest（可能需要扩展权限）
                    try {
                        GM_xmlhttpRequest({
                            method: 'GET',
                            url: `file:///${filePath}`,
                            onload: function (response) {
                                resolve(response.responseText);
                            },
                            onerror: function (error) {
                                reject(new Error(`无法读取文件: ${error}`));
                            }
                        });
                    } catch (e) {
                        reject(new Error('所有文件读取方法都失败了'));
                    }
                });
        });
    }

    // 执行搜索任务
    async function executeSearchTask(task) {
        isProcessing = true;
        updateStatus(`执行任务: ${task.keyword}`);

        try {
            // 检查当前页面是否已经是目标URL
            if (window.location.href !== task.url) {
                addLog(`跳转到: ${task.url}`, 'info');
                window.location.href = task.url;

                // 等待页面加载
                await waitForPageLoad();
            }

            // 等待商品列表加载
            addLog('等待商品列表加载...', 'info');
            await waitForProductList();

            // 获取页面HTML
            addLog('获取页面HTML...', 'info');
            const htmlContent = document.documentElement.outerHTML;

            // 发送到Python服务
            addLog('发送HTML到Python服务...', 'info');
            const success = await sendHtmlToPython(task.search_id, htmlContent, task.url, task.keyword);

            if (success) {
                addLog('任务执行成功!', 'info');
                updateStatus('任务完成');

                // 删除任务文件（通过Python服务）
                await deleteTaskFile();

                // 显示成功通知
                showNotification('任务完成', `关键词: ${task.keyword} 已处理`);
            } else {
                addLog('发送失败，请重试', 'error');
                updateStatus('发送失败');
            }

        } catch (error) {
            addLog(`任务执行失败: ${error}`, 'error');
            updateStatus('执行失败');
        } finally {
            isProcessing = false;
            currentSearchId = null;
        }
    }

    // 等待页面加载
    function waitForPageLoad() {
        return new Promise((resolve) => {
            if (document.readyState === 'complete') {
                resolve();
            } else {
                window.addEventListener('load', resolve);

                // 超时处理
                setTimeout(resolve, 10000);
            }
        });
    }

    // 等待商品列表加载
    function waitForProductList() {
        return new Promise((resolve, reject) => {
            const maxWaitTime = 30000; // 30秒
            const checkInterval = 1000; // 每1秒检查一次
            const startTime = Date.now();

            const checkProducts = () => {
                // 检查京东商品列表的选择器
                const productSelectors = [
                    '.jSearchList-792077',
                    '.jSearchList',
                    '.search-list',
                    '.j-item-list',
                    '.goods-list'
                ];

                let hasProducts = false;

                for (const selector of productSelectors) {
                    const elements = document.querySelectorAll(selector);
                    if (elements.length > 0) {
                        // 进一步检查是否有商品项
                        const productItems = elements[0].querySelectorAll('.jItem, .j-sub-object, .j-subobject, .goods-item');
                        if (productItems.length > 0) {
                            hasProducts = true;
                            break;
                        }
                    }
                }

                // 检查错误消息
                const errorMessages = document.querySelectorAll('.jMessageError, .no-result, .empty-tip');
                const hasError = errorMessages.length > 0;

                if (hasProducts || hasError) {
                    addLog(hasProducts ? '找到商品列表' : '页面显示无商品', 'info');
                    resolve();
                    return;
                }

                // 超时检查
                if (Date.now() - startTime > maxWaitTime) {
                    addLog('等待商品列表超时', 'warning');
                    resolve(); // 超时也继续
                    return;
                }

                // 继续等待
                setTimeout(checkProducts, checkInterval);
            };

            checkProducts();
        });
    }

    // 发送HTML到Python服务
    function sendHtmlToPython(searchId, htmlContent, url, keyword) {
        return new Promise((resolve) => {
            const data = {
                search_id: searchId,
                html_content: htmlContent,
                url: url,
                keyword: keyword
            };

            GM_xmlhttpRequest({
                method: 'POST',
                url: `${PYTHON_SERVER}/${MONITOR_NAME}/receive_html`,
                headers: {
                    'Content-Type': 'application/json'
                },
                data: JSON.stringify(data),
                timeout: 30000,
                onload: function (response) {
                    if (response.status === 200) {
                        try {
                            const result = JSON.parse(response.responseText);
                            if (result.status === 'success') {
                                addLog('HTML发送成功', 'info');
                                resolve(true);
                            } else {
                                addLog(`发送失败: ${result.message}`, 'error');
                                resolve(false);
                            }
                        } catch (e) {
                            addLog('解析响应失败', 'error');
                            resolve(false);
                        }
                    } else {
                        addLog(`HTTP错误: ${response.status}`, 'error');
                        resolve(false);
                    }
                },
                onerror: function (error) {
                    addLog(`请求失败: ${error}`, 'error');
                    resolve(false);
                },
                ontimeout: function () {
                    addLog('请求超时', 'error');
                    resolve(false);
                }
            });
        });
    }

    // 删除任务文件
    function deleteTaskFile() {
        return new Promise((resolve) => {
            // 通过Python服务删除任务文件
            fetch(`${PYTHON_SERVER}/${MONITOR_NAME}/delete_task_file`, {
                method: 'POST'
            })
                .then(response => {
                    if (response.ok) {
                        addLog('任务文件已删除', 'info');
                    } else {
                        addLog('删除任务文件失败', 'warning');
                    }
                    resolve();
                })
                .catch(error => {
                    addLog(`删除文件请求失败: ${error}`, 'warning');
                    resolve();
                });
        });
    }

    // 手动发送当前页面
    function sendCurrentPage() {
        if (isProcessing) {
            addLog('当前正在处理任务，请稍后', 'warning');
            return;
        }

        const searchId = `manual_${Date.now()}`;
        const htmlContent = document.documentElement.outerHTML;
        const url = window.location.href;
        const keyword = extractKeywordFromUrl(url);

        addLog('开始手动发送当前页面...', 'info');

        sendHtmlToPython(searchId, htmlContent, url, keyword)
            .then(success => {
                if (success) {
                    addLog('手动发送成功!', 'info');
                    showNotification('发送成功', '当前页面已发送到Python服务');
                } else {
                    addLog('手动发送失败', 'error');
                }
            });
    }

    // 从URL提取关键词
    function extractKeywordFromUrl(url) {
        try {
            const urlObj = new URL(url);
            const params = new URLSearchParams(urlObj.search);
            const keywordParam = params.get('keyword');

            if (keywordParam) {
                // 尝试解码（可能双重编码）
                try {
                    return decodeURIComponent(decodeURIComponent(keywordParam));
                } catch (e) {
                    return decodeURIComponent(keywordParam);
                }
            }
        } catch (e) {
            console.error('解析URL失败:', e);
        }

        return '未知关键词';
    }

    // 显示通知
    function showNotification(title, text) {
        if (typeof GM_notification === 'function') {
            GM_notification({
                title: title,
                text: text,
                timeout: 3000
            });
        } else {
            // 降级处理：在页面上显示临时通知
            const notification = document.createElement('div');
            notification.style.cssText = `
                position: fixed;
                top: 100px;
                right: 20px;
                background: #4CAF50;
                color: white;
                padding: 15px;
                border-radius: 5px;
                z-index: 1000000;
                box-shadow: 0 2px 10px rgba(0,0,0,0.2);
                animation: fadeInOut 3s ease-in-out;
            `;

            notification.innerHTML = `<strong>${title}</strong><br>${text}`;
            document.body.appendChild(notification);

            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 3000);
        }
    }

    // 自动检查任务
    function startAutoCheck() {
        if (taskCheckInterval) {
            clearInterval(taskCheckInterval);
        }

        taskCheckInterval = setInterval(() => {
            if (!isProcessing) {
                checkTaskFile();
            }
        }, 30000); // 每30秒检查一次

        addLog('已启动自动任务检查（每30秒）', 'info');
    }

    // 初始化
    function init() {
        addLog('京东监控助手初始化...', 'info');

        // 创建UI
        createUI();

        // 测试Python服务连接
        testPythonConnection();

        // 启动自动检查
        startAutoCheck();

        addLog('初始化完成，等待任务中...', 'info');
    }

    // 测试Python服务连接
    function testPythonConnection() {
        fetch(`${PYTHON_SERVER}/${MONITOR_NAME}/health`)
            .then(response => {
                if (response.ok) {
                    return response.json();
                }
                throw new Error(`HTTP ${response.status}`);
            })
            .then(data => {
                addLog(`Python服务连接成功: ${data.name}`, 'info');
                updateStatus('服务正常');
            })
            .catch(error => {
                addLog(`Python服务连接失败: ${error}`, 'error');
                updateStatus('服务断开');
            });
    }

    // 页面加载完成后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // 添加CSS动画
    const style = document.createElement('style');
    style.textContent = `
        @keyframes fadeInOut {
            0% { opacity: 0; transform: translateY(-10px); }
            10% { opacity: 1; transform: translateY(0); }
            90% { opacity: 1; transform: translateY(0); }
            100% { opacity: 0; transform: translateY(-10px); }
        }
    `;
    document.head.appendChild(style);

})();
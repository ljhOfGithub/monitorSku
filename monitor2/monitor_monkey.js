(function () {
    'use strict';

    let config = { keywords: [], history: [] };
    let saveMode = 'python'; // 'local' 或 'python'

    // 1. 创建悬浮按钮
    const btn = document.createElement('div');
    btn.innerHTML = `
        <div id="monkey-panel" style="position:fixed;top:20%;right:20px;z-index:9999;background:#fff;padding:10px;border:1px solid #ccc;box-shadow:2px 2px 10px rgba(0,0,0,0.2);border-radius:5px;font-size:12px;">
            <div style="font-weight:bold;margin-bottom:5px;">监控控制台</div>
            <button id="btn-fetch" style="width:100%;margin-bottom:5px;">开始抓取</button>
            <select id="mode-select" style="width:100%;">
                <option value="python">Python 写入</option>
                <option value="local">浏览器缓存</option>
            </select>
            <div id="status-msg" style="margin-top:5px;color:blue;">就绪</div>
        </div>
    `;
    document.body.appendChild(btn);

    // 2. 获取配置
    async function refreshConfig() {
        if (saveMode === 'python') {
            return new Promise((resolve) => {
                GM_xmlhttpRequest({
                    method: "GET",
                    url: "http://127.0.0.1:5000/config",
                    onload: (res) => {
                        config = JSON.parse(res.responseText);
                        document.getElementById('status-msg').innerText = "配置已同步";
                        resolve();
                    },
                    onerror: () => {
                        document.getElementById('status-msg').innerText = "Python未启动";
                        resolve();
                    }
                });
            });
        } else {
            config.history = GM_getValue('local_history', []);
        }
    }

    // 3. 提取 SKU 逻辑 (参考提供的逻辑)
    function extractProducts() {
        const productLinks = [];
        const hotKeywords = ['热销', '热卖', '爆款', '热门', 'hot', '平板', '笔记本', '电脑', '键盘', '耳机', '音响'];

        // 使用指定的选择器
        const items = document.querySelectorAll('.jSearchList-792077 li.jSubObject, div.jItem');

        items.forEach(product => {
            try {
                const picLink = product.querySelector('.jPic a');
                if (!picLink) return;

                let fullUrl = picLink.getAttribute('href');
                if (fullUrl.startsWith('//')) fullUrl = 'https:' + fullUrl;

                const skuMatch = fullUrl.match(/\/(\d+)\.html/);
                if (!skuMatch) return;

                const skuId = skuMatch[1];

                // 历史去重
                if (config.history.includes(skuId)) return;

                const titleElem = product.querySelector('.jDesc a');
                const title = titleElem ? titleElem.innerText.trim() : "未知商品";

                // 过滤关键词
                const isHot = hotKeywords.some(key => title.toLowerCase().includes(key));
                if (isHot) return;

                productLinks.push({
                    sku_id: skuId,
                    url: fullUrl,
                    title: title,
                    extract_time: new Date().toISOString()
                });
            } catch (e) {
                console.error("提取出错", e);
            }
        });
        return productLinks;
    }

    // 4. 保存数据
    function saveData(data) {
        if (data.length === 0) {
            document.getElementById('status-msg').innerText = "无新商品";
            return;
        }

        if (saveMode === 'python') {
            GM_xmlhttpRequest({
                method: "POST",
                url: "http://127.0.0.1:5000/save",
                headers: { "Content-Type": "application/json" },
                data: JSON.stringify(data),
                onload: (res) => {
                    const resData = JSON.parse(res.responseText);
                    document.getElementById('status-msg').innerText = `同步成功: +${resData.new_added}`;
                    refreshConfig();
                }
            });
        } else {
            const newHistory = [...config.history, ...data.map(i => i.sku_id)];
            GM_setValue('local_history', newHistory);
            config.history = newHistory;
            document.getElementById('status-msg').innerText = `本地保存: +${data.length}`;
        }
    }

    // 绑定事件
    document.getElementById('btn-fetch').onclick = async () => {
        document.getElementById('status-msg').innerText = "正在同步配置...";
        await refreshConfig();
        const results = extractProducts();
        saveData(results);
    };

    document.getElementById('mode-select').onchange = (e) => {
        saveMode = e.target.value;
    };

})();
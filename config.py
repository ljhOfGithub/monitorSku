# config.py - 机器人配置文件

# 各品牌机器人配置
ROBOT_CONFIGS = {
    "huawei": {
        "APP_ID": "cli_a99551173af8dcd5",
        "APP_SECRET": "NbfEX7gsuajHQmRIzUTUXdFjMP6w0j23",
        "brand": "huawei",
        "data_dir": "huawei_data"
    },
    "honor": {
        "APP_ID": "cli_a9aadf07b8f8dcdd",
        "APP_SECRET": "TBVyiDrbCU97C5Oh6ZpXogXfbTveOSFp",
        "brand": "honor",
        "data_dir": "honor_data"
    },
    "xiaomi": {
        "APP_ID": "cli_a9aad9df96b85cc5",
        "APP_SECRET": "72Hhr7fZsGlVVnwhp5D5YcgEvf1XCRzD",
        "brand": "xiaomi",
        "data_dir": "xiaomi_data"
    },
    "oppo": {
        "APP_ID": "cli_a9aad45314785cdc",
        "APP_SECRET": "2gVQdYFTcJBAg4dJoE4n0tLmIjXaUaOw",
        "brand": "oppo",
        "data_dir": "oppo_data"
    },
    "realme": {
        "APP_ID": "cli_a9aacadfe0b89cc6",
        "APP_SECRET": "4OhcUsX1YvJMFXJ6jtKbWdF131wDL2gx",
        "brand": "realme",
        "data_dir": "realme_data"
    }
}

# 通用配置
class DeviceQueryConfig:
    API_KEY = "39298081f644727e467e6496182391c0"
    QUERY_URL = "https://data.06api.com/api.php"

class BaiduOCRConfig:
    API_KEY = "B2WT4jGOnJ7V0kq7nRKtJVw4"
    SECRET_KEY = "SjRXsgpiaUfL1onSb4Z3w6RkqUeatlfs"
    OCR_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic"
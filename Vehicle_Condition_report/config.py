"""
配置文件
"""

# 登录配置
LOGIN_CONFIG = {
    "url": r"http://jmcoperuat.jmc.com.cn/port/welcome",
    "username": r"hirainuat",
    "password": r"prewkhp5qn",
    "use_url_auth": True,
}

# API查询配置
API_QUERY_CONFIG = {
    "url": r"https://jmcoperuat.jmc.com.cn/port/getData",
    "payload": {'applicationId': 3, 'endDate': None, 'messageType': 7, 'source': '', 'startDate': None, 'vin': 'LXWYELR43SHNYV972'},
}

# 车况查询配置
Vehicle_Condition_Control = {
    "url": r"https://jmcoperuat.jmc.com.cn/port/control",
    "payload": {'vin': 'LXWYELR43SHNYV972', 'opType': 'STATUS_QUERY', 'op': 'OPEN', 'extendAttribute': {'$': '$'}, 'caller': 'hirainuat'},
}
Vehicle_Condition_QUERY = {
    "url": r"https://jmcoperuat.jmc.com.cn/port/getData",
    "payload": {'applicationId': 12, 'endDate': None, 'messageType': 1, 'source': '', 'startDate': None, 'vin': 'LXWYELR43SHNYV972'},
}

# 信号列表路径
SIGNAL_LIST_PATH = 'D:/PROJECT/ELD/JMC-OTA-E820X信号列表-20260515.xlsx'

# Sheet名称
SIGNAL_SHEET_NAMES = ['基础车况信号平台化', '新能源法规（新）']

# VBA读取的国标Sheet名称
GUOBIAO_SHEET_NAMES = ['新能源法规（新）']

# VBA工程名
VBA_PROJECT = 'ELD'

# 输出目录
OUTPUT_DIR = 'D:\\实车半自动化\\Test'

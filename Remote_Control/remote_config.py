"""
配置文件
"""

# VIN码（统一配置）
VIN = "LJXELDESMT8TEST04"
#VIN = "LA9AEPG2XHHLJK001"

# 登录配置
LOGIN_CONFIG = {
    "url": r"http://jmcoperuat.jmc.com.cn/port/welcome",
    "username": r"hirainuat",
    "password": r"prewkhp5qn",
    "use_url_auth": True,
}

# 远控配置
REMOTE_CONTROL_TASKS = {
    "门锁": {
        "control": {"opType": "LOCK", "ops": {"解锁": "CLOSE", "闭锁": "OPEN"}},
        "signals": [
            {"CANID": 0x1A7, "name": "TBOX_DoorLockCmd",
             "values": {0: "NoRequest", 1: "Lock", 2: "Unlock", 3: "Invalid"}},
            {"CANID": 0x310, "name": "BCM_DoorLockStsFrntLe",
             "values": {0: "Reserved", 1: "Locked", 2: "Unlocked", 3: "Fault（ Reserved）"}},
        ],
        "Sub-item-response": {"子项编码":1,"子项参数":0},
    },
    "闪灯": {
        "control": {"opType": "LIGHT_FLASH", "ops": {"开启": "OPEN"}},
        "signals": [
            {"CANID": 0x1A7, "name": "TBOX_TurnIndcrCtrlCmd",
             "values": {0: "NoRequest", 1: "OFF", 2: "Blink", 3: "Reserved"}},
            {"CANID": 0x310, "name": "BCM_TurnIndicatorSts",
             "values": {0: "Off", 1: "LeOn", 2: "RiOn", 3: "LeAndRiOn"}},
        ],
        "Sub-item-response": {"子项编码":2,"子项参数":0},
    },
    "鸣笛": {
        "control": {"opType": "HONK", "ops": {"开启": "OPEN"}},
        "signals": [
            {"CANID": 0x1A7, "name": "TBOX_HornCmd", "values": {0: "NoRequest", 1: "OFF", 2: "ON", 3: "Reserved"}},
        ],
        "Sub-item-response": {"子项编码":3,"子项参数":0},
    },
    "寻车": {
        "control": {"opType": "FIND_VEHICLE", "ops": {"开启": "OPEN"}},
        "signals": [
            {"CANID": 0x1A7, "name": "TBOX_TurnIndcrCtrlCmd",
             "values": {0: "NoRequest", 1: "OFF", 2: "Blink", 3: "Reserved"}},
            {"CANID": 0x1A7, "name": "TBOX_HornCmd", "values": {0: "NoRequest", 1: "OFF", 2: "ON", 3: "Reserved"}},
            {"CANID": 0x310, "name": "BCM_TurnIndicatorSts",
             "values": {0: "Off", 1: "LeOn", 2: "RiOn", 3: "LeAndRiOn"}},
        ],
        "Sub-item-response": {"子项编码": 7, "子项参数": 0},
    },
    "远程启动": {
        "control": {"opType": "ENGINE", "ops": {"启动": "OPEN", "关闭": "CLOSE"}},
        "signals": [
            {"CANID": 0x1A1, "name": "TBOX_EngCtrlCmd",
             "values": {0: "NoRequest", 1: "Start", 2: "IGOFFRequest", 3: "IGONRequest"}},
            {"CANID": 0x1A5, "name": "PEPS_RemoteStartFeedBackCode",
             "values": {
        0x00:"Inactive", 0x01:"RemoteStart Be Close On IVI", 0x02:"Remote start more than 2 times",
        0x03:"Communication error", 0x05:"Command validity via CAN is Invalid",
        0x06:"Start refuse by unknown reason", 0x07:"Reserved", 0x13:"RS_Running",
        0x21:"RS_Stop", 0x25:"Any door Opened_5door", 0x26:"Any door not Locked",
        0x27:"Brake_Clutch is pressed", 0x51:"TBOX auth Faults after 3 tries",
        0x52:"ESCL Faults to Unlock after 3 tries", 0x53:"Engine response timeout",
        0x55:"Unexpected internal event", 0x56:"CID found in cabin",
        0x58:"EMS_VCU auth Faulture", 0xC5:"No Valid fob found",
        0xC9:"power on refuse by power stage not OFF", 0xCB:"Start refuse by vehicle speed",
        0xCD:"Start refuse by gear not P_N", 0xCE:"Engine Stop by Anti_theft Warning"
    }},
        ],
        "Sub-item-response": {"子项编码": 20, "子项参数": 0},
    },
    "一键制冷": {
        "control": {"opType": "OT_REFRIGERATION", "ops": {"开启": "OPEN", "关闭": "CLOSE"}},
        "signals": [
            {"CANID": 0x1A2, "name": "TBOX_AcWorkCmd",
             "values": {0: "NoRequest", 1: "OFF", 2: "Heating", 3: "Cooling", 4: "Auto", 5: "Manual（R）",
                        0x6: "Reserved", 0x7: "Reserved"}},
            {"CANID": 0x540, "name": "ACM_RemoteControlMode",
             "values": {0: "OFF", 1: "Heating", 2: "Cooling", 3: "Other modes"}},
        ],
        "Sub-item-response": {"子项编码": 14, "子项参数": 4},
    },
    "一键加热": {
        "control": {"opType": "OT_HEATING", "ops": {"开启": "OPEN", "关闭": "CLOSE"}},
        "signals": [
            {"CANID": 0x1A2, "name": "TBOX_AcWorkCmd",
             "values": {0: "NoRequest", 1: "OFF", 2: "Heating", 3: "Cooling", 4: "Auto", 5: "Manual（R）",
                        0x6: "Reserved", 0x7: "Reserved"}},
            {"CANID": 0x540, "name": "ACM_RemoteControlMode",
             "values": {0: "OFF", 1: "Heating", 2: "Cooling", 3: "Other modes"}},
        ],
        "Sub-item-response": {"子项编码": 13, "子项参数": 4},
    },
    "空调": {
        "control": {"opType": "AC_SWITCH", "ops": {"开启": "OPEN", "关闭": "CLOSE"}},
        "signals": [
            {"CANID": 0x1A2, "name": "TBOX_AcWorkCmd",
             "values": {0: "NoRequest", 1: "OFF", 2: "Heating", 3: "Cooling", 4: "Auto", 5: "Manual（R）",
                        0x6: "Reserved", 0x7: "Reserved"}},
            {"CANID": 0x540, "name": "ACM_RemoteControlMode",
             "values": {0: "OFF", 1: "Heating", 2: "Cooling", 3: "Other modes"}},
        ],
        "Sub-item-response": {"子项编码": 61, "子项参数": 4},
    },
    "锁车管理": {
        "control": {"opType": "LOCK_MANAGER", "ops": {"开启": "CLOSE", "关闭": "OPEN"}},
        "signals": [
            {"CANID": 0x602, "name": "TBOX_LockManagement",
             "values": {0: "Normal", 1: "Lock", 2: "Unlock", 3: "Invalid"}},
            {"CANID": 0x639, "name": "VCU_LockManagFeedback",
             "values": {0: "unlock", 1: "lock"}},
        ],
        "Sub-item-response": {"子项编码": 43, "子项参数": 0},
    },
    "车辆限扭": {
        "control": {"opType": "TORQUE_LIMIT",
                    "ops": {"Tq1": "T8", "Tq2": "T7", "Tq3": "T6", "Tq4": "T5", "Tq5": "T9", "取消": "T0"}},
        "signals": [
            {"CANID": 0x602, "name": "TBOX_VehicleMultiTqLmt",
             "values": {0: "NoRequest", 1: "Unlimited", 2: "RestrictionToTq1(90%)", 3: "RestrictionToTq2(80%)",
                        4: "RestrictionToTq3(70%)", 5: "RestrictionToTq4(60%)", 6: "invalid"}},
            {"CANID": 0x639, "name": "VCU_MultiPowerFeedback",
             "values": {0: "Invalid", 1: "Unlimited", 2: "Next time restriction to tq1", 3: "Restriction to tq1",
                        4: "Next time restriction to tq2", 5: "Restriction to tq2", 6: "Next time restriction to tq3",
                        7:"Restriction to tq3", 8:"Next time restriction to tq4", 9:"Restriction to tq4"}},
        ],
        "Sub-item-response": {"子项编码": 40, "子项参数": 0},
    },
    "车辆限速": {
        "control": {"opType": "SPEED_LIMIT",
                    "ops": {"Spd1": "T8", "Spd2": "T7", "Spd3": "T6", "Spd4": "T4", "Spd5": "T1", "取消": "T0"}},
        "signals": [
            {"CANID": 0x602, "name": "TBOX_VehicleMultiSpdLmt",
             "values": {0: "NoRequest", 1: "Unlimited", 2: "RestrictionToSpd1(90km/h)", 3: "RestrictionToSpd2(80km/h)",
                        4: "RestrictionToSpd3(60km/h)", 5: "RestrictionToSpd4(40km/h)", 6: "RestrictionToSpd5(10km/h)",
                        7: "invalid"}},
            {"CANID": 0x639, "name": "VCU_MultiSpdLmtFeedback",
             "values": {0x0:"Invalid", 0x1:"Unlimited", 0x2:"Next time restriction to spd1", 0x3:"Restriction to spd1", 0x4:"Next time restriction to spd2"
                        , 0x5:"Restriction to spd2", 0x6:"Next time restriction to spd3", 0x7:"Restriction to spd3", 0x8:"Next time restriction to spd4"
                        , 0x9:"Restriction to spd4", 0xA:"Next time restriction to spd5", 0xB:"Restriction to spd5"}},
        ],
        "Sub-item-response": {"子项编码": 41, "子项参数": 0},
    },
    # ── 新增远控：直接往下加 ──
}


REMOTE_CONTROL_CONFIG = {
    "url": r"https://jmcoperuat.jmc.com.cn/port/control",
    "payload": {"vin": VIN, "opType": "LOCK", "op": "CLOSE", "extendAttribute": {"$": "$"}, "caller": "hirainuat"},
}

# 远控结果查询配置
API_QUERY_CONFIG_TSP = {
    "url": r"https://jmcoperuat.jmc.com.cn/port/getData",
    "payload": {'applicationId': 4, 'endDate': None, 'messageType': 2, 'source': '', 'startDate': None, 'vin': VIN},
}

API_QUERY_CONFIG_TBOX = {
    "url": r"https://jmcoperuat.jmc.com.cn/port/getData",
    "payload": {'applicationId': 4, 'endDate': None, 'messageType': 1, 'source': '', 'startDate': None, 'vin': VIN},
}

# VBA 录制配置
VBA_CONFIG = {
    "project": "ELD",
    "network": "CAN1",
    "database": "TCANFD",
}

CAPTURE_PATH = r"D:\实车半自动化\Test_AUTO\TEST\capture.mf4"

BATCH_REPORT_DIR = r"D:/实车半自动化/Test_AUTO/Remote_Control"
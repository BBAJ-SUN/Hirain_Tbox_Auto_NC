#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""总线数据对照: 对应表加载 + Feed 值匹配 + VBA 总线值获取。

数据流:
    对应表(835g) -> 每行: wksSignal+value(匹配Feed) / TBOX_DBC+CANID(匹配总线)
    后台上报值 = Feed 解析结果
    总线值     = VBA COM 接口 getSignalPhyVal

用法:
    mapping = load_mapping("D:/.../Feed数据对应表.xlsx")
    val = get_feed_value(records, "TIRE_PRESSURE", "REAR_LEFT")
    bus = BusClient("VBACOM", "CX835KSA_ENV_test")
    bus.connect()
    v = bus.get_signal("0x361", "TPMS_LR_Pressure")
"""
import re

DEFAULT_MAPPING = r"D:\实车半自动化\Feed解析\Feed数据对应表.xlsx"
DEFAULT_COM_NAME = "VBACOM"
DEFAULT_PROJECT_NAME = "CX835KSA_ENV_test"
SHEET_NAME = "835g"
CAN_CHANNEL = "CAN1"


def _norm(s):
    """清洗字符串: 去空白/制表符/换行, 用于容错匹配。"""
    if s is None:
        return ""
    return str(s).replace("\t", "").replace("\n", "").replace(" ", "").strip().lower()


def load_mapping(path):
    """读取对应表, 返回行列表。

    每行: {wksSignal, value, tbox_dbc, canid, remark, units}
      - wksSignal 为合并单元格, 读取后前向填充
      - value 为 '/' 表示无子信号
      - canid 保留原样(如 '0x361'), 供 VBA 调用时 int(canid,16)
    """
    import pandas as pd
    df = pd.read_excel(path, sheet_name=SHEET_NAME)
    df["wksSignal"] = df["wksSignal"].ffill()
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "wksSignal": _clean_str(r.get("wksSignal")),
            "value": _clean_str(r.get("value")),
            "tbox_dbc": _clean_str(r.get("TBOX_DBC")),
            "canid": _clean_str(r.get("CANID")),
            "remark": _clean_str(r.get("备注")),
            "units": _clean_str(r.get("METRIC_UNITS")),
        })
    return rows


def _clean_str(v):
    if v is None or (isinstance(v, float) and v != v):  # NaN
        return ""
    s = str(v).strip()
    return "" if s.lower() == "nan" else s


def build_feed_index(records):
    """把 Feed 记录建成 信号名 -> [(tags值列表, vdisplay, group), ...] 索引。

    用于 get_feed_value 的 O(1) 查询, 避免每条记录反复拆解。
    按 group 递增(文件顺序)存储, 取最新即取最后一条。
    """
    from feed_parser import metric_items
    index = {}
    for rec in records:
        group = rec["group"]
        for signal, tags, tags_raw, value, err, m, vdisplay, vdetail in \
                metric_items(rec["obj"]):
            key = _norm(signal)
            if not key:
                continue
            tag_vals = [_norm(v) for v in tags.values()]
            index.setdefault(key, []).append(
                {"tag_vals": tag_vals, "vdisplay": vdisplay, "group": group})
    return index


def get_feed_value(feed_index, signal, value_sub):
    """在 Feed 索引中匹配信号值。

    规则:
      - 信号名 _norm 相等
      - 若 value_sub 非 '/' 且非空: 要求任一 tag 值包含 value_sub(norm 后)
      - 返回该信号最新一条(group 最大)的 vdisplay
    """
    key = _norm(signal)
    value_sub_n = _norm(value_sub)
    if key not in feed_index:
        return None
    # 取 group 最大的(最新)
    best = None
    for item in feed_index[key]:
        if value_sub_n and value_sub_n != "/":
            if not any(value_sub_n in tv for tv in item["tag_vals"]):
                continue
        if best is None or item["group"] > best["group"]:
            best = item
    if best is None:
        return None
    v = best["vdisplay"]
    # 单键 dict(如 enumValue)取内层值
    if isinstance(v, dict) and len(v) == 1:
        return next(iter(v.values()))
    return v


class BusClient:
    """VBA COM 封装: 连接工程 + 读取总线信号物理值。"""

    def __init__(self, com_name=DEFAULT_COM_NAME, project_name=DEFAULT_PROJECT_NAME):
        self.com_name = com_name
        self.project_name = project_name
        self._project = None
        self._can_bus = None
        self.error = ""  # 最近一次连接错误

    @property
    def connected(self):
        return self._can_bus is not None

    def connect(self):
        """连接 VBA 工程。失败时置 self.error, 返回 False。"""
        import win32com.client
        self.error = ""
        try:
            vba = win32com.client.Dispatch(self.com_name)
            project = vba.getProjectByname(self.project_name)
            if project is None:
                self.error = f"VBA工程不存在: {self.project_name}"
                self._project = None
                self._can_bus = None
                return False
            self._project = project
            self._can_bus = project.getCANBusModule()
            return True
        except Exception as e:
            self.error = f"VBA连接失败: {e}"
            self._project = None
            self._can_bus = None
            return False

    def get_signal(self, canid, signal):
        """读取总线信号物理值。canid 形如 '0x361'。

        返回 (成功与否, 值或错误信息)。失败不抛异常。
        """
        if not self.connected:
            return False, "VBA未连接"
        try:
            val = self._can_bus.getSignalPhyVal(
                CAN_CHANNEL, int(canid, 16), 1, signal)
            return True, val
        except Exception as e:
            return False, self._short_error(e)

    @staticmethod
    def _short_error(e):
        """把 COM 异常简化成简短提示(避免长错误文本撑爆表格列)。

        注意: 不能靠文本里是否含 "VBACOM" 判断(COM 异常都带 VBACOMAPI 来源),
        应优先识别具体错误语义。
        """
        text = str(e)
        if "not running" in text:
            return "VBA工程未运行"
        if "does not exist" in text:
            return "报文/信号不存在"
        if "not found" in text.lower():
            return "报文/信号不存在"
        if "disconnect" in text.lower():
            return "VBA连接已断开"
        if "co_createinstance" in text.lower() or "class not registered" in text.lower():
            return "VBA组件未注册"
        # 取 COM 异常的 description(第3段信息里的用户可读消息)
        try:
            args = getattr(e, "args", None)
            if args and len(args) >= 3 and isinstance(args[2], tuple) and len(args[2]) >= 2:
                msg = str(args[2][1])
                if msg:
                    return msg[:40]
        except Exception:
            pass
        first = text.splitlines()[0] if text.splitlines() else text
        return first[:40]

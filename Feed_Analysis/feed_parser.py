#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FeedOut 日志解析模块: 独立于 GUI 的可复用解析逻辑。

提供:
    - parse_log(path)      解析 FeedOut.txt, 返回记录列表
    - parse_log_range(path, minutes, max_records)  按时间窗/数量上限读取
    - cutoff_str(minutes)  N 分钟前的同格式时间字符串(过滤用)
    - extract_log_time(text)  从记录首行提取时间(兼容文件/命令行两种格式)
    - format_time(t)       格式化日志时间(T换空格, 去时区)
    - data_time(obj)       取记录的数据时间(Event timestamp / Metric startTime)
    - atype(obj)           取记录类型短名(Metric / Event)
    - metric_items(obj)    把一条记录拆成信号指标列表
    - value_display(value) 单键 dict 值的二级显示值
    - value_kv(value)      单键 dict 值的 (键名, 值)
    - record_brief(rec)    记录简要文本(用于树节点)
    - to_json(data)        dict/list 转格式化 JSON 文本
    - group_raw(rec)       整条记录的原始 JSON 文本
    - event_meta(obj)      Event 记录的 conditions / wellKnownLabel
    - configuration_items(obj)  CONFIGURATION 信号(备车数据)的结构化解析
    - indicator_items(obj) INDICATOR_LIGHT 信号(健康指示灯)的结构化解析
    - matches(rec, kw)     关键字是否匹配该记录

    metric_items 返回每项为 8 元组:
      (signal, tags, tags_raw, value, err, raw_metric, vdisplay, vdetail)
      - signal:     信号名
      - tags:       {标签名: 标签值}
      - tags_raw:   {标签名: 原始标签 dict}
      - value:      原始值(可能为 dict)
      - err:        错误名或 ""
      - raw_metric: 指标原始 dict
      - vdisplay:   二级显示值
      - vdetail:    三级展开文本


数据结构:
    记录 -> data -> signal(wksSignal/stringSignal) / tags[] / 值字段
    Event 类型: 信号在 payload.metrics[] 数组; Metric 类型: 信号就是 data 本身
"""
import json
import os
import re

# 一行 JsonDelegate 日志记录的起始
RECORD_RE = re.compile(r"JsonDelegate.*:\s*\{$")


def format_time(t):
    """格式化日志时间: 2026-08-17T13:48:34.977+08:00 -> 2026-08-17 13:48:34.977。

    T 换成空格, 去掉末尾时区偏移(+08:00)。非标准格式原样返回。
    """
    if not t:
        return ""
    # 去时区: +08:00 / +0800 / Z
    t = re.sub(r"[+-]\d{2}:?\d{2}$", "", t)
    t = t.rstrip("Z")
    # T 换空格
    return t.replace("T", " ")


def cutoff_str(minutes):
    """返回 N 分钟前的同格式时间字符串, 用于 log_time 过滤比较。

    log_time 是定长 'YYYY-MM-DD HH:MM:SS.mmm', 字符串比较 == 时间序比较。
    """
    import datetime
    t = datetime.datetime.now() - datetime.timedelta(minutes=minutes)
    return t.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def extract_log_time(text):
    """从记录文本首行提取日志时间, 兼容两种格式:
      - 文件:   2026-08-17T13:48:34.977+08:00  (无空格, 带T/时区)
      - 命令行: 2026-09-10 14:34:41.341        (日期与时分秒间有空格)

    返回 'YYYY-MM-DD HH:MM:SS.mmm' 格式, 提取不到返回 ""。
    """
    # 日期 + 时间(日期与时间间允许 T 或空格)
    m = re.match(
        r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2}(?:\.\d+)?)", text)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    # 兜底: 只有日期
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    if m:
        return m.group(1)
    # 再兜底: 第一个非空白字段
    m = re.match(r"^(\S+)", text)
    return format_time(m.group(1)) if m else ""


# 指标值字段的取值优先级
_VALUE_FIELDS = ("doubleValue", "stringValue", "int64Value", "enumValue",
                 "indicatorValue", "headingValue", "positionValue", "intValue",
                 "configurationValue")


def parse_log(path):
    """解析 FeedOut.txt, 返回记录列表。每条记录:
    {"group": 序号, "log_time": ..., "obj": dict}
    """
    records = []
    pending = []
    in_record = False
    group = 0
    seen = set()          # 已见记录的指纹(整条 JSON), 用于去重

    def flush():
        nonlocal group
        if not pending:
            return
        text = "\n".join(pending)
        pending.clear()
        log_time = extract_log_time(text)
        start = text.find("{")
        if start < 0:
            return
        json_text = text[start:]
        group += 1
        # 整条 JSON 完全一致视为重复, 只保留第一条
        if json_text in seen:
            return
        try:
            obj = json.loads(json_text)
        except json.JSONDecodeError:
            return
        seen.add(json_text)
        records.append({"group": group, "log_time": log_time,
                        "data_time": data_time(obj), "obj": obj})

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if RECORD_RE.search(line):
                flush()
                pending.append(line.rstrip("\r\n"))
                in_record = True
            elif in_record:
                pending.append(line.rstrip("\r\n"))
        flush()
    return records


def parse_log_range(path, minutes=None, max_records=None):
    """从文件读取记录, 支持时间窗过滤和数量上限。

    参数:
      - minutes:      None=全部; N=只保留**数据产生时间**在最近 N 分钟内的记录
      - max_records:  超过则丢弃最旧的(保留最新 N 条)
    """
    all_records = parse_log(path)
    if minutes:
        cutoff = cutoff_str(minutes)
        # 按数据产生时间过滤(与时间列显示一致); 无数据时间的记录用打印时间兜底
        all_records = [r for r in all_records
                       if (r.get("data_time") or r.get("log_time", "")) >= cutoff]
    if max_records and len(all_records) > max_records:
        # 保留最新 max_records 条(group 最大 / 时间最新)
        all_records = all_records[-max_records:]
    return all_records


class FileTailParser:
    """增量解析 FeedOut.txt: 首次全量, 之后只读新增行。

    用法:
        parser = FileTailParser(path)
        records1 = parser.read_new()   # 首次: 全量
        records2 = parser.read_new()   # 之后: 只返回新增的记录
    文件被覆盖(变小)时自动全量重来。
    """

    def __init__(self, path):
        self.path = path
        self.offset = 0        # 上次读到的字节位置
        self.group = 0         # 全局记录序号(追加时递增)
        self.pending = []      # 未完成记录的缓冲(处理跨行记录)
        self.in_record = False
        self.seen = set()      # 已见记录指纹(整条 JSON), 跨批次去重

    def _parse_lines(self, lines, flush_pending=False):
        """把新增行解析成记录, 返回记录列表。
        flush_pending=True 时, 读完所有行后强制 flush 残留记录(用于读到 EOF 时)。"""
        records = []
        pending = self.pending
        in_record = self.in_record

        def flush():
            nonlocal in_record
            if not pending:
                return
            text = "\n".join(pending)
            pending.clear()
            in_record = False
            log_time = extract_log_time(text)
            start = text.find("{")
            if start < 0:
                return
            json_text = text[start:]
            self.group += 1
            # 整条 JSON 完全一致视为重复(跨批次也去重), 只保留第一条
            if json_text in self.seen:
                return
            try:
                obj = json.loads(json_text)
            except json.JSONDecodeError:
                return
            self.seen.add(json_text)
            records.append({"group": self.group, "log_time": log_time,
                            "data_time": data_time(obj), "obj": obj})

        for line in lines:
            if RECORD_RE.search(line):
                flush()
                pending.append(line.rstrip("\r\n"))
                in_record = True
            elif in_record:
                pending.append(line.rstrip("\r\n"))

        if flush_pending:
            flush()

        # 保留未完成记录(等下次有新行再补全), 已完成的返回
        self.pending = pending
        self.in_record = in_record
        return records

    def read_new(self):
        """读取新增记录。文件变小(被覆盖)时全量重来。"""
        try:
            size = os.path.getsize(self.path)
        except OSError:
            return []
        # 文件被覆盖重写(变小): 重置状态全量重来
        if size < self.offset:
            self.offset = 0
            self.group = 0
            self.pending = []
            self.in_record = False
        if size == self.offset:
            return []  # 无新增
        with open(self.path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(self.offset)
            new_lines = f.readlines()
            self.offset = f.tell()
        records = self._parse_lines(new_lines)
        # 已读到文件末尾(offset==size): flush 残留记录
        # (若其实未写完则解析失败丢弃, 不会重复)
        if self.offset == size and self.pending:
            records.extend(self._parse_lines([], flush_pending=True))
        return records


def data_time(obj):
    """取记录的**数据产生时间**(优先 Event 的 timestamp, 否则 Metric 的 startTime)。

    数据时间通常是 UTC(带 Z), 转成本地时间后返回易读格式
    'YYYY-MM-DD HH:MM:SS.mmm'; 解析失败时退回原样格式化。
    """
    data = obj.get("data") or {}
    t = data.get("timestamp") or data.get("startTime") or ""
    if not t:
        return ""
    return to_local_time(t)


def to_local_time(t):
    """把带时区的 ISO 时间(如 2026-09-10T01:25:37Z) 转成本地时间字符串。

    转不了(格式异常)时退回 format_time 的结果。
    """
    import datetime
    s = t.strip()
    try:
        # 处理常见的 ISO 变体: ...Z(UTC) / ...+08:00 / 无时区
        iso = s
        if iso.endswith("Z"):
            iso = iso[:-1] + "+00:00"
        # 截掉过长的纳秒(>6位小数), Python 只支持微秒
        m = re.match(r"^(.*\.\d{6})\d*(.*)$", iso)
        if m:
            iso = m.group(1) + m.group(2)
        dt = datetime.datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            # 无时区信息: 视为 UTC
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        local = dt.astimezone()  # 转本地时区
        return local.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    except (ValueError, AttributeError):
        return format_time(t)


def atype(obj):
    """取记录类型短名(如 Metric / Event)。"""
    data = obj.get("data") or {}
    return (data.get("@type") or "").split(".")[-1]


def short_signal(name):
    """信号名的简化显示形式(仅用于界面显示, 匹配/取值仍用原名)。

    形如 aui:signal:<UUID>:custom:jmc-idps-log -> jmc-idps-log
    (UUID 是厂商唯一标识, 对阅读无意义; 保留末段可读名)
    不带冒号的普通名(如 DOOR_STATUS)原样返回。
    """
    if name is None or name == "":
        return ""
    # 数据中偶见非字符串信号名(如 3008.0), 显示层统一转字符串
    if not isinstance(name, str):
        return str(name)
    if ":" not in name:
        return name
    tail = name.rsplit(":", 1)[-1]
    return tail or name


def record_signals(obj):
    """记录包含的所有信号名(Metric 的信号 + Event conditions 的 requiredMetrics)。

    供"信号剔除"用: 只要任一信号命中剔除词, 整条记录不展示。
    """
    sigs = [it[0] for it in metric_items(obj) if isinstance(it[0], str)]
    sigs += [m["signal"] for c in event_conditions(obj)
             for m in c["metrics"] if isinstance(m["signal"], str)]
    return sigs


def parse_filters(text):
    """把剔除输入框文本解析成关键词列表(逗号/分号/换行分隔, 小写)。

    支持一次填多个, 如 "jmc-idps-log, TIRE_PRESSURE"。
    """
    if not text:
        return []
    raw = text.replace(";", ",").replace("，", ",").replace("\n", ",")
    return [p.strip().lower() for p in raw.split(",") if p.strip()]


def is_filtered(obj, filters):
    """记录是否应被剔除(任一信号名包含任一剔除词 -> True)。"""
    if not filters:
        return False
    for sig in record_signals(obj):
        low = sig.lower()
        if any(f in low for f in filters):
            return True
    return False


def _val_of(metric):
    """从指标 dict 取第一个非空值字段, 返回 (value, error)。"""
    err = (metric.get("errorValue") or {}).get("wkErrorName", "")
    value = None
    for f in _VALUE_FIELDS:
        if f in metric and metric[f] is not None:
            value = metric[f]
            break
    return value, err


def _tag_value_of(v):
    """从 tags[].value dict 取第一个非空字段值。"""
    if isinstance(v, dict):
        for vv in v.values():
            if vv is not None and vv != "":
                return vv
    return None


def metric_items(obj):
    """把一条记录拆成指标列表, 兼容 Metric 和 Event。

    返回 [(signal, tags, value, err, raw_metric, vdisplay, vdetail), ...]
      - signal:     信号名(wksSignal / stringSignal)
      - tags:       {标签名: 标签值}
      - value:      原始值(可能是 dict)
      - err:        错误名或 ""
      - raw_metric: 该指标的原始 dict(用于展示 JSON)
      - vdisplay:   二级显示值(单键 dict 取内层值)
      - vdetail:    三级展开文本(键名: 值)
    """
    data = obj.get("data") or {}
    payload = data.get("payload") or {}
    metrics = payload.get("metrics") if isinstance(payload, dict) else None
    if isinstance(metrics, list) and metrics:
        metrics = [m for m in metrics if isinstance(m, dict)]
    elif isinstance(data, dict) and data.get("signal"):
        metrics = [data]
    else:
        metrics = []

    items = []
    for m in metrics:
        sig = m.get("signal") or {}
        signal = sig.get("wksSignal") or sig.get("stringSignal") or ""
        tags = {}
        tags_raw = {}  # 标签名 -> 原始标签 dict(用于详情展示原始 JSON)
        for t in m.get("tags") or []:
            name = t.get("name") or {}
            tag_name = name.get("wktName") or name.get("stringName") or ""
            if tag_name:
                tags[tag_name] = _tag_value_of(t.get("value"))
                tags_raw[tag_name] = t
        value, err = _val_of(m)
        vdisplay, vdetail = value_display(value)
        # INDICATOR_LIGHT: 二级显示 additionalInfo.value(如 "600E27")
        if signal == "INDICATOR_LIGHT" and isinstance(value, dict):
            ai = value.get("additionalInfo") or {}
            if "value" in ai:
                vdisplay = ai.get("value")
                vdetail = f"additionalInfo.value: {ai.get('value')}"
        # POSITION: 二级显示 经纬度,altitude; 供树展开/详情用
        if signal == "POSITION" and isinstance(value, dict):
            lat, lon, alt = _position_parts(value)
            if lat is not None:
                vdisplay = f"{lat}, {lon}"
                vdetail = f"latitude: {lat}, longitude: {lon}, altitude: {alt}"
        items.append((signal, tags, tags_raw, value, err, m, vdisplay, vdetail))
    return items


def _position_parts(value):
    """从 positionValue 提取 (latitude, longitude, altitude)。

    结构: value.location[0].threeDPoint.{latitude,longitude,altitude}
    取不到返回 (None, None, None)。
    """
    try:
        loc = value.get("location") or []
        pt = loc[0].get("threeDPoint") or {}
        return (pt.get("latitude"), pt.get("longitude"), pt.get("altitude"))
    except (IndexError, AttributeError, KeyError):
        return None, None, None


def value_display(value):
    """单键 dict 值(如 enumValue 的 {"compassDirectionStatus":"NORTH"})
    返回 (内层值, "键名: 值"); 其它类型返回 (value, value)。
    """
    if isinstance(value, dict) and len(value) == 1:
        k, vv = next(iter(value.items()))
        return vv, f"{k}: {vv}"
    return value, value


def value_kv(value):
    """单键 dict 值返回 (键名, 值), 否则 (None, None)。"""
    if isinstance(value, dict) and len(value) == 1:
        return next(iter(value.items()))
    return None, None


def record_brief(rec):
    """记录节点的简要文本。Event 记录附加 wellKnownLabel。"""
    brief = f"[{rec['group']}] {atype(rec['obj'])} | {rec['log_time']}"
    _, label = event_meta(rec["obj"])
    if label:
        brief += f" | {label}"
    return brief


def oem_data_items(obj):
    """解析 Event 记录的 oemData.dataMap, 返回 [(字段名, 值), ...]。

    dataMap 结构: {字段名: {xxxValue: 值}}, 值取第一个非空 xxxValue。
    """
    data = obj.get("data") or {}
    oem = data.get("oemData") or {}
    data_map = oem.get("dataMap") or {}
    items = []
    for key, v in data_map.items():
        if not isinstance(v, dict):
            items.append((key, v))
            continue
        # 取第一个非空的值字段
        val = None
        for vv in v.values():
            if vv is not None and vv != "":
                val = vv
                break
        items.append((key, val))
    return items


def state_transition_info(obj):
    """StateTransition 事件的结构化信息。

    兼容两套字段(实际数据里都有):
      1) 扁平 string 前缀: stringFsmName / stringFromState / stringToState / stringTrigger
      2) 嵌套 commandStateTransition: {fsm, fromState, toState}
    返回 dict:
      - state:  id 最后一段(如 success)
      - message: payload.message
      - fsm / from_state / to_state: 状态流转
      - trigger: 触发条件(stringTrigger)
      - command_type: metadataTags.commandType
      - source:  data.source
      - id:    完整 id
    非 StateTransition 类型返回 None。
    """
    data = obj.get("data") or {}
    payload = data.get("payload") or {}
    if not (payload.get("@type") or "").endswith("StateTransition"):
        return None
    eid = data.get("id") or ""
    state = re.split(r"[:/]", eid)[-1] if eid else ""
    cst = payload.get("commandStateTransition") or {}
    return {
        "state": state,
        "message": payload.get("message") or "",
        # 优先扁平 string 字段, 退回嵌套 commandStateTransition
        "fsm": payload.get("stringFsmName") or cst.get("fsm") or "",
        "from_state": payload.get("stringFromState") or cst.get("fromState") or "",
        "to_state": payload.get("stringToState") or cst.get("toState") or "",
        "trigger": payload.get("stringTrigger") or "",
        "command_type": (data.get("metadataTags") or {}).get("commandType") or "",
        "source": data.get("source") or "",
        "id": eid,
    }


def _contains_key(obj, target):
    """递归判断 dict 中是否含指定键名。"""
    if isinstance(obj, dict):
        if target in obj:
            return True
        return any(_contains_key(v, target) for v in obj.values())
    if isinstance(obj, list):
        return any(_contains_key(v, target) for v in obj)
    return False


def record_title(rec):
    """一级节点标题: Metric | 信号名 或 Event | 简要名。

    Event 标题规则:
      - StateTransition 类(id 含 '/state_transition/'): 取"动作/状态"两段,
        如 aui:event/au/state_transition/actuation_unlock/request_queued
        -> actuation_unlock/request_queued
      - 其它带 ':' 的 id: 取最后一个 ':' 后的段(如 ignition_event)
      - 无 id: reportedProperties / @type 末段兜底
    """
    t = atype(rec["obj"])  # Metric / Event
    if t == "Event":
        data = rec["obj"].get("data") or {}
        eid = data.get("id") or ""
        # StateTransition 类: 去固定前缀, 取"动作/状态"
        if "/state_transition/" in eid:
            tail = eid.split("/state_transition/", 1)[1]
            parts = [p for p in tail.split("/") if p]
            state = "/".join(parts[-2:]) if parts else ""
            return f"Event | {state}" if state else "Event"
        if ":" in eid:
            # 取最后一个 ':' 后面的字符串
            state = eid.rsplit(":", 1)[-1]
            return f"Event | {state}" if state else "Event"
        # 无 id(或 id 无冒号): 兜底
        payload = data.get("payload") or {}
        # 若数据中含 reportedProperties(上报配置事件) -> 用该名字
        if _contains_key(payload, "reportedProperties"):
            return "Event | reportedProperties"
        # 否则截取 @type 末段(如 AssetChangeEvent)
        atype_str = payload.get("@type") or ""
        type_name = atype_str.rsplit(".", 1)[-1] if atype_str else ""
        return f"Event | {type_name}" if type_name else "Event"
    # Metric: 取第一个信号名(长名简化, 只用于显示)
    items = metric_items(rec["obj"])
    signal = short_signal(items[0][0]) if items else ""
    return f"Metric | {signal}" if signal else "Metric"


def to_json(data):
    """把任意 dict/list 转成格式化 JSON 文本, 失败返回 str(data)。"""
    try:
        return json.dumps(data, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return str(data)


def group_raw(rec):
    """整条记录的原始 JSON 文本。"""
    return to_json(rec["obj"])


def event_meta(obj):
    """Event 记录的元信息: (conditions, wellKnownLabel)。

    - conditions:   ["VEHICLE_STATUS_UPDATED", ...]
    - wellKnownLabel: "XEV_BATTERY_CHARGE_EVENT" 或 ""
    Metric 类型返回 ([], "")。
    """
    data = obj.get("data") or {}
    payload = data.get("payload") or {}
    conditions = []
    for c in payload.get("conditions") or []:
        if isinstance(c, dict):
            cond = c.get("condition")
            if cond:
                conditions.append(cond)
        elif c:
            conditions.append(c)
    label = payload.get("wellKnownLabel") or ""
    return conditions, label


def event_conditions(obj):
    """Event 记录 conditions 的结构化详情, 供树形展开。

    每个 condition 解析为:
      {"condition": "REMOTE_START_BEGAN",
       "metrics": [{"signal": "REMOTE_START_DEVICE_STATUS",
                    "value": "RUNNING", "raw": {...}}, ...]}
    - metrics 来自 condition.requiredMetrics 数组, 每个含 wksSignal + 值字段
    - 值字段取第一个非空(如 enumValue 的单键 dict 取内层值)
    - 无 requiredMetrics 的 condition, metrics 为空列表
    """
    data = obj.get("data") or {}
    payload = data.get("payload") or {}
    result = []
    for c in payload.get("conditions") or []:
        if not isinstance(c, dict):
            result.append({"condition": str(c), "metrics": []})
            continue
        # condition 偶见数字类型(如 163.0), 统一转字符串供显示/拼接
        cond = str(c.get("condition") or c.get("stringLabel") or "")
        metrics = []
        for rm in c.get("requiredMetrics") or []:
            if not isinstance(rm, dict):
                continue
            sig = rm.get("signal") or {}
            signal = sig.get("wksSignal") or sig.get("stringSignal") or ""
            value = None
            for f in _VALUE_FIELDS:
                if f in rm and rm[f] is not None:
                    value = rm[f]
                    break
            # 单键 dict(如 enumValue)取内层值
            if isinstance(value, dict) and len(value) == 1:
                value = next(iter(value.values()))
            metrics.append({"signal": signal, "value": value, "raw": rm})
        result.append({"condition": cond, "metrics": metrics})
    return result


def _string_value_of(v):
    """取 {stringValue: ...} 里的值。"""
    if isinstance(v, dict):
        return v.get("stringValue")
    return v


def configuration_items(obj):
    """解析 CONFIGURATION 信号(备车数据), 返回结构化描述。

    返回 (config_label, feature_status, blocks):
      - config_label:   "XEV_DEPARTURE_SCHEDULES_SETTING"
      - feature_status: "ON"/"OFF" (备车开关)
      - blocks:         [ {scheduleId, scheduleStatus, scheduleType, dayOfWeek,
                           hours, chrg_go_t_prcond_d_stat, raw}, ... ] 每块一个备车时间
    """
    data = obj.get("data") or {}
    payload = data.get("payload") or {}
    metrics = payload.get("metrics") if isinstance(payload, dict) else None
    if isinstance(metrics, list):
        metrics = [m for m in metrics if isinstance(m, dict)]
    elif isinstance(data, dict) and data.get("signal"):
        metrics = [data]
    else:
        metrics = []

    for m in metrics:
        sig = m.get("signal") or {}
        if sig.get("wksSignal") != "CONFIGURATION":
            continue
        cv = m.get("configurationValue") or {}
        config_label = cv.get("configuration") or ""
        xev = cv.get("xevDepartureSchedules") or {}
        feature_status = xev.get("departureScheduleFeatureStatus") or ""
        blocks = []
        for loc in xev.get("departureLocations") or []:
            for sch in (loc.get("departureSchedules") or []):
                if not isinstance(sch, dict):
                    continue
                sched = sch.get("schedule") or {}
                weekly = sched.get("weeklySchedule") or {}
                tod = weekly.get("timeOfDay") or {}
                oem = sch.get("oemData") or {}
                data_map = oem.get("dataMap") or {}
                chrg = _string_value_of(data_map.get("chrg_go_t_prcond_d_stat"))
                blocks.append({
                    "scheduleId": sch.get("scheduleId"),
                    "scheduleStatus": sch.get("scheduleStatus"),
                    "scheduleType": sched.get("scheduleType"),
                    "dayOfWeek": weekly.get("dayOfWeek"),
                    "hours": tod.get("hours"),
                    "timeZone": sched.get("timeZone"),
                    "scheduleExecutor": sched.get("scheduleExecutor"),
                    "chrg_go_t_prcond_d_stat": chrg,
                    "raw": sch,
                })
        return config_label, feature_status, blocks
    return "", "", []


def indicator_items(obj):
    """解析 INDICATOR_LIGHT 信号(车辆健康指示灯)。

    返回 (wellKnownIndicator, indicatorState, additionalInfo):
      - wellKnownIndicator: 指示灯名(如 ADAPTIVE_CRUISE_CONTROL)
      - indicatorState:     状态(ON/OFF)
      - additionalInfo:     附加信息 dict(如 {"@type":..., "value":"600E14"})
    非 INDICATOR_LIGHT 返回 ("", "", {})。
    """
    data = obj.get("data") or {}
    payload = data.get("payload") or {}
    metrics = payload.get("metrics") if isinstance(payload, dict) else None
    if isinstance(metrics, list):
        metrics = [m for m in metrics if isinstance(m, dict)]
    elif isinstance(data, dict) and data.get("signal"):
        metrics = [data]
    else:
        metrics = []

    for m in metrics:
        sig = m.get("signal") or {}
        if sig.get("wksSignal") != "INDICATOR_LIGHT":
            continue
        iv = m.get("indicatorValue") or {}
        return (iv.get("wellKnownIndicator") or "",
                iv.get("indicatorState") or "",
                iv.get("additionalInfo") or {})
    return "", "", {}


def matches(rec, kw):
    """关键字 kw(小写) 是否匹配该记录的任一信号/标签/值/事件元信息。"""
    if not kw:
        return True
    obj = rec["obj"]
    for signal, tags, tags_raw, value, err, m, vdisplay, vdetail in metric_items(obj):
        hay = [signal] + list(tags.keys()) + [str(v) for v in tags.values()]
        hay += [str(vdisplay), str(err)]
        if any(kw in str(x).lower() for x in hay):
            return True
    # 事件元信息
    conditions, label = event_meta(obj)
    if label and kw in label.lower():
        return True
    if any(kw in c.lower() for c in conditions):
        return True
    return False

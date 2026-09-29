#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Feed GUI 主程序: 两个 Tab。
    Tab1「Feed 数据监控」: 树形查看 JsonDelegate 信号结构(搜索/排序/tooltip)。
    Tab2「总线数据对照」: 对应表 + Feed值 + VBA总线值 并排对照。

用法:
    python feed_gui.py [FeedOut.txt]
    默认加载 D:/FeedConsumer/FeedOut.txt
"""
import argparse
import json
import os
import re
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from feed_parser import (parse_log, parse_log_range, cutoff_str,
                         data_time, atype, metric_items,
                         value_kv, record_brief, record_title,
                         to_json, group_raw, event_meta, event_conditions,
                         configuration_items, indicator_items, _position_parts,
                         state_transition_info, oem_data_items,
                         short_signal, parse_filters, is_filtered,
                         FileTailParser)
from bus_compare import (load_mapping, build_feed_index, get_feed_value,
                         BusClient, DEFAULT_MAPPING, DEFAULT_COM_NAME,
                         DEFAULT_PROJECT_NAME)

DEFAULT_FILE = r"D:\FeedConsumer\FeedOut.txt"

# 配置文件位置: 打包成 exe 后存到 exe 同目录(临时解压目录会被删), 源码运行存脚本同目录
if getattr(sys, "frozen", False):
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(_BASE_DIR, "feed_gui_config.json")

# FEED-SNAPSHOT 数据源默认值(jar 自动取程序同目录下的 .jar)
DEFAULT_FESN = "1XA0001G"
CMD_OUTPUT_PATH = os.path.join(_BASE_DIR, "feed-cmd-output.txt")
# 本次启动的 java 进程 PID: 供下次启动/退出时清理异常遗留的 JVM
PID_PATH = os.path.join(_BASE_DIR, "feed-cmd.pid")
# feed-consumer 内嵌 Tomcat 的监听端口(jar 默认值), 启动前预检是否被占用
FEED_PORT = 8082
# 隐藏子进程控制台窗口(Windows)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

# 数据源选项名(下拉框显示)
SRC_IDEA = "FEED-IDEA"        # 从文件读取
SRC_SNAPSHOT = "FEED-SNAPSHOT"  # 命令行 java 进程
# 兼容旧配置里存的名字
_OLD_SRC_NAMES = {"文件": SRC_IDEA, "命令行": SRC_SNAPSHOT}


def _norm_source(name):
    """把配置里可能存的旧数据源名映射为新名。"""
    return _OLD_SRC_NAMES.get(name, name)


def find_local_jar():
    """在程序同目录(脚本/exe 所在目录)查找 .jar 文件。

    返回找到的 jar 完整路径; 找不到返回 None; 多个时返回第一个(按名称排序)。
    """
    try:
        jars = sorted(f for f in os.listdir(_BASE_DIR)
                      if f.lower().endswith(".jar"))
    except OSError:
        return None
    return os.path.join(_BASE_DIR, jars[0]) if jars else None


def load_config():
    """读取配置文件(路径/VBA工程名等), 失败返回 {}。"""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    """保存配置到文件, 失败静默(不影响使用)。"""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _file_size(path):
    """返回文件字节数, 读取失败返回 0。"""
    try:
        return os.path.getsize(path)
    except (OSError, TypeError, ValueError):
        return 0


def _pid_alive(pid):
    """判断 PID 对应进程是否仍存在(用 tasklist 过滤, 跨平台时恒为 False)。"""
    if os.name != "nt":
        return False
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            stderr=subprocess.DEVNULL, creationflags=_NO_WINDOW)
    except (OSError, subprocess.CalledProcessError):
        return False
    return str(pid) in out.decode("utf-8", errors="replace")


def _kill_tree(pid):
    """强杀进程树(含 java launcher 甩出去的 JVM 子进程)。

    Windows 上 Popen.terminate() 只杀直接子进程, java 真正的 JVM 可能
    是另一个进程, 会导致 JVM 残留继续占用 8082 端口。
    """
    if os.name != "nt":
        return
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=_NO_WINDOW)
    except OSError:
        pass


def read_saved_pid():
    """读取上次启动记录下来的 java PID; 无记录或已失效返回 None。"""
    try:
        with open(PID_PATH, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        return None
    return pid if _pid_alive(pid) else None


def clean_stale_feed_proc():
    """清理上次异常退出(GUI 被强杀/崩溃)遗留的 java 进程。

    只杀 PID 文件里记录过的进程, 不碰其它 java(如 IDEA 或手动启动的实例)。
    返回 True 表示清理过。
    """
    pid = read_saved_pid()
    if pid is None:
        clear_saved_pid()
        return False
    _kill_tree(pid)
    clear_saved_pid()
    return True


def save_pid(pid):
    """记录本次启动的 java PID, 供下次异常退出后清理。"""
    try:
        with open(PID_PATH, "w", encoding="utf-8") as f:
            f.write(str(pid))
    except OSError:
        pass


def clear_saved_pid():
    """删除 PID 记录文件。"""
    try:
        os.remove(PID_PATH)
    except OSError:
        pass


def port_in_use(port):
    """检查端口是否已被占用(有 LISTENING)。用于启动前预检。"""
    if os.name != "nt":
        return False
    try:
        out = subprocess.check_output(
            ["netstat", "-ano", "-p", "TCP"],
            stderr=subprocess.DEVNULL, creationflags=_NO_WINDOW)
    except (OSError, subprocess.CalledProcessError):
        return False
    text = out.decode("utf-8", errors="replace")
    return re.search(rf":{port}\s+\S+\s+LISTENING", text) is not None


class FeedProcess:
    """启动 java -jar 子进程, 将其 stdout 逐行写入文件。

    输出落盘后, 现有文件读取/解析/自动刷新机制可直接复用。
    """

    def __init__(self):
        self.proc = None
        self._thread = None
        self.out_path = None
        self.error = ""
        self.port_conflict = False  # 启动时 8082 已被其它进程占用
        self.port_error = False     # 输出中出现端口占用报错

    @property
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self, jar, fesn, out_path):
        """启动进程。返回 (成功与否, 错误信息)。"""
        self.error = ""
        self.port_error = False
        if not os.path.exists(jar):
            self.error = f"jar 不存在: {jar}"
            return False, self.error
        # 先清掉上次异常退出遗留的 JVM(只杀本程序记录过的 PID)
        clean_stale_feed_proc()
        # 该端口若已被其它进程占用(手动启动的实例/IDEA), java 启动后会 bind 失败
        self.port_conflict = port_in_use(FEED_PORT)
        # 清空输出文件
        try:
            with open(out_path, "w", encoding="utf-8"):
                pass
        except OSError as e:
            self.error = f"无法创建输出文件: {e}"
            return False, self.error
        cmd = ["java", "-jar", jar, f"--tmc.feed-consumer.fesn={fesn}"]
        try:
            # Windows 下隐藏子进程控制台窗口
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                cwd=os.path.dirname(jar) or None,
                creationflags=_NO_WINDOW)
        except Exception as e:
            self.error = f"启动失败: {e}"
            return False, self.error
        self.out_path = out_path
        # 记录 PID: 下次启动/退出时可清理本次异常遗留的 JVM
        save_pid(self.proc.pid)
        # 子线程读流写文件(不阻塞 GUI)
        self._thread = threading.Thread(target=self._pump, args=(out_path,),
                                        daemon=True)
        self._thread.start()
        return True, ""

    def _pump(self, out_path):
        """子线程: 逐行读 java 输出写入文件(UTF-8/GBK 兜底, 统一换行)。"""
        try:
            with open(out_path, "a", encoding="utf-8", newline="") as f:
                for raw in iter(self.proc.stdout.readline, b""):
                    try:
                        line = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        line = raw.decode("gbk", errors="replace")
                    # 探测端口占用报错(启动后几秒内出现), 供 GUI 提示
                    if "Port" in line and "already in use" in line:
                        self.port_error = True
                    # 去掉行尾 \r\n, 统一用 \n 写(避免残留 \r 造成空行)
                    f.write(line.rstrip("\r\n") + "\n")
                    f.flush()
        except Exception:
            pass

    def stop(self):
        """终止进程树。

        Windows 上 terminate() 只杀直接子进程, java launcher 甩出去的 JVM
        会残留并继续占用 8082 端口, 故用 taskkill /T /F 连子进程一起杀。
        """
        if self.proc is not None and self.proc.poll() is None:
            _kill_tree(self.proc.pid)
            try:
                self.proc.wait(timeout=5)
            except Exception:
                pass
        self.proc = None
        clear_saved_pid()


def _items_matched(items, kw, obj=None):
    """判断是否命中关键字。

    匹配范围: 信号/标签/值/事件元信息 + 整条记录的原始 JSON(保证 JsonDelegate 里
    出现的任何内容都能搜到, 如 INDICATOR_LIGHT 的 wellKnownIndicator)。
    """
    for signal, tags, tags_raw, value, err, m, vdisplay, vdetail in items:
        hay = [signal] + list(tags.keys()) + [str(v) for v in tags.values()]
        hay += [str(vdisplay), str(err)]
        if any(kw in str(x).lower() for x in hay):
            return True
    if obj is not None:
        conditions, label = event_meta(obj)
        if label and kw in label.lower():
            return True
        if any(kw in c.lower() for c in conditions):
            return True
        # 匹配 conditions 的 requiredMetrics(信号名/值)
        for c in event_conditions(obj):
            for m in c["metrics"]:
                if kw in m["signal"].lower() or kw in str(m["value"]).lower():
                    return True
        # 兜底: 整条记录原始 JSON 子串匹配(覆盖所有字段)
        if kw in group_raw_str(obj).lower():
            return True
    return False


def group_raw_str(obj):
    """把记录对象序列化成 JSON 字符串(供全文搜索)。"""
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return str(obj)


class FeedGUI:
    def __init__(self, root, records, file_path):
        self.root = root
        self._cfg = load_config()       # 持久化配置
        self.records = records          # 共享全量(供 Tab2 总线对照使用, 不被裁剪)
        self.file_path = file_path
        self.newest_first = True        # 排序: True=最新在上
        # 时间窗: None=全部, 5/10/30/60=分钟(从配置恢复)
        _wm = {"最近5分钟": 5, "最近10分钟": 10, "最近30分钟": 30, "最近1小时": 60}
        self.window_minutes = _wm.get(self._cfg.get("window"), None)
        self.feed_records = records     # Tab1 树数据源(初始=全量, 切时间窗/刷新时更新)
        self._feed_auto_after = None    # Tab1 自动刷新定时器
        self._iid_rec = {}              # 树节点 iid -> rec 映射(供增量删旧)
        self._feed_proc = FeedProcess() # 命令行数据源的 java 进程
        self._idea_path = file_path     # FEED-IDEA 模式路径(切 SNAPSHOT 后用于切回)
        self._wait_start = None         # FEED-SNAPSHOT 等待数据开始时间
        self._wait_after = None         # 等待数据提示的定时器
        # 增量读取器: 自动刷新时只读新增行, 不从文件头重扫
        self._feed_tail = FileTailParser(file_path)
        self._feed_tail.offset = _file_size(file_path)  # 从文件末尾起追新
        root.title("Feed 数据监控与总线对照")
        root.geometry("1200x760")
        # 关闭窗口时保存配置
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 主容器: Notebook 两个 Tab
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=4, pady=4)

        # Tab1: Feed 数据监控
        tab1 = ttk.Frame(self.notebook)
        self.notebook.add(tab1, text="Feed 数据监控")
        self._build_feed_tab(tab1)

        # Tab2: 总线数据对照
        tab2 = ttk.Frame(self.notebook)
        self.notebook.add(tab2, text="总线数据对照")
        self._bus_tab = BusCompareTab(self, tab2)

    def _build_feed_tab(self, root_frame):
        """构建 Feed 数据监控 Tab: 数据源配置 + 搜索栏 + 工具栏 + 左树右详情。"""
        # 数据源选择行
        src_row = ttk.Frame(root_frame)
        src_row.pack(fill="x", padx=8, pady=(6, 0))
        ttk.Label(src_row, text="数据源:").pack(side="left")
        self.source_var = tk.StringVar(
            value=_norm_source(self._cfg.get("data_source")) or SRC_IDEA)
        self.source_combo = ttk.Combobox(
            src_row, textvariable=self.source_var, width=14, state="readonly",
            values=[SRC_IDEA, SRC_SNAPSHOT])
        self.source_combo.pack(side="left", padx=4)
        self.source_combo.bind("<<ComboboxSelected>>", self.on_source_change)

        # 文件模式控件
        self.file_row = ttk.Frame(src_row)
        ttk.Label(self.file_row, text="Feed路径:").pack(side="left")
        self.feed_path_var = tk.StringVar(value=self.file_path)
        ttk.Entry(self.file_row, textvariable=self.feed_path_var,
                  width=52).pack(side="left", padx=6)
        ttk.Button(self.file_row, text="加载",
                   command=self.on_load_feed_path).pack(side="left")

        # FEED-SNAPSHOT 模式控件(jar 自动取程序同目录下的 .jar)
        self.cmd_row = ttk.Frame(src_row)
        ttk.Label(self.cmd_row, text="FESN:").pack(side="left")
        self.fesn_var = tk.StringVar(
            value=self._cfg.get("fesn") or DEFAULT_FESN)
        ttk.Entry(self.cmd_row, textvariable=self.fesn_var, width=14).pack(
            side="left", padx=4)
        self.start_btn = ttk.Button(self.cmd_row, text="启动",
                                    command=self.on_start_cmd)
        self.start_btn.pack(side="left", padx=2)
        self.stop_btn = ttk.Button(self.cmd_row, text="停止",
                                   command=self.on_stop_cmd, state="disabled")
        self.stop_btn.pack(side="left", padx=2)
        self.jar_label_var = tk.StringVar(value="")
        ttk.Label(self.cmd_row, textvariable=self.jar_label_var,
                  foreground="#666").pack(side="left", padx=(8, 0))

        # 时间范围 + 自动刷新: 靠右固定, 不受中间控件切换影响
        self.feed_auto_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(src_row, text="自动刷新", variable=self.feed_auto_var,
                        command=self.toggle_feed_auto).pack(side="right", padx=8)

        self.window_var = tk.StringVar(
            value=self._cfg.get("window") or "全部")
        self.window_combo = ttk.Combobox(
            src_row, textvariable=self.window_var, width=10, state="readonly",
            values=["全部", "最近5分钟", "最近10分钟", "最近30分钟", "最近1小时"])
        self.window_combo.pack(side="right", padx=4)
        self.window_combo.bind("<<ComboboxSelected>>", self.on_window_change)
        ttk.Label(src_row, text="时间范围:").pack(side="right", padx=(16, 0))

        # 按当前数据源显示对应控件
        self._show_source_row()

        # 顶部: 搜索框 + 工具栏
        top = ttk.Frame(root_frame)
        top.pack(fill="x", padx=8, pady=6)
        ttk.Label(top, text="搜索:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self.on_search)
        search = ttk.Entry(top, textvariable=self.search_var, width=26)
        search.pack(side="left", padx=6)

        # 信号剔除: 逗号分隔多个, 命中的记录整条不显示(如高频无用的 jmc-idps-log)
        ttk.Label(top, text="剔除:").pack(side="left")
        self.filter_var = tk.StringVar(value=self._cfg.get("signal_filter") or "")
        self.filter_var.trace_add("write", self.on_search)
        filt = ttk.Entry(top, textvariable=self.filter_var, width=22)
        filt.pack(side="left", padx=6)
        ttk.Label(top, text="(逗号分隔可填多个)").pack(side="left")

        # 工具栏按钮
        ttk.Button(top, text="展开全部", command=self.expand_all).pack(side="left")
        ttk.Button(top, text="折叠全部", command=self.collapse_all).pack(
            side="left", padx=(4, 0))
        ttk.Button(top, text="刷新", command=self.on_refresh).pack(
            side="left", padx=(4, 0))

        self.status_var = tk.StringVar()
        ttk.Label(top, textvariable=self.status_var).pack(side="right")

        # 主区域: 左树 + 右详情
        paned = ttk.PanedWindow(root_frame, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # 左: 树
        tree_frame = ttk.Frame(paned)
        paned.add(tree_frame, weight=3)
        self.tree = ttk.Treeview(tree_frame, show="tree headings",
                                 columns=("value", "time"))
        self.tree.heading("#0", text="事件/信号")
        self.tree.heading("value", text="值")
        self.tree.heading("time", text="时间 ↓", command=self.on_toggle_sort)
        self.tree.column("#0", width=380)
        self.tree.column("value", width=200, anchor="w")
        self.tree.column("time", width=200, anchor="w")
        ys = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        xs = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.tree.tag_configure("hl", background="#fff3a0")  # 命中高亮
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Motion>", self.on_tree_motion)

        # tooltip 状态
        self._tip_after_id = None   # 延迟显示的 after id
        self._tip_win = None        # tooltip 窗口
        self._tip_text = ""         # 当前显示的内容
        self._tip_item = None       # 悬停的 item
        self._tip_last_pos = None   # 上次处理的位置(去重用)
        self._tip_font = None       # 字体测量对象(缓存)

        # 右: 详情
        detail_frame = ttk.Frame(paned)
        paned.add(detail_frame, weight=2)
        self.detail = tk.Text(detail_frame, wrap="none", state="disabled",
                              font=("Consolas", 10))
        ds = ttk.Scrollbar(detail_frame, orient="vertical",
                           command=self.detail.yview)
        dxs = ttk.Scrollbar(detail_frame, orient="horizontal",
                            command=self.detail.xview)
        self.detail.configure(yscrollcommand=ds.set, xscrollcommand=dxs.set)
        self.detail.grid(row=0, column=0, sticky="nsew")
        ds.grid(row=0, column=1, sticky="ns")
        dxs.grid(row=1, column=0, sticky="ew")
        detail_frame.rowconfigure(0, weight=1)
        detail_frame.columnconfigure(0, weight=1)

        self.node_detail = {}  # tree item id -> 详情文本
        self.build()

    # ---------- 数据源切换 ----------
    def _show_source_row(self):
        """按当前数据源显示对应控件行(不 expand, 避免挤占后面的控件)。"""
        if self.source_var.get() == SRC_SNAPSHOT:
            self.file_row.pack_forget()
            self.cmd_row.pack(side="left")
        else:
            self.cmd_row.pack_forget()
            self.file_row.pack(side="left")

    def on_source_change(self, _event=None):
        """切换数据源: FEED-IDEA(文件) <-> FEED-SNAPSHOT(命令行)。

        Tab2(总线对照) 的 Feed 值跟随当前数据源:
          - 切到 SNAPSHOT: Tab2 改读命令行输出文件
          - 切回 IDEA:     Tab2 改回原 Feed 路径
        """
        self._show_source_row()
        if self.source_var.get() == SRC_IDEA:
            # 切回文件: 若 cmd 进程在跑则停掉
            if self._feed_proc.running:
                self.on_stop_cmd()
            # Tab2 切回 FEED-IDEA 的原路径
            self.file_path = self._idea_path
            self._bus_tab.set_path(self._idea_path)
            self.feed_path_var.set(self._idea_path)
            self.status("已切回 FEED-IDEA 数据源")
        else:
            # 切到 SNAPSHOT: 立刻指向命令行输出文件(java 可能还没启动,
            # 此时文件里是上次残留数据; 启动后会清空重写)
            self.file_path = CMD_OUTPUT_PATH
            self._bus_tab.set_path(CMD_OUTPUT_PATH)
            self.status("已切到 FEED-SNAPSHOT 数据源(点[启动]运行 jar)")

    def on_start_cmd(self):
        """启动 FEED-SNAPSHOT 数据源(java 命令行, jar 取程序同目录)。"""
        fesn = self.fesn_var.get().strip()
        if not fesn:
            self.status("请填写 FESN")
            return
        # 自动查找程序同目录下的 jar
        jar = find_local_jar()
        if not jar:
            self.status(f"未找到 jar 文件(需放在 {_BASE_DIR} 下)")
            return
        self.jar_label_var.set(f"jar: {os.path.basename(jar)}")
        ok, err = self._feed_proc.start(jar, fesn, CMD_OUTPUT_PATH)
        if not ok:
            self.status(err)
            return
        # 输出文件作为 Feed 数据源(start 已清空该文件)
        self.file_path = CMD_OUTPUT_PATH
        self.feed_path_var.set(CMD_OUTPUT_PATH)
        self._feed_tail = FileTailParser(CMD_OUTPUT_PATH)
        self._feed_tail.offset = 0
        # Tab2 同步: 文件刚被清空, 必须重置其增量解析器与索引
        self._bus_tab.set_path(CMD_OUTPUT_PATH)
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        # 开启自动刷新, 让数据实时显示
        self.feed_auto_var.set(True)
        self.toggle_feed_auto()
        # 开始"等待数据"提示(FEED-SNAPSHOT 数据到达通常较慢)
        self._start_wait_hint(fesn, os.path.basename(jar))

    def _start_wait_hint(self, fesn, jar_name):
        """启动后显示"等待数据中", 并每秒更新已等待时长。"""
        import time
        self._wait_start = time.time()
        self._tick_wait_hint()

    def _tick_wait_hint(self):
        """每秒刷新等待提示; 数据到达后自动停止。"""
        if self._wait_start is None:
            return
        import time
        elapsed = int(time.time() - self._wait_start)
        # 端口被占: java 起得来但服务绑不上端口, 数据永远不来, 主动提示
        if self._feed_proc.port_error or self._feed_proc.port_conflict:
            self.status(f"⚠ 端口 {FEED_PORT} 被占用, java 服务启动失败"
                        f"(请先关闭占用该端口的程序)")
            return
        self.status(f"⏳ 等待数据中… 已等待 {elapsed} 秒")
        self._wait_after = self.root.after(1000, self._tick_wait_hint)

    def _stop_wait_hint(self):
        """数据到达或停止时, 结束等待提示。"""
        self._wait_start = None
        if self._wait_after:
            self.root.after_cancel(self._wait_after)
            self._wait_after = None

    def on_stop_cmd(self):
        """停止 FEED-SNAPSHOT 数据源(java 命令行)。"""
        self._stop_wait_hint()
        self._feed_proc.stop()
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.status("已停止 FEED-SNAPSHOT 数据源")

    def status(self, text):
        self.status_var.set(text)

    def hl_with_parents(self, iid):
        """标亮该节点及其所有祖先, 形成 三级->二级->一级 的命中链路。"""
        cur = iid
        while cur:
            self.tree.item(cur, tags=("hl",))
            cur = self.tree.parent(cur)

    # ---------- tooltip ----------
    def _node_text(self, iid, column):
        """取树节点的显示文本: #0 为信号列, #1/#2 为值列/时间列。总是返回 str。"""
        if column == "#0":
            v = self.tree.item(iid, "text")
            return "" if v is None else str(v)
        values = self.tree.item(iid, "values")
        # identify_column 返回列索引(#1/#2), 映射到 values 元组位置
        if column == "#1" and values:
            return "" if values[0] is None else str(values[0])
        if column == "#2" and len(values) > 1:
            return "" if values[1] is None else str(values[1])
        return ""

    def on_tree_motion(self, event):
        """鼠标移动: 若悬停节点的文本超长, 延迟显示 tooltip。

        性能优化:
          - 鼠标在同一节点同一列时, 不重复 identify/测量
          - 字体测量结果缓存
        """
        row = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)

        # tooltip 已显示且仍在同一节点: 只需跟随鼠标移动, 不重复测量
        if self._tip_item and (row, column) == (self._tip_item[0], self._tip_item[1]):
            if self._tip_win:
                self._move_tip()
            return

        # 同一节点快速掠过时, 不重复测量
        if self._tip_last_pos == (row, column):
            return
        self._tip_last_pos = (row, column)

        if self._tip_after_id:
            self.root.after_cancel(self._tip_after_id)
            self._tip_after_id = None

        if not row:
            self._hide_tip()
            return
        region = self.tree.identify("region", event.x, event.y)
        # 树列(#0)的 region 是 "tree", 数据列是 "cell"; 两者都应支持
        if region not in ("cell", "tree"):
            self._hide_tip()
            return

        text = self._node_text(row, column)
        if not text:
            self._hide_tip()
            return

        # 判断是否超长: 用字体测量宽度, 超过所在列宽才弹
        # 字体测量对象缓存, 避免每次 new 开销
        if self._tip_font is None:
            try:
                self._tip_font = tkfont.Font(
                    font=ttk.Style().lookup("Treeview", "font"))
            except Exception:
                self._tip_font = False
        if self._tip_font:
            text_w = self._tip_font.measure(text)
            col_w = self.tree.column(column, "width")
        else:
            text_w, col_w = len(text) * 8, 200  # 兜底估算

        # 列宽可能被 stretch 撑宽, 额外用文本长度兜底: 超过 30 字符必弹
        if text_w <= col_w + 20 and len(text) <= 30:
            self._hide_tip()
            return

        # 记录悬停内容, 延迟显示
        self._tip_item = (row, column, text)
        self._tip_after_id = self.root.after(500, self._show_tip)

    def _show_tip(self):
        """在鼠标位置显示 tooltip。"""
        self._tip_after_id = None
        if not self._tip_item:
            return
        row, column, text = self._tip_item
        if self._tip_text == text and self._tip_win:
            return  # 内容未变
        self._tip_text = text

        # 复用或新建窗口
        if self._tip_win is None:
            self._tip_win = tk.Toplevel(self.root)
            self._tip_win.overrideredirect(True)  # 无边框
            self._tip_win.attributes("-topmost", True)
            self._tip_label = tk.Label(self._tip_win, bg="#ffffe0", relief="solid",
                                       borderwidth=1, justify="left",
                                       wraplength=500, font=("Consolas", 9))
            self._tip_label.pack()
        self._tip_label.config(text=text)
        self._move_tip()
        self._tip_win.deiconify()

    def _move_tip(self):
        """把 tooltip 移到鼠标附近(偏移防遮挡)。"""
        if not self._tip_win:
            return
        x = self.root.winfo_pointerx() + 15
        y = self.root.winfo_pointery() + 15
        self._tip_win.geometry(f"+{x}+{y}")

    def _hide_tip(self):
        if self._tip_after_id:
            self.root.after_cancel(self._tip_after_id)
            self._tip_after_id = None
        self._tip_item = None
        if self._tip_win:
            self._tip_win.withdraw()

    def _add_signal_children(self, node, signal, tags, tags_raw, value, m, lt, kw):
        """给信号节点添加子节点(标签/特殊展开/值键值对)。"""
        # CONFIGURATION 信号: 专门的备车数据展开
        if signal == "CONFIGURATION":
            self.build_configuration(node, m, kw)
            return
        # INDICATOR_LIGHT 信号: 健康指示灯专门展开
        if signal == "INDICATOR_LIGHT":
            self.build_indicator(node, m, lt, kw)
            return
        # POSITION 信号: 展开 纬度/经度/海拔
        if signal == "POSITION":
            self.build_position(node, m, lt, kw)
            return
        # 标签节点
        for tag_name, tag_value in tags.items():
            leaf = self.tree.insert(node, "end", text=f"{tag_name}",
                                    values=(tag_value, lt))
            raw_tag = tags_raw.get(tag_name, {})
            self.node_detail[leaf] = (f"标签: {tag_name}\n值: {tag_value}\n"
                                      f"--- 原始数据 ---\n{to_json(raw_tag)}")
            if kw and (kw in tag_name.lower() or
                       kw in str(tag_value).lower()):
                self.hl_with_parents(leaf)
        # 单键 dict 值(如 enumValue): 键值对节点放最下面
        k, vv = value_kv(value)
        if k is not None:
            vleaf = self.tree.insert(node, "end", text=f"{k}",
                                     values=(vv, lt))
            self.node_detail[vleaf] = (f"值 {k}: {vv}\n"
                                       f"--- 原始数据 ---\n{to_json(value)}")
            if kw and (kw in k.lower() or kw in str(vv).lower()):
                self.hl_with_parents(vleaf)

    def _insert_record(self, rec, kw, index="end", items=None):
        """把一条记录插入树, 返回一级节点 iid。

        index="end" 追加到末尾; index=0 插入到顶部(新记录实时刷新用)。
        Metric 记录只含 1 个信号, 合并层级: 一级节点直接是信号。
        Event 记录保留记录层(可能含多个信号/conditions)。
        items: 可选, 已拆解的指标列表(避免重复调用 metric_items)。
        """
        obj = rec["obj"]
        if items is None:
            items = metric_items(obj)
        if kw and not _items_matched(items, kw, obj):
            return None

        # 子节点时间列统一留空(时间只在一级显示), 减少重复噪音
        lt = ""
        # 时间列用解析时缓存的数据产生时间(避免重复解析 ISO/转时区)
        dtime = rec.get("data_time") or data_time(obj)

        # --- Metric(仅1信号): 合并层级, 一级=信号 ---
        if atype(obj) == "Metric" and len(items) == 1:
            signal, tags, tags_raw, value, err, m, vdisplay, vdetail = items[0]
            node = self.tree.insert("", index, text=short_signal(signal),
                                    open=False, values=(vdisplay, dtime))
            self.node_detail[node] = self.signal_detail(
                signal, tags, value, err, m, vdisplay, vdetail)
            self._iid_rec[node] = rec
            if kw:
                self.tree.item(node, tags=("hl",))
            self._add_signal_children(node, signal, tags, tags_raw, value, m,
                                      lt, kw)
            return node

        # --- Event / 多信号 Metric: 保留记录层 ---
        parent = self.tree.insert("", index, text=record_title(rec),
                                  open=False, values=("", dtime))
        self.node_detail[parent] = self.group_detail(rec)
        # 记录 iid -> rec 映射(供删旧/恢复展开用)
        self._iid_rec[parent] = rec
        # 搜索状态下, 记录节点本身标亮(作为链路起点; 子节点命中会由 hl_with_parents 再标)
        if kw:
            self.tree.item(parent, tags=("hl",))

        # Event 记录的 conditions: 一级值列显示 condition 名, 二级直接显示信号
        if atype(obj) == "Event":
            conds = event_conditions(obj)
            if conds:
                cond_names = " ".join(c["condition"] for c in conds)
                self.tree.set(parent, "value", cond_names)
                # metrics 数组里已存在的信号名(避免 requiredMetrics 重复插入)
                metrics_signals = {s for s, *_ in items}
                for c in conds:
                    for m in c["metrics"]:
                        if m["signal"] in metrics_signals:
                            continue  # 该信号会在信号循环里插入, 跳过
                        child = self.tree.insert(
                            parent, "end", text=short_signal(m["signal"]),
                            open=False, values=(m["value"], lt))
                        self.node_detail[child] = (
                            f"条件 {c['condition']}\n"
                            f"信号 {m['signal']} = {m['value']}\n"
                            f"--- 原始数据 ---\n{to_json(m['raw'])}")
                        if kw and (kw in m["signal"].lower() or
                                   kw in str(m["value"]).lower()):
                            self.hl_with_parents(child)
            # StateTransition 事件(无 wellKnownLabel): 展开状态流转
            st = state_transition_info(obj)
            if st:
                self.build_state_transition(parent, st, lt, kw)

        for signal, tags, tags_raw, value, err, m, vdisplay, vdetail in items:
            child = self.tree.insert(parent, "end", text=short_signal(signal),
                                     open=False, values=(vdisplay, lt))
            self.node_detail[child] = self.signal_detail(
                signal, tags, value, err, m, vdisplay, vdetail)
            # 信号命中: 标亮 信号+记录
            if kw and kw in signal.lower():
                self.hl_with_parents(child)
            self._add_signal_children(child, signal, tags, tags_raw, value, m,
                                      lt, kw)
        # oemData: 按原数据顺序(信号之后), 直接展开键值对
        if atype(obj) == "Event":
            oem_items = oem_data_items(obj)
            if oem_items:
                self.build_oem_data(parent, oem_items, lt, kw)
        return parent

    def build(self):
        """重建树(带搜索过滤), 按数据产生时间排序。"""
        kw = self.search_var.get().strip().lower()
        self.tree.delete(*self.tree.get_children())
        self._iid_rec = {}
        shown = 0
        # 按数据产生时间 + 打印顺序排序(时间相同按 group, 保持文件原始顺序)
        records = sorted(
            self.feed_records,
            key=lambda r: (r.get("data_time") or r.get("log_time", ""),
                           r.get("group", 0)),
            reverse=self.newest_first)
        filters = parse_filters(self.filter_var.get())
        dropped = 0
        for rec in records:
            obj = rec["obj"]
            items = metric_items(obj)
            if is_filtered(obj, filters):
                dropped += 1
                continue
            if kw and not _items_matched(items, kw, obj):
                continue
            # 复用已拆解的 items, 避免 _insert_record 内重复调用 metric_items
            if self._insert_record(rec, kw, items=items) is not None:
                shown += 1
        self.status(f"共 {len(self.feed_records)} 条记录, 显示 {shown} 条"
                    + (f", 剔除 {dropped} 条" if dropped else "")
                    + f"({kw and ('搜索: ' + kw) or '全部'})"
                    f"{' [窗口:' + self.window_var.get() + ']' if hasattr(self, 'window_var') else ''}")

    def build_configuration(self, child, m, kw):
        """CONFIGURATION 信号: 展开 配置类型 -> 备车开关 -> 每个备车时间块。"""
        # 用 parser 的统一解析函数(兼容 Metric/Event 两种结构)
        config_label, feature_status, blocks = configuration_items(
            {"data": {"signal": {"wksSignal": "CONFIGURATION"},
                      "configurationValue": m.get("configurationValue")}})

        def hl(node_iid, text):
            if kw and kw in str(text).lower():
                self.hl_with_parents(node_iid)  # 标亮自身+信号+记录

        # 配置类型
        cfg = self.tree.insert(child, "end", text="configuration",
                               values=(config_label, ""))
        self.node_detail[cfg] = f"配置类型 configuration: {config_label}"
        hl(cfg, config_label)

        # 备车开关
        xev = (m.get("configurationValue") or {}).get("xevDepartureSchedules") or {}
        fst = self.tree.insert(child, "end", text="departureScheduleFeatureStatus",
                               values=(feature_status, ""))
        self.node_detail[fst] = (f"备车开关 departureScheduleFeatureStatus: {feature_status}\n"
                                 f"--- 原始数据 ---\n"
                                 f"{to_json(xev.get('departureScheduleFeatureStatus'))}")
        hl(fst, feature_status)

        # 每个备车时间块
        for b in blocks:
            block = self.tree.insert(
                child, "end",
                text=f"备车 {b['scheduleId']} | {b['dayOfWeek']} "
                     f"{b['hours']}时 | {b['scheduleType']}",
                open=False, values=(b["scheduleStatus"], ""))
            self.node_detail[block] = (f"备车项 scheduleId: {b['scheduleId']}\n"
                                       f"备车状态 scheduleStatus: {b['scheduleStatus']}\n"
                                       f"--- 原始数据 ---\n{to_json(b['raw'])}")
            hl(block, b["scheduleId"])

            fields = [
                ("scheduleId", b["scheduleId"]),
                ("scheduleStatus", b["scheduleStatus"]),
                ("scheduleType", b["scheduleType"]),
                ("dayOfWeek", b["dayOfWeek"]),
                ("hours", b["hours"]),
                ("timeZone", b["timeZone"]),
                ("scheduleExecutor", b["scheduleExecutor"]),
                ("chrg_go_t_prcond_d_stat", b["chrg_go_t_prcond_d_stat"]),
            ]
            for name, val in fields:
                leaf = self.tree.insert(block, "end", text=name, values=(val, ""))
                self.node_detail[leaf] = f"{name}: {val}"
                hl(leaf, val)

    def build_indicator(self, child, m, lt, kw):
        """INDICATOR_LIGHT 信号: 展开 指示灯名/状态/附加信息。"""
        # 用 parser 的统一解析函数
        wki, state, add_info = indicator_items(
            {"data": {"signal": {"wksSignal": "INDICATOR_LIGHT"},
                      "indicatorValue": m.get("indicatorValue")}})

        def hl(node_iid, text):
            if kw and kw in str(text).lower():
                self.hl_with_parents(node_iid)

        # 指示灯名
        n1 = self.tree.insert(child, "end", text="wellKnownIndicator",
                              values=(wki, lt))
        self.node_detail[n1] = f"指示灯 wellKnownIndicator: {wki}"
        hl(n1, wki)

        # 指示灯状态
        n2 = self.tree.insert(child, "end", text="indicatorState",
                              values=(state, lt))
        self.node_detail[n2] = f"状态 indicatorState: {state}"
        hl(n2, state)

        # 附加信息 value(去掉 additionalInfo 中间层, 直接显示 value)
        av = add_info.get("value")
        if av is not None:
            n3 = self.tree.insert(child, "end", text="value",
                                  values=(av, lt))
            self.node_detail[n3] = (f"值 value: {av}\n"
                                    f"--- 原始数据 ---\n{to_json(add_info)}")
            hl(n3, av)

    def build_position(self, child, m, lt, kw):
        """POSITION 信号: 展开 纬度/经度/海拔。位置无效时显示 INVALID。"""
        pv = m.get("positionValue") or {}
        lat, lon, alt = _position_parts(pv)

        def hl(node_iid, text):
            if kw and kw in str(text).lower():
                self.hl_with_parents(node_iid)

        if lat is None:
            n0 = self.tree.insert(child, "end", text="positionValue",
                                  values=("INVALID", lt))
            self.node_detail[n0] = f"位置无效 positionValue: {pv}"
            hl(n0, "INVALID")
            return
        # 纬度
        n1 = self.tree.insert(child, "end", text="latitude",
                              values=(lat, lt))
        self.node_detail[n1] = f"纬度 latitude: {lat}"
        hl(n1, lat)
        # 经度
        n2 = self.tree.insert(child, "end", text="longitude",
                              values=(lon, lt))
        self.node_detail[n2] = f"经度 longitude: {lon}"
        hl(n2, lon)
        # 海拔
        n3 = self.tree.insert(child, "end", text="altitude",
                              values=(alt, lt))
        self.node_detail[n3] = f"海拔 altitude: {alt}"
        hl(n3, alt)

    def build_state_transition(self, parent, st, lt, kw):
        """StateTransition 事件: 一级值列显示状态流转, 展开详情字段。"""
        def hl(node_iid, text):
            if kw and kw in str(text).lower():
                self.hl_with_parents(node_iid)

        # 一级值列: fromState -> toState
        transition = f"{st['from_state']} → {st['to_state']}"
        if st["from_state"] or st["to_state"]:
            self.tree.set(parent, "value", transition)

        fields = [
            ("stringFsmName", st["fsm"]),
            ("stringFromState", st["from_state"]),
            ("stringToState", st["to_state"]),
            ("stringTrigger", st["trigger"]),
            ("message", st["message"]),
            ("commandType", st["command_type"]),
            ("source", st["source"]),
        ]
        for name, val in fields:
            if not val:
                continue
            node = self.tree.insert(parent, "end", text=name,
                                    open=False, values=(val, lt))
            self.node_detail[node] = f"{name}: {val}"
            hl(node, val)

    def build_oem_data(self, parent, oem_items, lt, kw):
        """oemData 展开: 键值对直接作为二级节点(无 oemData 中间层)。"""
        def hl(node_iid, text):
            if kw and kw in str(text).lower():
                self.hl_with_parents(node_iid)

        for key, val in oem_items:
            node = self.tree.insert(parent, "end", text=key,
                                    open=False, values=(val, lt))
            self.node_detail[node] = f"{key}: {val}"
            hl(node, key)
            hl(node, val)

    def group_detail(self, rec):
        obj = rec["obj"]
        conditions, label = event_meta(obj)
        parts = [f"记录 #{rec['group']}",
                 f"日志时间: {rec['log_time']}",
                 f"类型: {atype(obj)}",
                 f"数据时间: {data_time(obj)}",
                 f"vin: {(obj.get('vin') or '')}",
                 f"esn: {(obj.get('esn') or '')}"]
        if label:
            parts.append(f"事件标签 wellKnownLabel: {label}")
        # conditions 结构化详情
        conds = event_conditions(obj)
        if conds:
            parts.append("触发条件 conditions:")
            for c in conds:
                head = f"  - {c['condition']}"
                if c["metrics"]:
                    parts.append(head)
                    for m in c["metrics"]:
                        parts.append(f"      {m['signal']} = {m['value']}")
                else:
                    parts.append(head)
        # StateTransition 事件详情
        st = state_transition_info(obj)
        if st:
            parts.append("事件类型: StateTransition")
            parts.append(f"事件ID: {st['id']}")
            if st["message"]:
                parts.append(f"消息: {st['message']}")
            if st["fsm"]:
                parts.append(f"状态机: {st['fsm']}")
            if st["from_state"] or st["to_state"]:
                parts.append(f"状态流转: {st['from_state']} → {st['to_state']}")
            if st["trigger"]:
                parts.append(f"触发条件: {st['trigger']}")
            if st["command_type"]:
                parts.append(f"命令类型: {st['command_type']}")
            if st["source"]:
                parts.append(f"来源: {st['source']}")
        # oemData 详情
        oem_items = oem_data_items(obj)
        if oem_items:
            parts.append("oemData:")
            for key, val in oem_items:
                parts.append(f"  {key}: {val}")
        parts.append("--- 原始数据 ---")
        parts.append(group_raw(rec))
        return "\n".join(parts)

    def signal_detail(self, signal, tags, value, err, m, vdisplay, vdetail):
        parts = [f"信号: {signal}"]
        # dict 值被简化展示时(单键 enumValue / INDICATOR_LIGHT 的 additionalInfo.value)
        if isinstance(value, dict) and not isinstance(vdisplay, dict):
            parts.append(f"值: {vdisplay}  ({vdetail})")
        else:
            parts.append(f"值: {value}")
        parts.append(f"错误: {err or '无'}")
        for k, v in tags.items():
            parts.append(f"标签 {k}: {v}")
        parts.append("--- 原始数据 JSON ---")
        try:
            parts.append(json.dumps(m, ensure_ascii=False, indent=2))
        except Exception:
            parts.append(str(m))
        return "\n".join(parts)

    def on_search(self, *args):
        """搜索输入: 防抖, 停止输入 300ms 后才重建(避免每敲一字全量重建卡顿)。"""
        if getattr(self, "_search_after", None):
            self.root.after_cancel(self._search_after)
        self._search_after = self.root.after(300, self._do_build)

    def _do_build(self):
        self._search_after = None
        self.build()

    def on_toggle_sort(self):
        """点击时间列头: 切换排序方向, 并更新表头箭头。"""
        self.newest_first = not self.newest_first
        arrow = "↓" if self.newest_first else "↑"
        self.tree.heading("time", text=f"时间 {arrow}",
                          command=self.on_toggle_sort)
        self.build()

    def expand_all(self):
        """递归展开所有层级(记录->信号->标签->值)。"""
        def expand(iid):
            for ch in self.tree.get_children(iid):
                expand(ch)
            if iid:
                self.tree.item(iid, open=True)

        for iid in self.tree.get_children(""):
            expand(iid)

    def collapse_all(self):
        for iid in self.tree.get_children(""):
            self.tree.item(iid, open=False)

    def _reload_feed(self, msg_prefix=""):
        """按当前时间窗从文件重读, 更新 Tab1 树数据(feed_records)。"""
        try:
            new_records = parse_log_range(self.file_path, self.window_minutes)
        except Exception as e:
            self.status(f"{msg_prefix}失败: {e}")
            return
        self.feed_records = new_records
        # 同步共享 records(供 Tab2 用), 但保持 Tab2 已扩展的尾部不受裁剪
        # 仅当 Tab2 未运行独立扩展时刷新; 此处简单起见: 若新读比现有长则保留长的
        if len(new_records) > len(self.records):
            self.records = new_records
        self.build()
        self.status(f"{msg_prefix}共 {len(new_records)} 条记录"
                    f"({self.window_var.get()})")

    def on_refresh(self):
        """手动刷新: 按当前时间窗重新读文件。"""
        self._reload_feed("刷新")

    def on_load_feed_path(self):
        """按输入的 Feed 路径重新加载文件, 并同步 Tab2 的解析器。"""
        new_path = self.feed_path_var.get().strip()
        if not os.path.exists(new_path):
            self.status(f"文件不存在: {new_path}")
            return
        self.file_path = new_path
        self._idea_path = new_path   # 记住 IDEA 模式路径(切回时用)
        # 重建增量读取器(新文件从尾追新)
        self._feed_tail = FileTailParser(new_path)
        self._feed_tail.offset = _file_size(new_path)
        self._reload_feed("已加载")
        # 同步 Tab2 的增量解析器到新路径
        self._bus_tab.set_path(new_path)

    def on_window_change(self, _event=None):
        """时间窗切换: 按新窗口从文件重读。"""
        # 档位 -> 分钟
        w = self.window_var.get()
        self.window_minutes = {"全部": None, "最近5分钟": 5, "最近10分钟": 10,
                               "最近30分钟": 30, "最近1小时": 60}.get(w, None)
        self._reload_feed(f"[{w}] ")

    def toggle_feed_auto(self):
        """Tab1 自动刷新开关。"""
        if self.feed_auto_var.get():
            self._schedule_feed_auto()
        else:
            if self._feed_auto_after:
                self.root.after_cancel(self._feed_auto_after)
                self._feed_auto_after = None

    def _schedule_feed_auto(self):
        """排定下一次 Tab1 自动刷新(增量插新, 不重建树, 保留展开状态)。"""
        if not self.feed_auto_var.get():
            return
        try:
            self._feed_incremental()
        except Exception:
            pass  # 增量失败不中断定时
        self._feed_auto_after = self.root.after(3000, self._schedule_feed_auto)

    def _find_insert_index(self, rec):
        """按数据时间 + 打印顺序, 找到新记录应插入的树位置(保持排序)。

        newest_first=True(最新在上): 时间越大越靠上(索引越小)。
        时间相同时按 group(打印顺序): 后打印的排前面。
        返回插入用的 index(整数)。若在"最早在上"模式, 由调用方决定是否用。
        """
        my_t = rec.get("data_time") or rec.get("log_time", "")
        my_g = rec.get("group", 0)
        children = self.tree.get_children("")
        for i, iid in enumerate(children):
            r = self._iid_rec.get(iid)
            if r is None:
                continue
            t = r.get("data_time") or r.get("log_time", "")
            g = r.get("group", 0)
            if self.newest_first:
                # 降序: 新记录更大(更新) -> 插在前面
                if t < my_t or (t == my_t and g < my_g):
                    return i
            else:
                # 升序: 新记录更小(更旧) -> 插在前面
                if t > my_t or (t == my_t and g > my_g):
                    return i
        return "end"  # 都不满足 -> 追加末尾

    def _feed_incremental(self):
        """增量刷新: 只读新增记录按数据时间插入树, 旧节点不动, 删超窗最旧。

        保持视口: tkinter 插行时默认保持当前可见内容位置, 滑块自动变化。
        """
        # 记录当前选中的一级记录(便于增量插入时维持高亮, 若仍存在)
        sel = self.tree.selection()
        anchor = sel[0] if sel else None
        try:
            new_recs = self._feed_tail.read_new()
        except Exception:
            new_recs = []
        if not new_recs:
            return
        # 追加到 feed_records
        self.feed_records.extend(new_recs)
        kw = self.search_var.get().strip().lower()
        filters = parse_filters(self.filter_var.get())
        cutoff = cutoff_str(self.window_minutes) if self.window_minutes else None
        inserted = 0
        # 按数据时间插入到正确位置(保持整体时间排序)
        for rec in new_recs:
            lt = rec.get("data_time") or rec.get("log_time", "")
            if cutoff and lt < cutoff:
                continue  # 超窗旧数据不插
            if is_filtered(rec["obj"], filters):
                continue  # 被剔除的信号不插
            idx = self._find_insert_index(rec)
            if self._insert_record(rec, kw, index=idx) is not None:
                inserted += 1
        # 删超窗/超上限的最旧节点
        removed = self._trim_old()
        # 数据已到达: 结束"等待数据"提示
        if inserted:
            self._stop_wait_hint()
        if inserted or removed:
            import time
            self.status(f"新增 {inserted} 条, 移除 {removed} 条 "
                        f"{time.strftime('%H:%M:%S')}")

    def _trim_old(self):
        """删除超出时间窗/数量上限的最旧记录节点。返回删除数。"""
        if not self.feed_records:
            return 0
        cutoff = cutoff_str(self.window_minutes) if self.window_minutes else None
        removed = 0
        # 从树底部(最旧)开始: 由于新增总是插顶, 旧记录在底部
        # 按数据产生时间判断是否超窗
        top_nodes = self.tree.get_children("")
        to_delete = []
        for iid in top_nodes:
            rec = self._iid_rec.get(iid)
            if rec is None:
                continue
            lt = rec.get("data_time") or rec.get("log_time", "")
            if cutoff and lt < cutoff:
                to_delete.append(iid)
        for iid in to_delete:
            rec = self._iid_rec.get(iid)
            self.tree.delete(iid)
            self._iid_rec.pop(iid, None)
            if rec in self.feed_records:
                self.feed_records.remove(rec)
            removed += 1
        return removed

    def on_select(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        detail = self.node_detail.get(iid, "")
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", detail)
        self.detail.configure(state="disabled")

    def _on_close(self):
        """关闭窗口前: 停止 java 进程 + 保存配置, 下次启动自动带出。"""
        # 停止命令行数据源进程和等待提示定时器, 避免残留
        try:
            self._stop_wait_hint()
            self._feed_proc.stop()
        except Exception:
            pass
        cfg = {
            "feed_path": self._idea_path,
            "window": self.window_var.get() if hasattr(self, "window_var") else "全部",
            "mapping_path": self._bus_tab.map_var.get().strip(),
            "vba_project": self._bus_tab.proj_var.get().strip(),
            "data_source": self.source_var.get(),
            "fesn": self.fesn_var.get().strip(),
            "signal_filter": self.filter_var.get().strip(),
        }
        save_config(cfg)
        self.root.destroy()


class BusCompareTab:
    """Tab2: 总线数据对照。对应表 + Feed值 + VBA总线值 并排展示。"""

    # 对照表列: 序号从0开始, #0是wksSignal列
    COLS = ("value", "dbc", "canid", "feed", "bus", "remark")
    HEADINGS = ("子信号", "TBOX_DBC", "CANID", "后台上报值(Feed)", "总线值(VBA)", "备注")

    def __init__(self, gui, frame):
        self.gui = gui
        self.root = gui.root
        self.frame = frame
        self.mapping = []
        self.feed_index = {}
        self.bus = None          # BusClient 实例
        self._bus_proj = ""      # 当前已连接的 VBA 工程名(检测变化用)
        self._timer_id = None    # 定时刷新 after id
        self._refresh_running = False  # 防止刷新重叠

        # 增量解析器: 每次刷新只读新增行, 避免全量重读
        # 初始 offset 置文件末尾, 避免与启动时 parse_log 的 records 重复
        self.tail = FileTailParser(gui.file_path)
        self.tail.offset = _file_size(gui.file_path)

        self._build_ui()
        self.load_mapping()      # 加载对应表
        self.refresh(initial=True)  # 首次刷新 Feed 值

    # ---------- UI ----------
    def _build_ui(self):
        f = self.frame
        # 顶部配置行
        cfg = ttk.Frame(f)
        cfg.pack(fill="x", padx=8, pady=6)

        ttk.Label(cfg, text="对应表:").grid(row=0, column=0, sticky="e")
        self.map_var = tk.StringVar(
            value=self.gui._cfg.get("mapping_path") or DEFAULT_MAPPING)
        ttk.Entry(cfg, textvariable=self.map_var, width=45).grid(
            row=0, column=1, padx=4)
        ttk.Button(cfg, text="加载", command=self.load_mapping).grid(
            row=0, column=2, padx=2)

        ttk.Label(cfg, text="VBA工程名:").grid(row=0, column=3, sticky="e", padx=(12, 0))
        self.proj_var = tk.StringVar(
            value=self.gui._cfg.get("vba_project") or DEFAULT_PROJECT_NAME)
        ttk.Entry(cfg, textvariable=self.proj_var, width=20).grid(
            row=0, column=4, padx=4)
        # 工程名变化时自动重连
        self.proj_var.trace_add("write", self.on_proj_change)

        # 第二行: 刷新控制
        ctl = ttk.Frame(f)
        ctl.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Label(ctl, text="刷新间隔(秒):").pack(side="left")
        self.interval_var = tk.StringVar(value="1")
        ttk.Spinbox(ctl, from_=1, to=60, textvariable=self.interval_var,
                    width=5).pack(side="left", padx=4)
        self.auto_var = tk.BooleanVar(value=False)
        self.auto_cb = ttk.Checkbutton(ctl, text="定时刷新",
                                       variable=self.auto_var,
                                       command=self.toggle_auto)
        self.auto_cb.pack(side="left", padx=8)
        ttk.Button(ctl, text="手动刷新", command=self.refresh).pack(
            side="left", padx=4)

        self.status_var = tk.StringVar()
        ttk.Label(ctl, textvariable=self.status_var).pack(side="right")

        # 对照表
        table_frame = ttk.Frame(f)
        table_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.table = ttk.Treeview(table_frame, show="tree headings",
                                  columns=self.COLS)
        self.table.heading("#0", text="wksSignal")
        for col, hd in zip(self.COLS, self.HEADINGS):
            self.table.heading(col, text=hd)
            self.table.column(col, width=110, anchor="w")
        self.table.column("value", width=100)
        self.table.column("dbc", width=180)
        self.table.column("canid", width=70)
        self.table.column("feed", width=130)
        self.table.column("bus", width=130)
        self.table.column("remark", width=220)
        ys = ttk.Scrollbar(table_frame, orient="vertical",
                           command=self.table.yview)
        xs = ttk.Scrollbar(table_frame, orient="horizontal",
                           command=self.table.xview)
        self.table.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

    # ---------- 数据 ----------
    def load_mapping(self):
        """加载对应表(按当前输入的路径), 失败时状态栏报错。"""
        path = self.map_var.get().strip()
        try:
            self.mapping = load_mapping(path)
        except Exception as e:
            self.status_var.set(f"对应表加载失败: {e}")
            self.mapping = []
            return
        self.status_var.set(f"对应表已加载: {len(self.mapping)} 行")
        self.rebuild_table()

    def rebuild_table(self):
        """重建对照表。iid 直接映射到 self.mapping 的下标。"""
        self.table.delete(*self.table.get_children())
        for idx, row in enumerate(self.mapping):
            self.table.insert("", idx, iid=str(idx),
                              text=row["wksSignal"],
                              values=(row["value"], row["tbox_dbc"],
                                      row["canid"], "", "", row["remark"]))

    def on_proj_change(self, *args):
        """VBA 工程名变化: 丢弃旧连接, 触发重连(防抖避免输入过程中反复重连)。"""
        if getattr(self, "_proj_after", None):
            self.root.after_cancel(self._proj_after)
        self._proj_after = self.root.after(800, self._do_proj_reconnect)

    def _do_proj_reconnect(self):
        self._proj_after = None
        self.bus = None  # 丢弃旧连接
        self._bus_proj = self.proj_var.get().strip()
        ok = self._connect_bus()
        if ok:
            self.status_var.set(f"VBA已连接工程: {self.proj_var.get().strip()}")
        # 重连后刷新总线值列
        self._update_bus_col()

    def _connect_bus(self):
        """连接 VBA(必要时)。返回是否连接成功。

        若 VBA 工程名已修改, 重置连接用新工程名重连。
        """
        proj = self.proj_var.get().strip()
        # 工程名变化时: 丢弃旧连接
        if self._bus_proj != proj:
            self.bus = None
            self._bus_proj = proj
        if self.bus is not None:
            return self.bus.connected
        self.bus = BusClient(DEFAULT_COM_NAME, proj)
        ok = self.bus.connect()
        if not ok:
            self.status_var.set(f"VBA未连接: {self.bus.error}")
        return ok

    def set_path(self, new_path):
        """Feed 路径变化时: 重置增量解析器并刷新。

        切换数据源/点加载都走这里。文件为空或不存在时, 明确清空索引,
        避免残留上一个数据源的旧值(Tab2 显示陈旧数据)。
        """
        self.tail = FileTailParser(new_path)
        records = []
        if new_path and os.path.exists(new_path):
            try:
                records = parse_log(new_path)
            except Exception:
                records = []
            # 已全量解析, 增量解析器从文件末尾起追新(否则 refresh 会重复读一遍)
            self.tail.offset = _file_size(new_path)
        self.gui.records = records
        self.feed_index = build_feed_index(records)
        self.refresh(initial=True)

    def refresh(self, initial=False):
        """手动/定时刷新: 增量读取 FeedOut.txt 新数据, 更新 Feed 值列 + 总线值列。"""
        # 防重叠: 定时刷新时若上一次还没跑完则跳过本次
        if self._refresh_running:
            return
        self._refresh_running = True
        try:
            # 1. 增量读取新增记录, 追加到 gui.records
            try:
                new_records = self.tail.read_new()
                if new_records:
                    self.gui.records.extend(new_records)
                    self.feed_index = build_feed_index(self.gui.records)
            except Exception:
                pass  # 读取失败保留旧索引
            # 2. 更新 Feed 值列 + 总线值列
            self._update_feed_col()
            self._update_bus_col()
        finally:
            self._refresh_running = False
            if not initial:
                import time
                self.status_var.set(f"已刷新 {time.strftime('%H:%M:%S')}")

    def _update_feed_col(self):
        """按对应表行匹配 Feed 值, 写入第4列(索引3)。"""
        for iid in self.table.get_children():
            row = self.mapping[int(iid)]
            feed = get_feed_value(self.feed_index, row["wksSignal"],
                                  row["value"])
            values = list(self.table.item(iid, "values"))
            values[3] = "" if feed is None else str(feed)
            self.table.item(iid, values=values)

    def _update_bus_col(self):
        """VBA 获取总线值, 写入第5列(索引4)。同一(canid,signal)去重。"""
        if not self.mapping:
            return
        ok = self._connect_bus()
        if not ok:
            # VBA未连接: 总线值列显示提示
            for iid in self.table.get_children():
                values = list(self.table.item(iid, "values"))
                values[4] = "VBA未连接"
                self.table.item(iid, values=values)
            return
        # 去重: (canid, tbox_dbc) -> value
        cache = {}
        for iid in self.table.get_children():
            row = self.mapping[int(iid)]
            values = list(self.table.item(iid, "values"))
            if not row["canid"] or not row["tbox_dbc"]:
                values[4] = ""
            else:
                key = (row["canid"], row["tbox_dbc"])
                if key not in cache:
                    cache[key] = self.bus.get_signal(row["canid"],
                                                     row["tbox_dbc"])
                succ, val = cache[key]
                values[4] = str(val) if succ else val
            self.table.item(iid, values=values)

    # ---------- 定时刷新 ----------
    def toggle_auto(self):
        """定时刷新开关。"""
        if self.auto_var.get():
            self._schedule()
        else:
            if self._timer_id:
                self.root.after_cancel(self._timer_id)
                self._timer_id = None

    def _schedule(self):
        """排定下一次定时刷新。"""
        if not self.auto_var.get():
            return
        try:
            interval = max(1, int(float(self.interval_var.get())))
        except ValueError:
            interval = 1
        self.refresh()
        self._timer_id = self.root.after(interval * 1000, self._schedule)


def main():
    parser = argparse.ArgumentParser(description="FeedOut JSON 浏览器")
    parser.add_argument("file", nargs="?", default=None,
                        help=f"FeedOut.txt 路径(默认读取配置或 {DEFAULT_FILE})")
    args = parser.parse_args()

    # 路径优先级: 命令行参数 > 配置文件 > 默认
    cfg = load_config()
    path = args.file or cfg.get("feed_path") or DEFAULT_FILE
    if not os.path.exists(path):
        # 文件不存在: 仍启动 GUI(让用户手动改路径), 不直接退出
        print(f"提示: 文件不存在 {path}, 请在界面中修改路径", flush=True)
        records = []
    else:
        print("解析中...", flush=True)
        records = parse_log(path)
        print(f"解析完成: {len(records)} 条记录", flush=True)

    # 清理上次异常退出遗留的 java 进程(否则它一直占着 8082, 新实例起不来)
    if clean_stale_feed_proc():
        print("已清理上次遗留的 FEED-SNAPSHOT java 进程", flush=True)

    root = tk.Tk()
    app = FeedGUI(root, records, path)
    root.mainloop()


if __name__ == "__main__":
    main()

"""
远控测试工具 - 图形界面
选择远控任务和操作，自动完成：发远控 → 录报文 → 查TSP/TBOX → 解析MF4
"""
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import sys
import os
import threading
import time
from functools import partial

# 路径处理
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from remote_config import REMOTE_CONTROL_CONFIG, API_QUERY_CONFIG_TSP, API_QUERY_CONFIG_TBOX, CAPTURE_PATH, BATCH_REPORT_DIR
from remote_control_function import APIQuery


class RemoteControlApp:
    def __init__(self, parent):
        self.parent = parent
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill=tk.BOTH, expand=True)

        self.api = APIQuery()
        self.run_status = tk.StringVar(value="待执行")
        self.first_delay = tk.IntVar(value=30)  # 首次延时/每轮开始前延时
        self.loop_count = tk.IntVar(value=1)
        self._stop_flag = threading.Event()
        self._batch_results = []
        self._sequence = []  # 有序序列 [[task_name, op_name, delay_var], ...]，可重复
        self._seq_expanded = True
        self._seq_container = None
        self._seq_task_frame = None
        self._seq_profiles = {}  # 保存的执行序列
        self._current_profile = tk.StringVar(value="自定义")
        self._profile_cb = None  # Combobox 控件引用
        self._custom_state = None  # 保存自定义模式的状态
        self._tasks = self._load_tasks()  # 从文件加载远控任务列表

        self.task_items = []  # [(task_name, op_name, display_text, BooleanVar), ...]  # [(task_name, op_name, display_text, BooleanVar), ...]
        self.entries = {}  # 配置项输入框

        self.setup_ui()

    def _add_entry(self, parent, label, default, key, row):
        ttk.Label(parent, text=f"{label}:").grid(row=row, column=0, sticky="w", pady=2)
        e = ttk.Entry(parent, width=28)
        e.insert(0, default)
        e.grid(row=row, column=1, sticky="ew", pady=2, padx=(5, 0))
        self.entries[key] = e
        return row + 1

    def _add_file_entry(self, parent, label, default, key, row):
        ttk.Label(parent, text=f"{label}:").grid(row=row, column=0, sticky="w", pady=2)
        f = ttk.Frame(parent)
        f.grid(row=row, column=1, sticky="ew", pady=2, padx=(5, 0))
        e = ttk.Entry(f, width=20)
        e.insert(0, default)
        e.pack(side="left", fill="x", expand=True)
        self.entries[key] = e
        ttk.Button(f, text="选择", width=5, command=lambda: self._browse_file(e)).pack(side="right", padx=(3, 0))
        return row + 1

    def _add_folder_entry(self, parent, label, default, key, row):
        ttk.Label(parent, text=f"{label}:").grid(row=row, column=0, sticky="w", pady=2)
        f = ttk.Frame(parent)
        f.grid(row=row, column=1, sticky="ew", pady=2, padx=(5, 0))
        e = ttk.Entry(f, width=20)
        e.insert(0, default)
        e.pack(side="left", fill="x", expand=True)
        self.entries[key] = e
        ttk.Button(f, text="选择", width=5, command=lambda: self._browse_folder(e)).pack(side="right", padx=(3, 0))
        return row + 1

    def _browse_file(self, entry):
        path = filedialog.askopenfilename(title="选择文件", filetypes=[("MF4", "*.mf4"), ("所有文件", "*.*")])
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    def _browse_folder(self, entry):
        path = filedialog.askdirectory(title="选择文件夹")
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    def _load_config_values(self):
        """从 remote_config.py 读取当前配置值"""
        config = {}
        try:
            with open(os.path.join(BASE_DIR, "remote_config.py"), "r", encoding="utf-8") as f:
                exec(f.read(), config)
        except Exception:
            config = {}
        return {
            "vin": config.get("VIN", "LXWYELR29SHNY0919"),
            "vba_project": config.get("VBA_CONFIG", {}).get("project", "ELD"),
            "vba_network": config.get("VBA_CONFIG", {}).get("network", "CAN1"),
            "vba_database": config.get("VBA_CONFIG", {}).get("database", "TCANFD"),
            "report_dir": config.get("BATCH_REPORT_DIR", os.path.join(BASE_DIR, "batch_reports")),
            "capture_path": config.get("CAPTURE_PATH", os.path.join(BASE_DIR, "capture.mf4")),
        }

    def _load_tasks(self):
        """从文件加载 REMOTE_CONTROL_TASKS，exe 环境覆盖 frozen 模块"""
        cfg = {}
        search_dirs = []
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            search_dirs.append(exe_dir)
            search_dirs.append(os.path.join(exe_dir, "Remote_Control"))
            if hasattr(sys, '_MEIPASS'):
                search_dirs.append(sys._MEIPASS)
        search_dirs.append(BASE_DIR)
        search_dirs.append(os.getcwd())
        for d in search_dirs:
            config_path = os.path.join(d, "remote_config.py")
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    exec(content, cfg)
                    if cfg.get("REMOTE_CONTROL_TASKS"):
                        return cfg["REMOTE_CONTROL_TASKS"]
                except Exception:
                    pass
        # frozen 模块兜底
        from remote_config import REMOTE_CONTROL_TASKS
        return REMOTE_CONTROL_TASKS

    def _save_config(self):
        """将界面配置写入 remote_config.py"""
        cfg = self._load_config_values()
        vin = self.entries["vin"].get()
        vba_project = self.entries["vba_project"].get()
        vba_network = self.entries["vba_network"].get()
        vba_database = self.entries["vba_database"].get()
        report_dir = self.entries["report_dir"].get()
        capture_path = self.entries["capture_path"].get()

        config_path = os.path.join(BASE_DIR, "remote_config.py")
        # 如果配置文件不存在，生成一个默认的
        if not os.path.exists(config_path):
            self._create_default_config(config_path, vin, vba_project, vba_network, vba_database, report_dir, capture_path)
            messagebox.showinfo("成功", "配置已保存")
            return

        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 替换配置值
        import re
        content = re.sub(r'^VIN = .*', f'VIN = "{vin}"', content, flags=re.MULTILINE)
        content = re.sub(r'(?<="project": ")[^"]*', vba_project, content)
        content = re.sub(r'(?<="network": ")[^"]*', vba_network, content)
        content = re.sub(r'(?<="database": ")[^"]*', vba_database, content)
        content = re.sub(r'^BATCH_REPORT_DIR = .*', f'BATCH_REPORT_DIR = r"{report_dir}"', content, flags=re.MULTILINE)
        escaped_path = capture_path.replace("\\", "\\\\")
        content = re.sub(r'^CAPTURE_PATH = .*', f'CAPTURE_PATH = r"{escaped_path}"', content, flags=re.MULTILINE)

        with open(config_path, "w", encoding="utf-8") as f:
            f.write(content)

        messagebox.showinfo("成功", "配置已保存")

    def _create_default_config(self, path, vin, vba_project, vba_network, vba_database, report_dir, capture_path):
        """生成默认的 remote_config.py"""
        TASKS = self._tasks

        with open(path, "w", encoding="utf-8") as f:
            f.write('"""\n配置文件\n"""\n\n')
            f.write(f'# VIN码（统一配置）\nVIN = "{vin}"\n\n')
            f.write('# 登录配置\n')
            f.write(f'LOGIN_CONFIG = {{\n')
            f.write(f'    "url": r"http://jmcoperuat.jmc.com.cn/port/welcome",\n')
            f.write(f'    "username": r"hirainuat",\n')
            f.write(f'    "password": r"prewkhp5qn",\n')
            f.write(f'    "use_url_auth": True,\n')
            f.write(f'}}\n\n')
            f.write('# 远控配置\n')
            f.write('REMOTE_CONTROL_TASKS = {\n')
            for tname, tcfg in TASKS.items():
                f.write(f'    "{tname}": {{\n')
                f.write(f'        "control": {{"opType": "{tcfg["control"]["opType"]}", "ops": {tcfg["control"]["ops"]}}},\n')
                f.write(f'        "signals": [\n')
                for sig in tcfg["signals"]:
                    canid = sig["CANID"]
                    canid_hex = f"0x{canid:X}" if isinstance(canid, int) else canid
                    vals = sig["values"]
                    vals_str = ", ".join(f"0x{k:X}: {repr(v)}" if isinstance(k, int) else f"{k}: {repr(v)}" for k, v in vals.items())
                    f.write(f'            {{"CANID": {canid_hex}, "name": "{sig["name"]}", "values": {{{vals_str}}}}},\n')
                f.write(f'        ],\n')
                sub = tcfg.get("Sub-item-response", {})
                f.write(f'        "Sub-item-response": {sub},\n')
                f.write(f'    }},\n')
            f.write('}\n\n')
            f.write('# 远控请求配置\n')
            f.write('REMOTE_CONTROL_CONFIG = {\n')
            f.write(f'    "url": r"https://jmcoperuat.jmc.com.cn/port/control",\n')
            f.write(f'    "payload": {{"vin": "{vin}", "opType": "LOCK", "op": "CLOSE", "extendAttribute": {{"$": "$"}}, "caller": "hirainuat"}},\n')
            f.write('}\n\n')
            f.write('# 远控结果查询配置\n')
            f.write('API_QUERY_CONFIG_TSP = {\n')
            f.write(f'    "url": r"https://jmcoperuat.jmc.com.cn/port/getData",\n')
            f.write(f'    "payload": {{"applicationId": 4, "endDate": None, "messageType": 2, "source": "", "startDate": None, "vin": "{vin}"}},\n')
            f.write('}\n\n')
            f.write('API_QUERY_CONFIG_TBOX = {\n')
            f.write(f'    "url": r"https://jmcoperuat.jmc.com.cn/port/getData",\n')
            f.write(f'    "payload": {{"applicationId": 4, "endDate": None, "messageType": 1, "source": "", "startDate": None, "vin": "{vin}"}},\n')
            f.write('}\n\n')
            f.write('# VBA 录制配置\n')
            f.write('VBA_CONFIG = {\n')
            f.write(f'    "project": "{vba_project}",\n')
            f.write(f'    "network": "{vba_network}",\n')
            f.write(f'    "database": "{vba_database}",\n')
            f.write('}\n\n')
            f.write(f'CAPTURE_PATH = r"{capture_path}"\n\n')
            f.write(f'BATCH_REPORT_DIR = r"{report_dir}"\n')

    def _save_config_no_dialog(self):
        """保存配置到文件，不弹窗"""
        vin = self.entries["vin"].get()
        vba_project = self.entries["vba_project"].get()
        vba_network = self.entries["vba_network"].get()
        vba_database = self.entries["vba_database"].get()
        report_dir = self.entries["report_dir"].get()
        capture_path = self.entries["capture_path"].get()

        config_path = os.path.join(BASE_DIR, "remote_config.py")
        if not os.path.exists(config_path):
            self._create_default_config(config_path, vin, vba_project, vba_network, vba_database, report_dir, capture_path)
            return

        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()

        import re
        content = re.sub(r'^VIN = .*', f'VIN = "{vin}"', content, flags=re.MULTILINE)
        content = re.sub(r'(?<="project": ")[^"]*', vba_project, content)
        content = re.sub(r'(?<="network": ")[^"]*', vba_network, content)
        content = re.sub(r'(?<="database": ")[^"]*', vba_database, content)
        content = re.sub(r'^BATCH_REPORT_DIR = .*', f'BATCH_REPORT_DIR = r"{report_dir}"', content, flags=re.MULTILINE)
        # 替换 CAPTURE_PATH，转义反斜杠
        escaped_path = capture_path.replace("\\", "\\\\")
        content = re.sub(r'^CAPTURE_PATH = .*', f'CAPTURE_PATH = r"{escaped_path}"', content, flags=re.MULTILINE)

        with open(config_path, "w", encoding="utf-8") as f:
            f.write(content)

    def setup_ui(self):
        main_paned = ttk.PanedWindow(self.frame, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # ====== 左侧：配置面板 ======
        cf = ttk.LabelFrame(main_paned, text="配置", padding=10)
        main_paned.add(cf, weight=1)

        # 可滚动区域
        self._config_canvas = tk.Canvas(cf, highlightthickness=0)
        scroll = ttk.Scrollbar(cf, orient="vertical", command=self._config_canvas.yview)
        scroll_frame = ttk.Frame(self._config_canvas)
        scroll_frame.bind("<Configure>", lambda e: self._config_canvas.configure(scrollregion=self._config_canvas.bbox("all")))
        inner = self._config_canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        self._config_canvas.configure(yscrollcommand=scroll.set)
        self._config_canvas.bind("<Configure>", lambda e: self._config_canvas.itemconfig(inner, width=e.width))
        self._config_canvas.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        cf.grid_rowconfigure(0, weight=1)
        cf.grid_columnconfigure(0, weight=1)

        def _on_mousewheel(event):
            if not self._config_canvas.winfo_ismapped():
                return
            # 只处理鼠标在配置栏区域内的事件
            x, y = self._config_canvas.winfo_pointerx(), self._config_canvas.winfo_pointery()
            x1, y1, x2, y2 = self._config_canvas.winfo_rootx(), self._config_canvas.winfo_rooty(), \
                              self._config_canvas.winfo_rootx() + self._config_canvas.winfo_width(), \
                              self._config_canvas.winfo_rooty() + self._config_canvas.winfo_height()
            if x1 <= x <= x2 and y1 <= y <= y2:
                self._config_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self._config_canvas.bind_all("<MouseWheel>", _on_mousewheel, add="+")

        # ===== 配置参数 =====
        cfg = self._load_config_values()
        config_frame = ttk.LabelFrame(scroll_frame, text="基本配置", padding=8)
        config_frame.pack(fill=tk.X, pady=(0, 8))

        row = 0
        row = self._add_entry(config_frame, "VIN码", cfg["vin"], "vin", row)
        row = self._add_entry(config_frame, "VBA工程名", cfg["vba_project"], "vba_project", row)
        row = self._add_entry(config_frame, "VBA网络", cfg["vba_network"], "vba_network", row)
        row = self._add_entry(config_frame, "VBA数据库", cfg["vba_database"], "vba_database", row)
        row = self._add_folder_entry(config_frame, "报告目录", cfg["report_dir"], "report_dir", row)
        row = self._add_file_entry(config_frame, "录制路径", cfg["capture_path"], "capture_path", row)

        btn_frame = ttk.Frame(config_frame)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=5)
        ttk.Button(btn_frame, text="保存配置", command=self._save_config).pack()

        # 分组可收拉的任务列表
        ttk.Label(scroll_frame, text="选择远控项:", font=("", 10, "bold")).pack(anchor="w", pady=(0, 5))

        self.task_items = []  # [(task_name, op_name, BooleanVar), ...]
        self.group_expanded = {}  # task_name -> bool

        for task_name in self._tasks.keys():
            task = self._tasks[task_name]
            ops = list(task["control"]["ops"].keys())
            if not ops:
                continue

            group = ttk.Frame(scroll_frame)
            group.pack(fill=tk.X, pady=(3, 0))

            header = ttk.Frame(group)
            header.pack(fill=tk.X)
            arrow = ttk.Label(header, text="▼", font=("", 9))
            arrow.pack(side="left")
            ttk.Label(header, text=f"{task_name}（{len(ops)}项）", font=("", 9, "bold")).pack(side="left", padx=3)

            container = ttk.Frame(group)
            container.pack(fill=tk.X, padx=(20, 0))

            for op_name in ops:
                var = tk.BooleanVar(value=False)
                op_row = ttk.Frame(container)
                op_row.pack(fill=tk.X, pady=1)
                order_label = ttk.Label(op_row, text="", font=("", 8), foreground="gray", width=2)
                order_label.pack(side="left")
                cb = ttk.Checkbutton(
                    op_row, text=op_name, variable=var,
                    command=lambda tn=task_name, on=op_name, v=var: self._on_check(tn, on, v),
                )
                cb.pack(side="left")
                plus_btn = tk.Button(op_row, text="+", font=("", 9), width=2, bd=1,
                                      command=lambda tn=task_name, on=op_name: self._add_to_sequence(tn, on))
                plus_btn.pack(side="left", padx=(15, 3))
                minus_btn = tk.Button(op_row, text="−", font=("", 9), width=2, bd=1,
                                       command=lambda tn=task_name, on=op_name: self._remove_from_sequence(tn, on))
                minus_btn.pack(side="left", padx=3)
                self.task_items.append((task_name, op_name, var, order_label))

            self.group_expanded[task_name] = True

            # 用 partial 绑定当前变量，避免闭包陷阱
            def toggle(cont, arr, tn, e=None):
                if self.group_expanded[tn]:
                    cont.pack_forget()
                    arr.config(text="▶")
                    self.group_expanded[tn] = False
                else:
                    cont.pack(fill=tk.X, padx=(20, 0))
                    arr.config(text="▼")
                    self.group_expanded[tn] = True

            arrow.bind("<Button-1>", partial(toggle, container, arrow, task_name))

        # ====== 右侧：执行面板 ======
        rf = ttk.Frame(main_paned)
        main_paned.add(rf, weight=1)

        ef = ttk.LabelFrame(rf, text="执行", padding=10)
        ef.pack(fill=tk.X, pady=(0, 5))

        sf = ttk.Frame(ef)
        sf.pack(fill=tk.X, pady=5)
        ttk.Label(sf, text="状态:").pack(side="left")
        ttk.Label(sf, textvariable=self.run_status, font=("", 9, "bold")).pack(side="left", padx=5)
        btn_frame = ttk.Frame(sf)
        btn_frame.pack(side="right")
        ttk.Button(btn_frame, text="清除日志", command=self.clear_log).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="停止", command=self.stop_run).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="执行", command=self.run).pack(side="left", padx=2)

        # 执行次数
        loop_frame = ttk.Frame(ef)
        loop_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(loop_frame, text="执行次数:", font=("", 9, "bold")).pack(side="left")
        ttk.Spinbox(loop_frame, from_=1, to=100, textvariable=self.loop_count, width=5).pack(side="left", padx=5)

        # ====== 执行序列（可折叠）======
        seq_frame = ttk.LabelFrame(rf, text="执行序列", padding=5)
        seq_frame.pack(fill=tk.X, pady=(0, 5))

        seq_header = ttk.Frame(seq_frame)
        seq_header.pack(fill=tk.X)
        seq_arrow = ttk.Label(seq_header, text="▼", font=("", 9))
        seq_arrow.pack(side="left")
        ttk.Label(seq_header, text="执行序列", font=("", 9, "bold")).pack(side="left", padx=3)

        # 序列选择 + 保存
        seq_toolbar = ttk.Frame(seq_frame)
        seq_toolbar.pack(fill=tk.X, pady=(2, 0))
        ttk.Label(seq_toolbar, text="序列:", font=("", 8)).pack(side="left")
        self._profile_cb = ttk.Combobox(seq_toolbar, textvariable=self._current_profile,
                                         values=["自定义"], width=18, state="readonly", font=("", 8))
        self._profile_cb.pack(side="left", padx=3)
        ttk.Button(seq_toolbar, text="保存", width=5, command=self._save_seq_profile_dialog).pack(side="left", padx=1)
        ttk.Button(seq_toolbar, text="删除", width=5, command=self._delete_seq_profile).pack(side="left")
        self._current_profile.trace("w", self._on_seq_profile_changed)

        self._seq_container = ttk.Frame(seq_frame)
        self._seq_container.pack(fill=tk.X)

        # 表头
        hdr = ttk.Frame(self._seq_container)
        hdr.pack(fill=tk.X, pady=(2, 0))
        ttk.Label(hdr, text="顺序", font=("", 8, "bold"), width=5).pack(side="left")
        ttk.Label(hdr, text="远控项", font=("", 8, "bold"), width=20).pack(side="left")
        ttk.Label(hdr, text="延时(秒)", font=("", 8, "bold"), width=9).pack(side="right")
        ttk.Label(hdr, text="", width=2).pack(side="right")  # 对应 × 按钮位置

        # 首次延时行
        first_row = ttk.Frame(self._seq_container)
        first_row.pack(fill=tk.X, pady=1)
        ttk.Label(first_row, text="首次", font=("", 8), width=5).pack(side="left")
        ttk.Label(first_row, text="—", font=("", 8), width=20).pack(side="left")
        ttk.Spinbox(first_row, from_=0, to=3600, textvariable=self.first_delay, width=6).pack(side="right")

        ttk.Separator(self._seq_container, orient="horizontal").pack(fill=tk.X, pady=3)

        # 任务行容器（带滚动，固定高度）
        seq_canvas_frame = ttk.Frame(self._seq_container)
        seq_canvas_frame.pack(fill=tk.X, pady=(2, 0))
        self._seq_canvas = tk.Canvas(seq_canvas_frame, height=120, highlightthickness=0)
        seq_scroll = ttk.Scrollbar(seq_canvas_frame, orient="vertical", command=self._seq_canvas.yview)
        self._seq_task_frame = ttk.Frame(self._seq_canvas)
        self._seq_task_frame.bind("<Configure>", lambda e: self._seq_canvas.configure(scrollregion=self._seq_canvas.bbox("all")))
        self._seq_canvas_win = self._seq_canvas.create_window((0, 0), window=self._seq_task_frame, anchor="nw")
        self._seq_canvas.bind("<Configure>", lambda e: self._seq_canvas.itemconfig(self._seq_canvas_win, width=e.width))
        self._seq_canvas.configure(yscrollcommand=seq_scroll.set)
        self._seq_canvas.pack(side="left", fill=tk.X, expand=True)
        seq_scroll.pack(side="right", fill="y")
        # 鼠标滚轮（bind_all 避免 Spinbox 抢事件）
        def _on_seq_wheel(event):
            if not self._seq_canvas.winfo_ismapped():
                return
            x, y = self._seq_canvas.winfo_pointerx(), self._seq_canvas.winfo_pointery()
            x1 = self._seq_canvas.winfo_rootx()
            y1 = self._seq_canvas.winfo_rooty()
            x2 = x1 + self._seq_canvas.winfo_width()
            y2 = y1 + self._seq_canvas.winfo_height()
            if x1 <= x <= x2 and y1 <= y <= y2:
                self._seq_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self._seq_canvas.bind_all("<MouseWheel>", _on_seq_wheel, add="+")

        # 折叠切换
        def toggle_seq(cont, arr, e=None):
            if self._seq_expanded:
                cont.pack_forget()
                arr.config(text="▶")
                self._seq_expanded = False
            else:
                cont.pack(fill=tk.X)
                arr.config(text="▼")
                self._seq_expanded = True

        seq_arrow.bind("<Button-1>", partial(toggle_seq, self._seq_container, seq_arrow))

        # 初始刷新序列
        self._refresh_sequence()
        # 加载已保存的序列
        self._load_seq_profiles()

        lf = ttk.LabelFrame(rf, text="执行日志", padding=10)
        lf.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(lf, height=15, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _on_check(self, task_name, op_name, var):
        """勾选时追加一次，取消时移除所有该任务的实例"""
        if var.get():
            self._add_to_sequence(task_name, op_name)
        else:
            # 取消勾选：移除所有该任务的实例
            self._sequence = [item for item in self._sequence if not (item[0] == task_name and item[1] == op_name)]
            self._refresh_order_labels()
            self._refresh_sequence()

    def _add_to_sequence(self, task_name, op_name):
        """在序列末尾追加一个任务，延时默认取该任务上一次的值"""
        # 查找该任务上一次的值
        last_delay = 30
        for item in reversed(self._sequence):
            if item[0] == task_name and item[1] == op_name:
                last_delay = item[2].get()
                break
        self._sequence.append([task_name, op_name, tk.IntVar(value=last_delay)])
        # 确保勾选框是勾选的
        for tn, on, var, _ in self.task_items:
            if tn == task_name and on == op_name:
                var.set(True)
                break
        self._refresh_order_labels()
        self._refresh_sequence()

    def _remove_from_sequence(self, task_name, op_name):
        """移除最后一次出现的该任务"""
        for i in range(len(self._sequence) - 1, -1, -1):
            if self._sequence[i][0] == task_name and self._sequence[i][1] == op_name:
                del self._sequence[i]
                break
        # 检查是否还有该任务的实例
        has = any(item[0] == task_name and item[1] == op_name for item in self._sequence)
        if not has:
            for tn, on, var, _ in self.task_items:
                if tn == task_name and on == op_name:
                    var.set(False)
                    break
        self._refresh_order_labels()
        self._refresh_sequence()

    def _remove_seq_item(self, index):
        """按索引移除序列中的一项"""
        if 0 <= index < len(self._sequence):
            task_name, op_name = self._sequence[index][0], self._sequence[index][1]
            del self._sequence[index]
            # 检查是否还有该任务的实例
            has = any(item[0] == task_name and item[1] == op_name for item in self._sequence)
            if not has:
                for tn, on, var, _ in self.task_items:
                    if tn == task_name and on == op_name:
                        var.set(False)
                        break
            self._refresh_order_labels()
            self._refresh_sequence()

    def _refresh_order_labels(self):
        """刷新左侧序号标签，显示每个任务在序列中的出现次数"""
        for name, op, var, label in self.task_items:
            count = sum(1 for item in self._sequence if item[0] == name and item[1] == op)
            if count > 0:
                label.config(text=str(count))
            else:
                label.config(text="")

    def _get_checked_tasks(self):
        """返回序列中的所有任务（含重复）"""
        return [(item[0], item[1]) for item in self._sequence]

    def _refresh_sequence(self):
        """刷新执行序列表格"""
        if not self._seq_task_frame:
            return
        # 清除旧行
        for w in self._seq_task_frame.winfo_children():
            w.destroy()
        for i, item in enumerate(self._sequence):
            task_name, op_name, delay_var = item
            row = ttk.Frame(self._seq_task_frame)
            row.pack(fill=tk.X, pady=1)
            ttk.Label(row, text=str(i + 1), font=("", 8), width=5).pack(side="left")
            ttk.Label(row, text=f"{task_name}→{op_name}", font=("", 8), width=20).pack(side="left")
            tk.Button(row, text="×", font=("", 8), width=2, bd=1,
                       command=lambda idx=i: self._remove_seq_item(idx)).pack(side="right", padx=(5, 0))
            ttk.Spinbox(row, from_=0, to=3600, textvariable=delay_var, width=6).pack(side="right")

    def _get_seq_profiles_path(self):
        return os.path.join(BASE_DIR, "sequences.json")

    def _load_seq_profiles(self):
        """从文件加载保存的序列"""
        path = self._get_seq_profiles_path()
        if not os.path.exists(path):
            return
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                self._seq_profiles = json.load(f)
            names = ["自定义"] + list(self._seq_profiles.keys())
            self._profile_cb["values"] = names
        except Exception:
            self._seq_profiles = {}

    def _save_seq_profiles(self):
        """保存序列到文件"""
        import json
        path = self._get_seq_profiles_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._seq_profiles, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"[!] 序列保存失败: {e}")

    def _save_seq_profile_dialog(self):
        """弹出对话框，保存当前序列"""
        from tkinter.simpledialog import askstring
        current_name = self._current_profile.get()
        default_name = "" if current_name == "自定义" else current_name
        name = askstring("保存序列", "请输入序列名称：", initialvalue=default_name, parent=self.parent)
        if not name:
            return
        if not self._sequence:
            messagebox.showwarning("提示", "序列为空")
            return
        items = [{"task": item[0], "op": item[1], "delay": item[2].get()} for item in self._sequence]
        self._seq_profiles[name] = {
            "first_delay": self.first_delay.get(),
            "items": items,
        }
        # 如果改名了，删掉旧名称
        if current_name != "自定义" and name != current_name:
            del self._seq_profiles[current_name]
        self._save_seq_profiles()
        # 刷新下拉框
        names = ["自定义"] + list(self._seq_profiles.keys())
        self._profile_cb["values"] = names
        # 只有名称变了才触发 trace，避免覆盖自定义状态
        if self._current_profile.get() != name:
            self._current_profile.set(name)
        self.log(f"[OK] 序列 '{name}' 已保存（{len(items)} 项）")

    def _delete_seq_profile(self):
        """删除当前选中的序列"""
        name = self._current_profile.get()
        if name == "自定义" or name not in self._seq_profiles:
            messagebox.showwarning("提示", "请先选择一个要删除的序列")
            return
        if not messagebox.askyesno("确认删除", f"确定删除序列 '{name}'？", parent=self.parent):
            return
        del self._seq_profiles[name]
        self._save_seq_profiles()
        # 刷新下拉框
        names = ["自定义"] + list(self._seq_profiles.keys())
        self._profile_cb["values"] = names
        self._current_profile.set("自定义")
        self.log(f"[OK] 序列 '{name}' 已删除")

    def _save_custom_state(self):
        """保存当前自定义模式的状态"""
        self._custom_state = {
            "first_delay": self.first_delay.get(),
            "sequence": [[item[0], item[1], item[2].get()] for item in self._sequence],
        }

    def _restore_custom_state(self):
        """恢复自定义模式的状态"""
        self._sequence.clear()
        for _, _, var, _ in self.task_items:
            var.set(False)
        if not self._custom_state or not self._custom_state.get("sequence"):
            self.first_delay.set(30)
            self._refresh_order_labels()
            self._refresh_sequence()
            return
        self.first_delay.set(self._custom_state["first_delay"])
        for item_data in self._custom_state["sequence"]:
            task_name, op_name, delay = item_data
            self._sequence.append([task_name, op_name, tk.IntVar(value=delay)])
            for tn, on, var, _ in self.task_items:
                if tn == task_name and on == op_name:
                    var.set(True)
                    break
        self._refresh_order_labels()
        self._refresh_sequence()
        self._refresh_order_labels()
        self._refresh_sequence()

    def _on_seq_profile_changed(self, *args):
        """下拉框选择变化时，应用序列"""
        name = self._current_profile.get()
        if name != "自定义":
            # 只有从自定义切过来时才保存自定义状态
            if getattr(self, '_prev_profile', None) == "自定义":
                self._save_custom_state()
            self._apply_seq_profile(name)
        else:
            self._restore_custom_state()
        self._prev_profile = name

    def _apply_seq_profile(self, name):
        """应用保存的序列：重建 _sequence"""
        profile = self._seq_profiles.get(name)
        if not profile:
            return
        self._sequence.clear()
        self.first_delay.set(profile.get("first_delay", 30))
        # 取消所有勾选
        for _, _, var, _ in self.task_items:
            var.set(False)
        for item in profile.get("items", []):
            task_name, op_name, delay = item["task"], item["op"], item.get("delay", 30)
            self._sequence.append([task_name, op_name, tk.IntVar(value=delay)])
            for tn, on, var, _ in self.task_items:
                if tn == task_name and on == op_name:
                    var.set(True)
                    break
        self._refresh_order_labels()
        self._refresh_sequence()
        self.log(f"[OK] 已加载序列 '{name}'")

    def log(self, msg):
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.parent.update()

    def clear_log(self):
        self.log_text.delete(1.0, tk.END)

    def run(self):
        self._stop_flag.clear()
        threading.Thread(target=self._run, daemon=True).start()

    def stop_run(self):
        self._stop_flag.set()
        self.log("[!] 正在停止...")

    def _wait_with_stop(self, seconds, msg="等待"):
        """等待指定秒数，期间检测停止标志，返回 True 继续执行"""
        for i in range(seconds):
            if self._stop_flag.is_set():
                self.log(f"  [!] 已停止")
                return False
            if (i + 1) % 5 == 0:
                self.log(f"  {msg} {i+1}/{seconds}")
            time.sleep(1)
        return True

    def _run(self):
        self.run_status.set("执行中...")
        self.log("=" * 60)
        self.log("执行远控流程")
        self.log("=" * 60)

        # 保存界面配置到文件，直接从文件读取配置值
        try:
            self._save_config_no_dialog()
            # 直接从文件读取配置，避免 frozen 模块缓存问题
            cfg = {}
            config_path = os.path.join(BASE_DIR, "remote_config.py")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    exec(f.read(), cfg)
            self._capture_path = cfg.get("CAPTURE_PATH", os.path.join(BASE_DIR, "capture.mf4"))
            self._report_dir = cfg.get("BATCH_REPORT_DIR", os.path.join(BASE_DIR, "batch_reports"))
        except Exception as e:
            self.log(f"[!] 配置保存失败: {e}")

        checked = self._get_checked_tasks()
        if len(self._sequence) < 1:
            self.log("[X] 序列为空，请添加远控项")
            self.run_status.set("❌ 失败")
            return

        loop = self.loop_count.get()
        seq_len = len(self._sequence)
        total = seq_len * loop
        self.log(f"序列 {seq_len} 项，执行 {loop} 次，共 {total} 项")
        for item in self._sequence:
            self.log(f"  - {item[0]} → {item[1]}（延时 {item[2].get()} 秒）")
        self.log(f"  首次延时: {self.first_delay.get()} 秒")

        # 登录一次
        self.log("\n[登录] 登录...")
        success, _ = self.api.login_and_get_cookies()
        if not success:
            self.log("[X] 登录失败，批量执行终止")
            self.run_status.set("❌ 失败")
            return

        # 构建循环执行列表（含重复）
        items = []
        for _ in range(loop):
            items.extend(self._sequence)
        for idx, seq_item in enumerate(items):
            if self._stop_flag.is_set():
                self.log("[!] 执行被中断")
                break
            task_name, op_name, delay_var = seq_item
            # 计算当前轮次
            current_round = idx // seq_len + 1
            is_first_in_round = idx % seq_len == 0

            # 每轮开始前等待首次延时
            if is_first_in_round:
                first_delay = self.first_delay.get()
                if first_delay > 0:
                    self.log(f"\n⌛ 等待 {first_delay} 秒后开始第{current_round}轮...")
                    if not self._wait_with_stop(first_delay, "首次延时"):
                        break

            self.log("\n" + "-" * 50)
            self.log(f"[第{current_round}轮 {idx+1}/{total}] {task_name} → {op_name}")
            self.log("-" * 50)

            task = self._tasks.get(task_name)
            if not task:
                self.log("  [X] 未知任务，跳过")
                continue

            if op_name not in task["control"]["ops"]:
                self.log(f"  [X] 操作 '{op_name}' 无效，跳过")
                continue
            op_value = task["control"]["ops"][op_name]
            self.log(f"  操作: {op_name} ({op_value})")

            # 执行单个任务
            result = self._execute_single_task(task, task_name, op_name, op_value, current_round)
            self._batch_results.append(result)

            # 任务后延时
            if idx < len(items) - 1:
                delay = delay_var.get()
                if delay > 0:
                    self.log(f"\n⌛ 等待 {delay} 秒后执行下一个任务...")
                    if not self._wait_with_stop(delay, "任务延时"):
                        break

        self.log("\n" + "=" * 60)
        # 打印远控状态汇总
        pass_count = sum(1 for r in self._batch_results if r.get("status") == "pass")
        fail_count = sum(1 for r in self._batch_results if r.get("status") == "fail")
        nodata_count = sum(1 for r in self._batch_results if r.get("status") == "nodata")
        total = len(self._batch_results)
        self.log(f"远控汇总: ✅ PASS {pass_count}  ❌ FAIL {fail_count}  ⚠️ NODATA {nodata_count}  共 {total} 项")
        self.log("=" * 60)
        if self._stop_flag.is_set():
            self.log("[!] 执行已中断（部分完成）")
            self.run_status.set("⏹ 已中断")
        else:
            self.log("[OK] 执行完成")
            self.run_status.set("✅ 完成")

        # 生成批量报告
        self._generate_batch_report()

    def _execute_single_task(self, task, task_name, op_name, op_value, current_round=1):
        """执行单个远控任务，返回结果数据"""
        # 运行时从文件读取最新配置
        runtime_cfg = {}
        try:
            config_path = os.path.join(BASE_DIR, "remote_config.py")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    exec(f.read(), runtime_cfg)
        except Exception:
            pass
        rc_cfg = runtime_cfg.get("REMOTE_CONTROL_CONFIG", REMOTE_CONTROL_CONFIG)
        tsp_cfg = runtime_cfg.get("API_QUERY_CONFIG_TSP", API_QUERY_CONFIG_TSP)
        tbox_cfg = runtime_cfg.get("API_QUERY_CONFIG_TBOX", API_QUERY_CONFIG_TBOX)
        capture_path = runtime_cfg.get("CAPTURE_PATH", getattr(self, '_capture_path', CAPTURE_PATH))
        T1 = time.time()
        result = {
            "task_name": task_name,
            "op_name": op_name,
            "round": current_round,
            "tsp": None,
            "tbox": None,
            "signals": [],
            "status": "nodata",
        }

        # 1. 开始录制
        self.log("\n[步骤1] 开始录制报文...")
        can_ids = list(set(sig["CANID"] for sig in task["signals"]))
        task_id = self.api.start_capture(can_ids)
        if not task_id:
            self.log("  [X] 录制启动失败，跳过此任务")
            return result

        time.sleep(1)
        # 2. 发起远控
        self.log("\n[步骤2] 发起远控请求...")
        payload = rc_cfg["payload"].copy()
        payload["opType"] = task["control"]["opType"]
        payload["op"] = op_value
        control_result = self.api.send_remote_control(
            api_url=rc_cfg["url"],
            request_data=payload,
        )
        if not control_result:
            self.log("  [X] 远控发起失败，跳过此任务")
            return result

        # 3. 等待录制
        self.log("\n[步骤3] 等待录制 30 秒...")
        if not self._wait_with_stop(30, "录制"):
            self.log("  [X] 录制未完成，跳过此任务")
            return result
        self.log("  [OK] 录制完成")

        # 4. 停止录制
        self.log("\n[步骤4] 停止录制...")
        self.api.stop_capture(task_id)

        # 5. 查询 TSP
        self.log("\n[步骤5] 查询 TSP 响应结果...")
        tsp_result = self.api.query_by_api(
            api_url=tsp_cfg.get("url"),
            request_data=tsp_cfg.get("payload", {}).copy(),
        )
        tsp_send_ts = 0
        tsp_parsed = None
        if tsp_result:
            try:
                tsp_send_ts = int(tsp_result.get("result", [{}])[0].get("sendTimestamp", 0)) / 1000
            except Exception:
                pass
            tsp_parsed = self.api.parse_tsp_result(tsp_result)
        self._check_and_print_result("TSP", tsp_parsed, T1, tsp_send_ts)
        # 时间差不在范围内，视为未查询到数据
        diff = tsp_send_ts - T1
        result["tsp"] = tsp_parsed if tsp_parsed and 0 <= diff <= 30 else None

        # 6. 查询 TBOX
        self.log("\n[步骤6] 查询 TBOX 上报结果...")
        tbox_result = self.api.query_by_api(
            api_url=tbox_cfg.get("url"),
            request_data=tbox_cfg.get("payload", {}).copy(),
        )
        tbox_send_ts = 0
        tbox_parsed = None
        if tbox_result:
            try:
                tbox_send_ts = int(tbox_result.get("result", [{}])[0].get("sendTimestamp", 0)) / 1000
            except Exception:
                pass
            tbox_parsed = self.api.parse_tbox_result(tbox_result)
        self._check_and_print_result("TBOX", tbox_parsed, T1, tbox_send_ts)
        diff = tbox_send_ts - T1
        result["tbox"] = tbox_parsed if tbox_parsed and 0 <= diff <= 30 else None
        # 远控状态：pass / fail / nodata
        if result["tbox"]:
            error_code = result["tbox"].get("errorCode", "N/A")
            # 子项比对：从 responseData 中提取子项参数和子项编码，分别与配置比对
            sub_item_match = False
            sub_item = task.get("Sub-item-response")
            if sub_item:
                response_data = result["tbox"].get("responseData", {})
                expected_param = sub_item["子项参数"]
                expected_code = sub_item["子项编码"]
                # responseData 格式: {子项编码: 子项参数, ...}
                actual_code = None
                actual_param = None
                for k, v in response_data.items():
                    actual_code = k
                    actual_param = v
                    break  # 取第一对
                if actual_code is not None and str(actual_code) == str(expected_code) and str(actual_param) == str(expected_param):
                    sub_item_match = True
                    self.log(f"  [OK] 子项比对: 编码={actual_code}, 参数={actual_param} ✓")
                else:
                    self.log(f"  [X] 子项比对: 期望(编码={expected_code}, 参数={expected_param}), "
                             f"实际(编码={actual_code}, 参数={actual_param})")
            else:
                # 未配置子项比对，默认通过
                sub_item_match = True

            if str(error_code) == "0" and sub_item_match:
                result["status"] = "pass"
            else:
                result["status"] = "fail"
        else:
            result["status"] = "nodata"

        # 7. 解析 MF4
        self.log("\n[步骤7] 解析 总线报文 快发三帧...")
        for sig in task["signals"]:
            self.log(f"  --- 信号: {sig['name']} ---")
            sig_result = self.api.parse_mf4_signal(capture_path, sig["name"], sig["values"])
            if sig_result:
                self.log(f"  基准值: {sig_result['base_val']} → {sig_result['base_meaning']}")
                for i, f in enumerate(sig_result["frames"]):
                    self.log(f"  帧 {i+1}: {f['value']} → {f['meaning']}")
                self.log(f"  周期: {sig_result['period_ms']}ms")
            else:
                self.log("  请求/响应未发出")
            result["signals"].append({
                "name": sig["name"],
                "result": sig_result,
            })

        # 打印远控状态
        status = result["status"]
        sub_item = task.get("Sub-item-response")
        if status == "pass":
            error_code = result["tbox"].get("errorCode", "N/A") if result["tbox"] else "?"
            self.log(f"\n  ✅ PASS（错误码: {error_code}）")
        elif status == "fail":
            error_code = result["tbox"].get("errorCode", "N/A") if result["tbox"] else "?"
            reasons = []
            if str(error_code) != "0":
                reasons.append(f"错误码={error_code}")
            if sub_item:
                response_data = result["tbox"].get("responseData", {}) if result["tbox"] else {}
                expected_param = sub_item["子项参数"]
                expected_code = sub_item["子项编码"]
                actual_code = None
                actual_param = None
                for k, v in response_data.items():
                    actual_code = k
                    actual_param = v
                    break
                if str(actual_code) != str(expected_code):
                    reasons.append(f"子项编码不匹配: 期望={expected_code}, 实际={actual_code}")
                if str(actual_param) != str(expected_param):
                    reasons.append(f"子项参数不匹配: 期望={expected_param}, 实际={actual_param}")
            reason_str = "; ".join(reasons) if reasons else ""
            self.log(f"\n  ❌ FAIL（{reason_str}）")
        else:
            self.log("\n  ⚠️ NODATA（未查询到TBOX结果）")

        return result

    def _check_and_print_result(self, label, parsed, T1, send_ts):
        """检查时间差并打印"""
        if not parsed:
            self.log(f"  [X] {label} 解析失败")
            return
        diff = send_ts - T1
        self.log(f"  {label} 时间戳: {parsed.get('timestamp', 'N/A')}（与远控时间差: {diff:.1f}s）")
        if diff < 0 or diff > 30:
            self.log(f"  [!] {label} 未查询到数据（时间差 {diff:.1f}s，远控前或超30s）")
        else:
            self.log(f"  [OK] {label} 查询到数据")
            if label == "TSP":
                for param, code in parsed.get("controlCommands", {}).items():
                    self.log(f"  子项参数：{param} 子项编码: {code}")
            else:
                self.log(f"  错误码: {parsed.get('errorCode', 'N/A')}")
                for code, param in parsed.get("responseData", {}).items():
                    self.log(f"  子项编码：{code} 子项参数: {param}")

    def _generate_batch_report(self):
        """生成批量执行结果的 HTML 报告"""
        if not self._batch_results:
            return

        import datetime

        output_dir = getattr(self, '_report_dir', BATCH_REPORT_DIR)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(output_dir, f"batch_report_{timestamp}.html")

        cards = ""
        pass_count = 0
        fail_count = 0
        nodata_count = 0
        for r in self._batch_results:
            st = r.get("status", "nodata")
            if st == "pass":
                pass_count += 1
            elif st == "fail":
                fail_count += 1
            else:
                nodata_count += 1

        all_rounds = [r2.get("round", 1) for r2 in self._batch_results]
        max_round = max(all_rounds)

        round_idx = 0  # 每轮独立计数
        for idx, r in enumerate(self._batch_results, 1):
            st = r.get("status", "nodata")
            round_num = r.get("round", 1)
            if idx > 1 and round_num != self._batch_results[idx-2].get("round", 1):
                round_idx = 0  # 重置计数
                cards += f"""
        <div class="round-sep">第 {round_num} 轮</div>"""
            elif max_round > 1 and idx == 1:
                cards += f"""
        <div class="round-sep">第 1 轮</div>"""
            round_idx += 1
            st = r.get("status", "nodata")
            if st == "pass":
                header_color = "#52c41a"
                badge = "PASS"
            elif st == "fail":
                header_color = "#ff4d4f"
                badge = "FAIL"
            else:
                header_color = "#faad14"
                badge = "NODATA"
            # 多轮才显示轮次
            round_label = f"第{round_num}轮 " if max_round > 1 else ""
            cards += f"""
        <div class="card">
            <div class="card-title" style="background:{header_color}" onclick="toggleBody(this)">
                <span class="arrow">▶</span> [{round_idx}] {r['task_name']} → {r['op_name']}  <span class="badge">{badge}</span>
            </div>
            <div class="card-body" style="display:none">"""

            # TSP
            tsp = r.get("tsp")
            cards += f"""
                <div class="col">
                    <div class="col-title">TSP 结果</div>"""
            if tsp:
                cards += f"""
                    <div class="info-row"><span class="label">时间戳</span><span class="val">{tsp.get('timestamp', 'N/A')}</span></div>"""
                for param, code in tsp.get("controlCommands", {}).items():
                    cards += f"""
                    <div class="info-row"><span class="label">子项参数</span><span class="val">{param}</span></div>
                    <div class="info-row"><span class="label">子项编码</span><span class="val">{code}</span></div>"""
            else:
                cards += f"""
                    <div class="no-data">未查询到数据</div>"""
            cards += f"""
                </div>"""

            # TBOX
            tbox = r.get("tbox")
            cards += f"""
                <div class="col">
                    <div class="col-title">TBOX 结果</div>"""
            if tbox:
                cards += f"""
                    <div class="info-row"><span class="label">时间戳</span><span class="val">{tbox.get('timestamp', 'N/A')}</span></div>
                    <div class="info-row"><span class="label">错误码</span><span class="val">{tbox.get('errorCode', 'N/A')}</span></div>"""
                for code, param in tbox.get("responseData", {}).items():
                    cards += f"""
                    <div class="info-row"><span class="label">子项编码</span><span class="val">{code}</span></div>
                    <div class="info-row"><span class="label">子项参数</span><span class="val">{param}</span></div>"""
            else:
                cards += f"""
                    <div class="no-data">未查询到数据</div>"""
            cards += f"""
                </div>"""

            # 信号
            cards += f"""
                <div class="col">
                    <div class="col-title">信号解析</div>"""
            for sig in r.get("signals", []):
                sig_name = sig["name"]
                sig_result = sig.get("result")
                if sig_result:
                    cards += f"""
                    <div class="sig-block">
                        <div class="sig-name">{sig_name}</div>
                        <div class="info-row"><span class="label">基准值</span><span class="val">{sig_result['base_val']} → {sig_result['base_meaning']}</span></div>
                        <div class="info-row"><span class="label">快发帧</span></div>
                        <div class="frame-row">"""
                    for i, f in enumerate(sig_result["frames"]):
                        cards += f"""<span class="frame">帧{i+1}: {f['value']}→{f['meaning']}</span>"""
                    cards += f"""
                        </div>
                        <div class="info-row"><span class="label">周期</span><span class="val">{sig_result['period_ms']}ms</span></div>
                    </div>"""
                else:
                    cards += f"""
                    <div class="sig-block">
                        <div class="sig-name">{sig_name}</div>
                        <div class="no-data">TBOX请求未发出</div>
                    </div>"""
            cards += f"""
                </div>
            </div>
        </div>"""

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>批量远控测试报告</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: "Microsoft YaHei", Arial, sans-serif; background: #f0f2f5; padding: 20px; }}
.container {{ max-width: 1400px; margin: 0 auto; }}
h1 {{ text-align: center; color: #333; margin-bottom: 5px; }}
.subtitle {{ text-align: center; color: #999; font-size: 13px; margin-bottom: 20px; }}
.summary {{ display: flex; justify-content: center; gap: 30px; margin-bottom: 20px; }}
.summary-box {{ padding: 8px 20px; border-radius: 6px; text-align: center; color: white; font-size: 14px; font-weight: bold; }}
.summary-pass {{ background: #52c41a; }}
.summary-fail {{ background: #ff4d4f; }}
.summary-total {{ background: #1890ff; }}
.summary-nodata {{ background: #faad14; }}
.card {{ background: white; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); margin-bottom: 6px; overflow: hidden; }}
.arrow {{ font-size: 11px; margin-right: 4px; color: rgba(255,255,255,0.7); }}
.card-title {{ color: white; padding: 6px 12px; font-size: 13px; font-weight: bold; cursor: pointer; }}
.round-sep {{ text-align: center; padding: 4px; font-size: 13px; font-weight: bold; color: #666; background: #f5f5f5; border-radius: 4px; margin: 4px 0; }}
.badge {{ display: inline-block; background: rgba(255,255,255,0.25); border-radius: 3px; padding: 1px 8px; font-size: 11px; float: right; }}
.card-body {{ display: flex; gap: 0; font-size: 12px; }}
.col {{ flex: 1; padding: 6px 10px; border-right: 1px solid #f0f0f0; min-width: 0; }}
.col:last-child {{ border-right: none; }}
.col-title {{ font-size: 12px; font-weight: bold; color: #1565c0; margin-bottom: 4px; padding-bottom: 2px; border-bottom: 1px solid #e3f2fd; }}
.info-row {{ padding: 2px 0 2px 4px; font-size: 12px; }}
.label {{ color: #888; font-weight: bold; }}
.label::after {{ content: "："; }}
.val {{ color: #333; }}
.no-data {{ color: #999; font-style: italic; font-size: 12px; }}
.sig-block {{ background: #f8f9fa; border-radius: 4px; padding: 4px 6px; margin: 3px 0; }}
.sig-name {{ font-weight: bold; color: #333; font-size: 12px; margin-bottom: 2px; }}
.frame-row {{ display: flex; flex-wrap: wrap; gap: 3px; margin: 2px 0; }}
.frame {{ display: inline-block; background: #e3f2fd; border-radius: 3px; padding: 1px 6px; font-size: 11px; }}
.footer {{ text-align: center; color: #999; font-size: 11px; margin-top: 8px; }}
</style>
</head>
<body>
<div class="container">
<h1>批量远控测试报告</h1>
<div class="subtitle">生成时间: {timestamp}</div>
<div class="summary">
    <div class="summary-box summary-total">总执行: {len(self._batch_results)}</div>
    <div class="summary-box summary-pass">PASS: {pass_count}</div>
    <div class="summary-box summary-fail">FAIL: {fail_count}</div>
    <div class="summary-box summary-nodata">NODATA: {nodata_count}</div>
</div>
{cards}
<div class="footer">报告路径: {report_path}</div>
</div>
<script>
function toggleBody(title) {{
    var body = title.nextElementSibling;
    var arrow = title.querySelector('.arrow');
    if (body.style.display === 'none') {{
        body.style.display = 'flex';
        arrow.textContent = '▼';
    }} else {{
        body.style.display = 'none';
        arrow.textContent = '▶';
    }}
}}
</script>
</body>
</html>"""

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html)

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html)

        self.log(f"\n[OK] 批量报告已生成: {report_path}")
        self._batch_results = []


def main(parent=None):
    if parent is None:
        root = tk.Tk()
        root.title("远控测试工具")
        root.geometry("850x600")
        root.minsize(750, 500)
        app = RemoteControlApp(root)
        root.mainloop()
    else:
        app = RemoteControlApp(parent)
    return app


if __name__ == "__main__":
    main()
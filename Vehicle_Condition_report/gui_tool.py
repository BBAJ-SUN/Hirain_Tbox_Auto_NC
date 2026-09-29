"""
车辆信号自动化测试工具 - 图形界面
配置 config.py 并执行 query_signal_report.py
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import sys
import os
import threading
import io
import time

# 路径处理
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(BASE_DIR, "config.py")

# 默认配置
DEFAULT_CONFIG = {
    "LOGIN_CONFIG": {
        "url": "http://jmcoperuat.jmc.com.cn/port/welcome",
        "username": "hirainuat",
        "password": "prewkhp5qn",
        "use_url_auth": True,
    },
    "API_QUERY_CONFIG": {
        "url": "https://jmcoperuat.jmc.com.cn/port/getData",
        "payload": {
            "applicationId": 3,
            "endDate": None,
            "messageType": 7,
            "source": "",
            "startDate": None,
            "vin": "LA9AEPG2XHHLJK001",
        },
    },
    "SIGNAL_LIST_PATH": r"D:\PROJECT\E326\JMC-OTA-E326信号列表-20260605改.xlsx",
    "SIGNAL_SHEET_NAMES": ["基础车况信号平台化", "新能源法规（新）"],
    "GUOBIAO_SHEET_NAMES": ["基础车况信号平台化", "新能源法规（新）"],
    "VBA_PROJECT": "ELD",
    "OUTPUT_DIR": r"D:\实车半自动化\Test_AUTO\query_results",
}


class ToolApp:
    def __init__(self, parent):
        self.parent = parent
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill=tk.BOTH, expand=True)

        self.config_data = {}
        self.run_status = tk.StringVar(value="待执行")
        self.vehicle_delay = tk.IntVar(value=30)

        self.load_config()
        self.setup_ui()

    def load_config(self):
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    exec(f.read(), self.config_data)
            else:
                self.config_data = DEFAULT_CONFIG.copy()
        except Exception:
            self.config_data = DEFAULT_CONFIG.copy()

    def save_config(self):
        try:
            self._write_config()
            messagebox.showinfo("成功", "配置已保存")
            self.config_data = {}
            self.load_config()
        except Exception as e:
            messagebox.showerror("错误", f"保存失败:\n{str(e)}")

    def _write_config(self):
        vin = self.entries["API_QUERY_CONFIG.payload.vin"].get().strip()
        login = {
            "url": self.entries["LOGIN_CONFIG.url"].get(),
            "username": self.entries["LOGIN_CONFIG.username"].get(),
            "password": self.entries["LOGIN_CONFIG.password"].get(),
            "use_url_auth": True,
        }
        api = {
            "url": self.entries["API_QUERY_CONFIG.url"].get(),
            "payload": {
                "applicationId": int(self.entries["API_QUERY_CONFIG.payload.applicationId"].get()),
                "endDate": None,
                "messageType": int(self.entries["API_QUERY_CONFIG.payload.messageType"].get()),
                "source": "",
                "startDate": None,
                "vin": vin,
            }
        }
        signal_list_path = self.entries["SIGNAL_LIST_PATH"].get()
        sheet_names = [s.strip() for s in self.entries["SIGNAL_SHEET_NAMES"].get().split(",") if s.strip()]
        vba_sheet_names = [s.strip() for s in self.entries["GUOBIAO_SHEET_NAMES"].get().split(",") if s.strip()]
        vba_project = self.entries["VBA_PROJECT"].get()
        output_dir = self.entries["OUTPUT_DIR"].get()

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write('"""\n配置文件\n"""\n\n')
            f.write("# 登录配置\n")
            self._write_dict(f, "LOGIN_CONFIG", login)
            f.write("\n# API查询配置\n")
            self._write_dict(f, "API_QUERY_CONFIG", api)
            f.write("\n# 车况查询配置\n")
            vc_control = self.config_data.get("Vehicle_Condition_Control", {})
            vc_control_payload = vc_control.get("payload", {}).copy()
            vc_control_payload["vin"] = vin
            vc_control = {"url": vc_control.get("url", "https://jmcoperuat.jmc.com.cn/port/control"), "payload": vc_control_payload}
            self._write_dict(f, "Vehicle_Condition_Control", vc_control)
            vc_query = self.config_data.get("Vehicle_Condition_QUERY", {})
            vc_query_payload = vc_query.get("payload", {}).copy()
            vc_query_payload["vin"] = vin
            vc_query = {"url": vc_query.get("url", "https://jmcoperuat.jmc.com.cn/port/getData"), "payload": vc_query_payload}
            self._write_dict(f, "Vehicle_Condition_QUERY", vc_query)
            f.write(f"\n# 信号列表路径\nSIGNAL_LIST_PATH = {repr(signal_list_path)}\n\n")
            f.write(f"# Sheet名称\nSIGNAL_SHEET_NAMES = {repr(sheet_names)}\n\n")
            f.write(f"# VBA读取的国标Sheet名称\nGUOBIAO_SHEET_NAMES = {repr(vba_sheet_names)}\n\n")
            f.write(f"# VBA工程名\nVBA_PROJECT = {repr(vba_project)}\n\n")
            f.write(f"# 输出目录\nOUTPUT_DIR = {repr(output_dir)}\n")

    def _write_dict(self, f, name, data):
        f.write(f"{name} = {{\n")
        for key, val in data.items():
            if isinstance(val, str):
                escaped = val.replace("\\", "\\\\")
                f.write(f'    "{key}": r"{escaped}",\n')
            elif val is None:
                f.write(f'    "{key}": None,\n')
            else:
                f.write(f'    "{key}": {repr(val)},\n')
        f.write("}\n")

    def setup_ui(self):
        main_paned = ttk.PanedWindow(self.frame, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        cf = ttk.LabelFrame(main_paned, text="配置", padding=10)
        main_paned.add(cf, weight=1)

        canvas = tk.Canvas(cf)
        self._config_canvas = canvas
        scroll = ttk.Scrollbar(cf, orient="vertical", command=canvas.yview)
        sf = ttk.Frame(canvas)
        sf.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=sf, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill=tk.BOTH, expand=True)
        scroll.pack(side="right", fill="y")

        def _on_mousewheel(event):
            if not self._config_canvas.winfo_ismapped():
                return
            # 只在鼠标位于配置栏区域内时滚动
            x, y = self._config_canvas.winfo_pointerx(), self._config_canvas.winfo_pointery()
            x1, y1, x2, y2 = self._config_canvas.winfo_rootx(), self._config_canvas.winfo_rooty(), \
                              self._config_canvas.winfo_rootx() + self._config_canvas.winfo_width(), \
                              self._config_canvas.winfo_rooty() + self._config_canvas.winfo_height()
            if x1 <= x <= x2 and y1 <= y <= y2:
                self._config_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self._config_canvas.bind_all("<MouseWheel>", _on_mousewheel, add="+")

        row = 0
        self.entries = {}

        ttk.Label(sf, text="【登录配置】", font=("", 10, "bold")).grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 5))
        row += 1
        login = self.config_data.get("LOGIN_CONFIG", {})
        for key, label in [("url", "登录地址"), ("username", "用户名"), ("password", "密码")]:
            row = self._add_entry(sf, label, login.get(key, ""), f"LOGIN_CONFIG.{key}", row)

        ttk.Label(sf, text="【API查询配置】", font=("", 10, "bold")).grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 5))
        row += 1
        api = self.config_data.get("API_QUERY_CONFIG", {})
        row = self._add_entry(sf, "API地址", api.get("url", ""), "API_QUERY_CONFIG.url", row)
        payload = api.get("payload", {})
        for key, label in [("applicationId", "应用ID"), ("messageType", "消息类型"), ("vin", "VIN码")]:
            row = self._add_entry(sf, label, str(payload.get(key, "")), f"API_QUERY_CONFIG.payload.{key}", row)

        ttk.Label(sf, text="【信号列表】", font=("", 10, "bold")).grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 5))
        row += 1
        row = self._add_file_entry(sf, "信号列表路径", self.config_data.get("SIGNAL_LIST_PATH", ""), "SIGNAL_LIST_PATH", row)
        row = self._add_entry(sf, "车况Sheet(逗号分隔)", ", ".join(self.config_data.get("SIGNAL_SHEET_NAMES", [])), "SIGNAL_SHEET_NAMES", row)
        row = self._add_entry(sf, "国标Sheet(逗号分隔)", ", ".join(self.config_data.get("GUOBIAO_SHEET_NAMES", [])), "GUOBIAO_SHEET_NAMES", row)

        ttk.Label(sf, text="【VBA配置】", font=("", 10, "bold")).grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 5))
        row += 1
        row = self._add_entry(sf, "工程名", self.config_data.get("VBA_PROJECT", "ELD"), "VBA_PROJECT", row)

        ttk.Label(sf, text="【输出目录】", font=("", 10, "bold")).grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 5))
        row += 1
        row = self._add_folder_entry(sf, "报告输出目录", self.config_data.get("OUTPUT_DIR", ""), "OUTPUT_DIR", row)

        ttk.Button(sf, text="保存配置", command=self.save_config).grid(row=row, column=0, columnspan=2, pady=20)
        sf.columnconfigure(1, weight=1)

        rf = ttk.Frame(main_paned)
        main_paned.add(rf, weight=1)

        ef = ttk.LabelFrame(rf, text="执行", padding=10)
        ef.pack(fill=tk.X, pady=(0, 10))

        # 状态行
        status_frame = ttk.Frame(ef)
        status_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(status_frame, text="状态:").pack(side="left")
        ttk.Label(status_frame, textvariable=self.run_status, font=("", 9, "bold")).pack(side="left", padx=5)
        ttk.Button(status_frame, text="清除日志", command=self.clear_log, width=8).pack(side="right", padx=3)

        # 功能按钮行
        btn_frame = ttk.Frame(ef)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="车况比对", command=self.run_script, width=16).pack(side="left", padx=3)
        ttk.Button(btn_frame, text="国标总线值读取", command=self.run_vba, width=16).pack(side="left", padx=3)
        ttk.Separator(btn_frame, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(btn_frame, text="车况查询", command=self.run_vehicle_condition, width=12).pack(side="left", padx=3)
        ttk.Label(btn_frame, text="延时:", font=("", 8)).pack(side="left", padx=(5, 0))
        ttk.Spinbox(btn_frame, from_=0, to=300, textvariable=self.vehicle_delay, width=5).pack(side="left", padx=2)

        lf = ttk.LabelFrame(rf, text="执行日志", padding=10)
        lf.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(lf, height=15, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _add_entry(self, parent, label, default, key, row):
        ttk.Label(parent, text=f"{label}:").grid(row=row, column=0, sticky="w", pady=2)
        e = ttk.Entry(parent, width=35)
        e.insert(0, default)
        e.grid(row=row, column=1, sticky="ew", pady=2, padx=(5, 0))
        self.entries[key] = e
        return row + 1

    def _add_file_entry(self, parent, label, default, key, row):
        ttk.Label(parent, text=f"{label}:").grid(row=row, column=0, sticky="w", pady=2)
        f = ttk.Frame(parent)
        f.grid(row=row, column=1, sticky="ew", pady=2, padx=(5, 0))
        e = ttk.Entry(f, width=25)
        e.insert(0, default)
        e.pack(side="left", fill="x", expand=True)
        self.entries[key] = e
        ttk.Button(f, text="选择", width=6, command=lambda: self._browse_file(e)).pack(side="right", padx=(3, 0))
        return row + 1

    def _add_folder_entry(self, parent, label, default, key, row):
        ttk.Label(parent, text=f"{label}:").grid(row=row, column=0, sticky="w", pady=2)
        f = ttk.Frame(parent)
        f.grid(row=row, column=1, sticky="ew", pady=2, padx=(5, 0))
        e = ttk.Entry(f, width=25)
        e.insert(0, default)
        e.pack(side="left", fill="x", expand=True)
        self.entries[key] = e
        ttk.Button(f, text="选择", width=6, command=lambda: self._browse_folder(e)).pack(side="right", padx=(3, 0))
        return row + 1

    def _browse_file(self, entry):
        path = filedialog.askopenfilename(title="选择文件", filetypes=[("Excel", "*.xlsx *.xls"), ("所有文件", "*.*")])
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    def _browse_folder(self, entry):
        path = filedialog.askdirectory(title="选择文件夹")
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    def log(self, msg):
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.parent.update()

    def clear_log(self):
        self.log_text.delete(1.0, tk.END)

    def run_script(self):
        threading.Thread(target=self._run, daemon=True).start()

    def run_vba(self):
        threading.Thread(target=self._run_vba, daemon=True).start()

    def _run(self):
        self.run_status.set("执行中...")
        self.log("=" * 50)
        self.log("开始执行...")
        self.log("=" * 50)

        # 保存当前界面配置
        self._write_config()
        self.log("[OK] 配置已保存")

        # 确保从文件系统加载 config.py，而不是从 exe 内部
        sys.path.insert(0, BASE_DIR)

        # 在模块重载列表中添加 vba_signal_reader
        for mod in ['config', 'query_signal_report', 'api_query', 'signal_comparison', 'vba_signal_reader']:
            if mod in sys.modules:
                del sys.modules[mod]

        from query_signal_report import run

        # 捕获 print 输出
        old_stdout = sys.stdout
    
        class DualOutput:
            def __init__(self, stdout, log_func):
                self.stdout = stdout if stdout is not None else open(os.devnull, 'w')
                self.log_func = log_func
                self.buffer = ""

            def write(self, text):
                self.stdout.write(text)
                self.buffer += text
                if "\n" in text:
                    for line in self.buffer.split("\n")[:-1]:
                        if line.rstrip():
                            self.log_func(line.rstrip())
                    self.buffer = self.buffer.split("\n")[-1]

            def flush(self):
                self.stdout.flush()

        try:
            sys.stdout = DualOutput(sys.stdout, self.log)
            run()
            self.run_status.set("✅ 完成")
        except Exception as e:
            self.run_status.set("❌ 失败")
            self.log(f"[X] 异常: {e}")
        finally:
            sys.stdout = old_stdout

        self.log("=" * 50)

    def _run_vba(self):
        self.run_status.set("执行中...")
        self.log("=" * 50)
        self.log("VBA 总线信号读取")
        self.log("=" * 50)

        # 保存当前界面配置
        self._write_config()
        self.log("[OK] 配置已保存")

        # 确保从文件系统加载 config.py
        sys.path.insert(0, BASE_DIR)

        # 清除缓存的模块，强制重新导入
        for mod in ['config', 'vba_signal_reader', 'api_query']:
            if mod in sys.modules:
                del sys.modules[mod]

        from vba_signal_reader import run

        # 捕获 print 输出
        old_stdout = sys.stdout

        class DualOutput:
            def __init__(self, stdout, log_func):
                self.stdout = stdout if stdout is not None else open(os.devnull, 'w')
                self.log_func = log_func
                self.buffer = ""

            def write(self, text):
                self.stdout.write(text)
                self.buffer += text
                if "\n" in text:
                    for line in self.buffer.split("\n")[:-1]:
                        if line.rstrip():
                            self.log_func(line.rstrip())
                    self.buffer = self.buffer.split("\n")[-1]

            def flush(self):
                self.stdout.flush()

        try:
            sys.stdout = DualOutput(sys.stdout, self.log)
            run()
            self.run_status.set("✅ 完成")
        except Exception as e:
            self.run_status.set("❌ 失败")
            self.log(f"[X] 异常: {e}")
        finally:
            sys.stdout = old_stdout

        self.log("=" * 50)

    def run_vehicle_condition(self):
        threading.Thread(target=self._run_vehicle_condition, daemon=True).start()

    def _run_vehicle_condition(self):
        """车况查询：登录 → 延时等待 → 下发车况查询命令 → 查询结果 → 信号分析 → VBA → 报告"""
        import base64
        import time

        self.run_status.set("执行中...")
        self.log("=" * 50)
        self.log("车况查询流程")
        self.log("=" * 50)

        delay = self.vehicle_delay.get()
        vin = self.entries["API_QUERY_CONFIG.payload.vin"].get().strip()
        self.log(f"延时: {delay} 秒，VIN: {vin}")

        # 保存配置
        self._write_config()
        self.log("[OK] 配置已保存")

        # 确保从文件系统加载模块
        sys.path.insert(0, BASE_DIR)
        for mod in ['config', 'api_query', 'signal_comparison']:
            if mod in sys.modules:
                del sys.modules[mod]

        from config import (
            LOGIN_CONFIG, Vehicle_Condition_Control, Vehicle_Condition_QUERY,
            SIGNAL_LIST_PATH, VBA_PROJECT, OUTPUT_DIR
        )
        from api_query import APIQuery
        from signal_comparison import SignalComparison

        # 捕获 print 输出
        old_stdout = sys.stdout

        class DualOutput:
            def __init__(self, stdout, log_func):
                self.stdout = stdout if stdout is not None else open(os.devnull, 'w')
                self.log_func = log_func
                self.buffer = ""

            def write(self, text):
                self.stdout.write(text)
                self.buffer += text
                if "\n" in text:
                    for line in self.buffer.split("\n")[:-1]:
                        if line.rstrip():
                            self.log_func(line.rstrip())
                    self.buffer = self.buffer.split("\n")[-1]

            def flush(self):
                self.stdout.flush()

        try:
            sys.stdout = DualOutput(sys.stdout, self.log)

            # 1. 登录
            self.log("\n[步骤1] 登录...")
            api = APIQuery()
            success, _ = api.login_and_get_cookies()
            if not success:
                self.log("[X] 登录失败")
                self.run_status.set("❌ 失败")
                return

            # 2. 延时等待
            if delay > 0:
                self.log(f"\n[步骤2] 等待 {delay} 秒后下发车况查询命令...")
                for i in range(delay):
                    if (i + 1) % 5 == 0 or i == 0:
                        self.log(f"  等待 {i+1}/{delay}")
                    time.sleep(1)
            else:
                self.log("\n[步骤2] 延时为0，立即下发...")

            # 3. 下发车况查询命令（使用GUI中的VIN）
            self.log("\n[步骤3] 下发车况查询命令...")
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            }
            username = LOGIN_CONFIG.get("username", "")
            password = LOGIN_CONFIG.get("password", "")
            if username and password:
                credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
                headers['Authorization'] = f'Basic {credentials}'

            control_url = Vehicle_Condition_Control["url"]
            control_payload = Vehicle_Condition_Control["payload"].copy()
            control_payload["vin"] = vin
            self.log(f"请求URL: {control_url}")
            response = api.session.post(control_url, json=control_payload, headers=headers, timeout=30)
            self.log(f"响应状态码: {response.status_code}")
            if response.status_code != 200:
                self.log("[X] 车况查询命令下发失败")
                self.run_status.set("❌ 失败")
                return
            self.log("[OK] 车况查询命令已下发")

            # 等待30秒，等TBOX上报车况数据
            self.log("\n  等待 30 秒，等待TBOX上报车况数据...")
            for i in range(30):
                if (i + 1) % 5 == 0:
                    self.log(f"  等待 {i+1}/30")
                time.sleep(1)
            self.log("  [OK] 等待完成")

            # 4. 查询车况数据（使用GUI中的VIN）
            self.log("\n[步骤4] 查询TBOX车况数据...")
            query_url = Vehicle_Condition_QUERY["url"]
            query_payload = Vehicle_Condition_QUERY["payload"].copy()
            query_payload["vin"] = vin
            result = api.query_by_api(api_url=query_url, request_data=query_payload)
            if not result:
                self.log("[X] 车况数据查询失败")
                self.run_status.set("❌ 失败")
                return

            # 5. 解析数据
            self.log("\n[步骤5] 解析车况数据...")
            parsed_signals = api.parse_result_data(result)
            if not parsed_signals:
                self.log("[X] 数据解析失败")
                self.run_status.set("❌ 失败")
                return

            did_codes = set()
            for signal in parsed_signals:
                did_code = signal.get('didCode')
                if did_code:
                    did_codes.add(str(did_code))
            self.log(f"[OK] 提取了 {len(did_codes)} 个 didCode")

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            if not os.path.exists(OUTPUT_DIR):
                os.makedirs(OUTPUT_DIR)

            # 6. 信号对比分析
            self.log("\n[步骤6] 信号编号对比分析...")
            comparison = SignalComparison()
            signal_codes, all_signals = comparison.load_signal_codes(SIGNAL_LIST_PATH)
            comparison_result = comparison.compare_signals(did_codes, signal_codes, all_signals)
            comparison_html = os.path.join(OUTPUT_DIR, f"vehicle_condition_comparison_{timestamp}.html")
            comparison.generate_html_report(comparison_result, comparison_html,
                                             query_info={"vin": vin, "app_id": "12", "msg_type": "1"})
            self.log(f"[OK] 对比报告已生成: {comparison_html}")

            # 7. 信号匹配 + VBA 总线值 + HTML 报告
            self.log("\n[步骤7] 信号匹配与报告生成...")
            signal_mapping = api.load_signal_mapping(SIGNAL_LIST_PATH)
            if signal_mapping is None:
                self.log("[X] 加载信号对应表失败")
                self.run_status.set("❌ 失败")
                return

            matched_data = api.match_signals(parsed_signals, signal_mapping)
            if not matched_data:
                self.log("[X] 信号匹配失败")
                self.run_status.set("❌ 失败")
                return

            # 获取总线值（VBA COM）
            self.log("\n  通过 VBA COM 获取总线信号值...")
            try:
                import win32com.client
                vba = win32com.client.Dispatch("VBACOM")
                project = vba.getProjectByname(VBA_PROJECT)
                if project and project.isStart():
                    can_bus = project.getCANBusModule()
                    self.log("  [OK] VBA COM 连接成功")
                    success = 0
                    failed = 0
                    for item in matched_data:
                        can_id_raw = item.get('CANID', '')
                        eng_name = item.get('english_name', '')
                        if can_id_raw and eng_name:
                            try:
                                can_id = int(str(can_id_raw).strip(), 16)
                                value = can_bus.getSignalPhyVal("CAN1", can_id, 1, eng_name)
                                item['bus_value'] = str(value)
                                success += 1
                            except Exception:
                                item['bus_value'] = '-'
                                failed += 1
                        else:
                            item['bus_value'] = '-'
                            failed += 1
                    self.log(f"  [OK] 总线值获取完成: 成功 {success} 条，失败 {failed} 条")
                else:
                    self.log("  [!] VBA 未连接或未启动，跳过总线值获取")
                    for item in matched_data:
                        item['bus_value'] = '-'
            except ImportError:
                self.log("  [!] 未安装 pywin32，跳过总线值获取")
                for item in matched_data:
                    item['bus_value'] = '-'

            # 生成 HTML 报告
            report_html = api.generate_html(matched_data, f"vehicle_condition_report_{timestamp}.html",
                                             query_info={"vin": vin, "app_id": "12", "msg_type": "1"})
            if not report_html:
                self.log("[X] HTML生成失败")
                self.run_status.set("❌ 失败")
                return

            self.log("\n" + "=" * 50)
            self.log("[OK] 车况查询完成！")
            self.log("=" * 50)
            self.log(f"对比报告: {comparison_html}")
            self.log(f"信号报告: {report_html}")
            self.run_status.set("✅ 完成")

        except Exception as e:
            self.run_status.set("❌ 失败")
            self.log(f"[X] 异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            sys.stdout = old_stdout

        self.log("=" * 50)


def main(parent=None):
    # 首次运行自动生成 config.py
    if not os.path.exists(CONFIG_PATH):
        cfg = DEFAULT_CONFIG
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write('"""配置文件"""\n\n')
            f.write("LOGIN_CONFIG = {\n")
            for k, v in cfg["LOGIN_CONFIG"].items():
                escaped = str(v).replace("\\", "\\\\")
                f.write(f'    "{k}": r"{escaped}",\n')
            f.write("}\n\n")
            f.write("API_QUERY_CONFIG = {\n")
            f.write(f'    "url": r"{cfg["API_QUERY_CONFIG"]["url"]}",\n')
            f.write('    "payload": {\n')
            for k, v in cfg["API_QUERY_CONFIG"]["payload"].items():
                f.write(f'        "{k}": None,\n' if v is None else f'        "{k}": r"{str(v).replace(chr(92), chr(92)+chr(92))}",\n')
            f.write("    },\n")
            f.write("}\n\n")
            f.write(f'SIGNAL_LIST_PATH = r"{cfg["SIGNAL_LIST_PATH"]}"\n\n')
            f.write(f'SIGNAL_SHEET_NAMES = {repr(cfg["SIGNAL_SHEET_NAMES"])}\n\n')
            f.write(f'GUOBIAO_SHEET_NAMES = {repr(cfg["GUOBIAO_SHEET_NAMES"])}\n\n')
            f.write(f'VBA_PROJECT = "{cfg["VBA_PROJECT"]}"\n\n')
            f.write(f'OUTPUT_DIR = r"{cfg["OUTPUT_DIR"]}"\n')
            # 首次生成也写入车况查询配置
            vin = cfg["API_QUERY_CONFIG"]["payload"].get("vin", "LA9AEPG2XHHLJK001")
            f.write('\n# 车况查询配置\n')
            f.write('Vehicle_Condition_Control = {\n')
            f.write('    "url": r"https://jmcoperuat.jmc.com.cn/port/control",\n')
            f.write(f'    "payload": {{"vin": "{vin}", "opType": "STATUS_QUERY", "op": "OPEN", "extendAttribute": {{"$": "$"}}, "caller": "hirainuat"}},\n')
            f.write('}\n\n')
            f.write('Vehicle_Condition_QUERY = {\n')
            f.write('    "url": r"https://jmcoperuat.jmc.com.cn/port/getData",\n')
            f.write(f'    "payload": {{"applicationId": 12, "endDate": None, "messageType": 1, "source": "", "startDate": None, "vin": "{vin}"}},\n')
            f.write('}\n')

    if parent is None:
        root = tk.Tk()
        root.title("车况信号比对工具")
        root.geometry("850x600")
        root.minsize(750, 500)
        app = ToolApp(root)
        root.mainloop()
    else:
        app = ToolApp(parent)
    return app


if __name__ == "__main__":
    main()
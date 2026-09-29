"""
远控功能函数 - 工具类
封装登录、发起远控、录制报文、查询远控结果、解析MF4等功能
"""
import requests
import base64
import json
import datetime
import numpy as np
import os
import sys
from remote_config import LOGIN_CONFIG, REMOTE_CONTROL_CONFIG, API_QUERY_CONFIG_TSP, API_QUERY_CONFIG_TBOX, VBA_CONFIG, CAPTURE_PATH


def _read_config_from_file():
    """从文件系统读取 remote_config.py，避免 exe 内 frozen 模块缓存问题"""
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "remote_config.py")
    cfg = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                exec(f.read(), cfg)
        except Exception:
            pass
    return cfg


class APIQuery:
    """远控API查询类"""

    def __init__(self):
        """初始化"""
        self.session = requests.Session()

    def login_and_get_cookies(self):
        """通过HTTP Basic Auth直接登录"""
        cfg = _read_config_from_file()
        login_cfg = cfg.get("LOGIN_CONFIG", LOGIN_CONFIG)
        try:
            print("=" * 50)
            print("通过HTTP Basic Auth登录获取认证信息...")
            print("=" * 50)

            original_url = login_cfg["url"]
            username = login_cfg["username"]
            password = login_cfg["password"]

            credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers = {
                'Authorization': f'Basic {credentials}',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            }

            response = self.session.get(original_url, headers=headers, timeout=15)
            print(f"登录状态码: {response.status_code}")
            print(f"[OK] 获取到 {len(self.session.cookies)} 个cookie")
            print("[OK] 登录成功，认证信息已获取")
            return True, None

        except Exception as e:
            print(f"[X] 登录失败: {str(e)}")
            return False, None

    def _build_headers(self):
        """构建通用请求头（含Basic Auth）"""
        cfg = _read_config_from_file()
        login_cfg = cfg.get("LOGIN_CONFIG", LOGIN_CONFIG)
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': login_cfg.get("url", ""),
        }
        username = login_cfg.get("username", "")
        password = login_cfg.get("password", "")
        if username and password:
            credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers['Authorization'] = f'Basic {credentials}'
        return headers

    def send_remote_control(self, vin=None, api_url=None, request_data=None):
        """
        发起远控请求

        Args:
            vin: VIN码
            api_url: 远控地址（默认使用REMOTE_CONTROL_CONFIG.url）
            request_data: 远控请求数据（默认使用REMOTE_CONTROL_CONFIG.payload）

        Returns:
            响应JSON数据
        """
        try:
            print("\n" + "=" * 50)
            print("发起远控请求...")
            print("=" * 50)

            if not api_url or not request_data:
                cfg = _read_config_from_file()
                rc_cfg = cfg.get("REMOTE_CONTROL_CONFIG", REMOTE_CONTROL_CONFIG)
                if not api_url:
                    api_url = rc_cfg.get("url")
                if not request_data:
                    request_data = rc_cfg.get("payload", {}).copy()

            if vin:
                request_data["vin"] = vin

            if not request_data.get("vin"):
                print("[X] 未提供VIN码")
                return None

            headers = self._build_headers()
            print(f"请求URL: {api_url}")
            print(f"请求数据: {request_data}")

            response = self.session.post(api_url, json=request_data, headers=headers, timeout=30)
            print(f"响应状态码: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                print(f"[OK] 远控请求已发送，响应共 {len(str(result))} 字符")
                return result
            else:
                print(f"[X] 远控请求失败: {response.status_code}")
                print(f"响应内容: {response.text}")
                return None

        except Exception as e:
            print(f"[X] 远控请求异常: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def query_by_api(self, api_url=None, request_data=None):
        """
        通过API查询数据（通用方法）

        Args:
            api_url: API地址
            request_data: 请求数据

        Returns:
            响应JSON数据
        """
        try:
            if not api_url:
                print("[X] 未提供API地址")
                return None

            print(f"\n发送POST请求: {api_url}")
            headers = self._build_headers()

            response = self.session.post(api_url, json=request_data, headers=headers, timeout=30)
            print(f"响应状态码: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                print(f"[OK] 获取到响应数据，共 {len(str(result))} 字符")
                return result
            else:
                print(f"[X] 请求失败: {response.status_code}")
                print(f"响应内容: {response.text}")
                return None

        except Exception as e:
            print(f"[X] API查询异常: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    # ============== TBOX 结果解析 ==============

    @staticmethod
    def _ms_to_beijing_time(ms_timestamp):
        """将毫秒时间戳转为北京时间（UTC+8）字符串"""
        if not ms_timestamp:
            return "N/A"
        try:
            ts = int(ms_timestamp) / 1000  # ms → s
            utc_time = datetime.datetime.utcfromtimestamp(ts)
            beijing_time = utc_time + datetime.timedelta(hours=8)
            return beijing_time.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(ms_timestamp)

    def parse_tbox_result(self, response_data):
        """
        解析TBOX查询结果
        提取流程: result[0] → payload → data → errorCode + responseData

        Args:
            response_data: TBOX API返回的完整JSON数据

        Returns:
            dict: {"errorCode": 错误码, "responseData": {子项参数: 子项编码, ...}}
        """
        try:
            print("\n" + "=" * 50)
            print("解析TBOX远控结果...")
            print("=" * 50)

            result_list = response_data.get("result", [])
            if not result_list:
                print("[X] 未找到result数据")
                return None

            first_result = result_list[0]
            timestamp = self._ms_to_beijing_time(first_result.get("sendTimestamp"))
            payload_str = first_result.get("payload", "")
            if not payload_str:
                print("[X] 未找到payload数据")
                return None

            payload = json.loads(payload_str)
            data_result = payload.get("data", {})

            error_code = data_result.get("errorCode", "N/A")
            response_data_dict = data_result.get("responseData", {})

            print(f"[OK] 时间戳: {timestamp}")
            print(f"[OK] 错误码: {error_code}")
            print(f"[OK] 子项数量: {len(response_data_dict)}")

            # 打印详细信息
            for param, code in response_data_dict.items():
                print(f"      子项参数: {param} → 子项编码: {code}")

            return {
                "timestamp": timestamp,
                "errorCode": error_code,
                "responseData": response_data_dict,
            }

        except Exception as e:
            print(f"[X] TBOX结果解析失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    # ============== TSP 结果解析 ==============

    def parse_tsp_result(self, response_data):
        """
        解析TSP查询结果
        提取流程: result[0] → payload → data → controlCommands

        Args:
            response_data: TSP API返回的完整JSON数据

        Returns:
            dict: {"controlCommands": {子项参数: 子项编码, ...}}
        """
        try:
            print("\n" + "=" * 50)
            print("解析TSP远控结果...")
            print("=" * 50)

            result_list = response_data.get("result", [])
            if not result_list:
                print("[X] 未找到result数据")
                return None

            first_result = result_list[0]
            timestamp = self._ms_to_beijing_time(first_result.get("sendTimestamp"))
            payload_str = first_result.get("payload", "")
            if not payload_str:
                print("[X] 未找到payload数据")
                return None

            payload = json.loads(payload_str)
            data_result = payload.get("data", {})

            control_commands = data_result.get("controlCommands", {})

            print(f"[OK] 时间戳: {timestamp}")
            print(f"[OK] 子项数量: {len(control_commands)}")

            for param, code in control_commands.items():
                print(f"      子项参数: {param} → 子项编码: {code}")

            return {
                "timestamp": timestamp,
                "controlCommands": control_commands,
            }

        except Exception as e:
            print(f"[X] TSP结果解析失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    # ============== VBA 录制报文 ==============

    def start_capture(self, can_ids, path=None):
        """通过 VBA COM 录制指定 CAN 报文的信号"""
        import win32com.client
        cfg = _read_config_from_file()
        vba_cfg = cfg.get("VBA_CONFIG", VBA_CONFIG)
        if not path:
            path = cfg.get("CAPTURE_PATH", CAPTURE_PATH)

        print(f"\n开始录制报文到: {path}")
        print(f"  录制CAN ID: {[hex(cid) for cid in can_ids]}")

        try:
            vba = win32com.client.Dispatch("VBACOM")
            project = vba.getProjectByname(vba_cfg["project"])
            if project is None or not project.isStart():
                print("[X] VBA 未连接或未启动")
                return None

            can_bus = project.getCANBusModule()
            network = project.getNetworkByName(vba_cfg["network"], 0)
            vbus_database = network.getDatabaseByName(vba_cfg["database"])

            signals = ()
            for can_id in can_ids:
                signals += vbus_database.getSignalsByMsg(can_id, 1)
                print(f"  已添加 CAN ID 0x{can_id:X} 的信号")

            res = can_bus.startCapture(signals, path)
            task_id = res.getInfo()
            print(f"[OK] 开始录制，任务ID: {task_id}")
            return task_id

        except Exception as e:
            print(f"[X] 录制启动失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def stop_capture(self, task_id):
        """停止录制"""
        if not task_id:
            print("[!] 无录制任务ID，跳过停止")
            return

        import win32com.client
        cfg = _read_config_from_file()
        vba_cfg = cfg.get("VBA_CONFIG", VBA_CONFIG)
        try:
            vba = win32com.client.Dispatch("VBACOM")
            project = vba.getProjectByname(vba_cfg["project"])
            can_bus = project.getCANBusModule()
            can_bus.stopCapture(task_id)
            print("[OK] 录制已停止")
        except Exception as e:
            print(f"[X] 停止录制失败: {e}")

    # ============== MF4 解析 ==============

    def parse_mf4_signal(self, mf4_path, signal_name, signal_values):
        """解析 MF4 中指定信号的快发三帧"""
        from asammdf import MDF
        mdf = MDF(mf4_path)

        target_ch = None
        for ch in mdf.channels_db.keys():
            if ch.endswith(f"::{signal_name}"):
                target_ch = ch
                break

        if target_ch is None:
            print(f"  [X] 未找到信号 '{signal_name}'")
            mdf.close()
            return None

        try:
            signal = mdf.get(target_ch)
            data = np.array(signal.samples, dtype=float)
            timestamps = np.array(signal.timestamps, dtype=float)

            if len(data) < 3:
                print(f"  [X] 信号 '{signal_name}' 数据不足3帧")
                mdf.close()
                return None

            base_val = data[0]

            change_idx = -1
            for i in range(1, len(data)):
                if data[i] != base_val:
                    change_idx = i
                    break

            if change_idx == -1:
                print(f"  [X] 信号 '{signal_name}' 无变化（始终为 {base_val}）")
                mdf.close()
                return None

            end_idx = min(change_idx + 4, len(data))
            frame_count = end_idx - change_idx

            changed_values = data[change_idx:end_idx]
            changed_times = timestamps[change_idx:end_idx]

            intervals = []
            for i in range(1, len(changed_times)):
                intervals.append((changed_times[i] - changed_times[i-1]) * 1000)

            # 周期按前三帧（即前2个间隔）计算
            period_intervals = intervals[:2]
            avg_period = sum(period_intervals) / len(period_intervals) if period_intervals else 0

            frames = []
            for v in changed_values:
                int_val = int(v)
                meaning = signal_values.get(int_val, f"未知({int_val})")
                frames.append({"value": int_val, "meaning": meaning})

            result = {
                "base_val": int(base_val),
                "base_meaning": signal_values.get(int(base_val), f"未知({int(base_val)})"),
                "frames": frames,
                "period_ms": round(avg_period, 1),
                "intervals_ms": [round(x, 1) for x in intervals],
            }

            print(f"  [OK] '{signal_name}': {base_val} → {changed_values[0]}")
            print(f"        周期: {avg_period:.1f}ms")
            for f in frames:
                print(f"        值: {f['value']} → {f['meaning']}")

            mdf.close()
            return result

        except Exception as e:
            print(f"  [X] 解析信号 '{signal_name}' 失败: {e}")
            mdf.close()
            return None
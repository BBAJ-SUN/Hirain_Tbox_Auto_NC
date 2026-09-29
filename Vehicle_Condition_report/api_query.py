"""
API查询脚本
通过POST请求方式获取数据
"""

import requests
import json
import time
import base64
import pandas as pd
from config import LOGIN_CONFIG, API_QUERY_CONFIG, SIGNAL_SHEET_NAMES


def _to_int_str(val):
    """将浮点数转为整数字符串，避免显示 1.0 这样的格式"""
    if pd.isna(val):
        return '-'
    try:
        if isinstance(val, float):
            return str(int(val))
        return str(val)
    except (ValueError, TypeError):
        return '-'


class APIQuery:
    """API查询类"""

    def __init__(self):
        """初始化"""
        self.session = requests.Session()

    def login_and_get_cookies(self):
        """通过HTTP Basic Auth直接登录，无需浏览器，速度更快"""
        try:
            print("=" * 50)
            print("通过HTTP Basic Auth登录获取认证信息...")
            print("=" * 50)

            original_url = LOGIN_CONFIG["url"]
            username = LOGIN_CONFIG["username"]
            password = LOGIN_CONFIG["password"]

            # 构建 Basic Auth 头
            credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers = {
                'Authorization': f'Basic {credentials}',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            }

            # 发送GET请求获取cookies
            response = self.session.get(original_url, headers=headers, timeout=15)
            print(f"登录状态码: {response.status_code}")
            print(f"[OK] 获取到 {len(self.session.cookies)} 个cookie")
            print("[OK] 登录成功，认证信息已获取")

            return True, None

        except Exception as e:
            print(f"[X] 登录失败: {str(e)}")
            return False, None

    def query_by_api(self, vin=None, api_url=None, request_data=None):
        """
        通过API查询数据

        Args:
            vin: VIN码（如果request_data中已有vin，此项将被忽略）
            api_url: API地址（如果不提供，使用配置文件中的地址）
            request_data: 请求数据（如果不提供，使用配置文件中的payload）

        Returns:
            响应数据
        """
        try:
            print("\n" + "=" * 50)
            print("发送POST请求查询数据...")
            print("=" * 50)

            # 使用配置文件中的URL
            if not api_url:
                api_url = API_QUERY_CONFIG.get("url")
                print(f"[!] 使用配置文件中的API地址: {api_url}")

            if not api_url:
                print("[X] 未提供API地址")
                return None

            # 使用配置文件中的payload
            if not request_data:
                request_data = API_QUERY_CONFIG.get("payload", {}).copy()
                print(f"[!] 使用配置文件中的payload")

                # 如果指定了vin参数，更新payload中的vin
                if vin:
                    request_data["vin"] = vin
                    print(f"[!] 使用指定的VIN码: {vin}")

            # 如果payload中没有vin，使用参数中的vin或配置中的vin
            if not request_data.get("vin"):
                vin = vin or API_QUERY_CONFIG.get("payload", {}).get("vin", "")
                if vin:
                    request_data["vin"] = vin

            if not request_data.get("vin"):
                print("[X] 未提供VIN码")
                return None

            # 设置请求头
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Referer': LOGIN_CONFIG.get("url", ""),
            }

            # 添加HTTP Basic Auth认证头
            username = LOGIN_CONFIG.get("username", "")
            password = LOGIN_CONFIG.get("password", "")
            if username and password:
                credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
                headers['Authorization'] = f'Basic {credentials}'
                print(f"[!] 已添加HTTP Basic Auth认证头（用户: {username}）")

            print(f"\n请求URL: {api_url}")
            print(f"请求数据: (已发送)")

            # 发送POST请求
            response = self.session.post(
                api_url,
                json=request_data,
                headers=headers,
                timeout=30
            )

            print(f"\n响应状态码: {response.status_code}")

            if response.status_code == 200:
                # 尝试解析JSON响应
                try:
                    result = response.json()
                    print(f"响应数据: (已保存，共 {len(str(result))} 字符)")
                    return result
                except:
                    # 如果不是JSON，返回文本
                    print(f"响应文本:\n{response.text}")
                    return response.text
            else:
                print(f"[X] 请求失败: {response.status_code}")
                print(f"响应内容: {response.text}")
                return None

        except Exception as e:
            print(f"[X] API查询失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def query_vehicle_info(self, vin=None):
        """查询车辆信息（示例方法）"""
        return self.query_by_api(vin)

    def quick_query(self):
        """快速查询（使用配置文件中的所有设置）"""
        return self.query_by_api()

    def parse_result_data(self, response_data):
        """
        解析API返回的数据

        Args:
            response_data: API返回的完整数据

        Returns:
            解析后的信号数据列表
        """
        try:
            print("\n" + "=" * 50)
            print("解析数据...")
            print("=" * 50)

            # 提取result列表
            result_list = response_data.get("result", [])
            if not result_list:
                print("[X] 未找到result数据")
                return None

            print(f"[OK] 找到 {len(result_list)} 条result数据")

            # 获取第一条数据
            first_result = result_list[0]
            print(f"[OK] 提取第一条数据，id: {first_result.get('id')}")

            # 提取payload
            payload_str = first_result.get("payload", "")
            if not payload_str:
                print("[X] 未找到payload数据")
                return None

            # 解析payload JSON
            payload = json.loads(payload_str)
            print(f"[OK] payload解析成功")

            # 提取customDids (从vehicleUploadData中)
            vehicle_upload_data = payload.get("data", {}).get("vehicleUploadData", [])
            if not vehicle_upload_data:
                print("[!] 未找到vehicleUploadData数据，尝试vehData...")
                vehicle_upload_data = payload.get("data", {}).get("vehData", [])
                if not vehicle_upload_data:
                    print("[X] 未找到vehicleUploadData或vehData数据")
                    return None
                else:
                    print(f"[OK] 从vehData中找到数据，共 {len(vehicle_upload_data)} 条")

            custom_dids = vehicle_upload_data[0].get("customDids", [])
            if not custom_dids:
                print("[X] 未找到customDids数据")
                return None

            print(f"[OK] 找到 {len(custom_dids)} 组信号数据")

            # 解析所有信号
            parsed_signals = []
            for did_group in custom_dids:
                did_code = did_group.get("didCode")
                did_signals = did_group.get("didSignals", [])

                for signal in did_signals:
                    parsed_signals.append({
                        "didCode": did_code,
                        "number": signal.get("number"),
                        "status": signal.get("status"),
                        "values": signal.get("values")
                    })

            print(f"[OK] 共解析出 {len(parsed_signals)} 个信号值")
            return parsed_signals

        except Exception as e:
            print(f"[X] 数据解析失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def load_signal_mapping(self, excel_path):
        """
        加载信号对应表（从多个sheet页合并）

        Args:
            excel_path: Excel文件路径

        Returns:
            DataFrame格式的信号对应表
        """
        try:
            print(f"\n加载信号对应表: {excel_path}")

            # 定义要读取的sheet页列表（从config读取）
            sheet_names = SIGNAL_SHEET_NAMES

            # 读取多个sheet并合并
            dfs = []
            for sheet_name in sheet_names:
                try:
                    df_sheet = pd.read_excel(excel_path, sheet_name=sheet_name)

                    # 只保留需要的列
                    columns_to_keep = ['CANID', '信号编号', '中文名称', '中文解释', '英文名称', '精度转换']
                    df_sheet = df_sheet[columns_to_keep]

                    # 添加来源标识
                    df_sheet['source_sheet'] = sheet_name

                    dfs.append(df_sheet)
                    print(f"[OK] 从 '{sheet_name}' 读取了 {len(df_sheet)} 条数据")
                except Exception as e:
                    print(f"[!] 读取 '{sheet_name}' 失败: {str(e)}")
                    continue

            if not dfs:
                print("[X] 未能读取任何sheet页数据")
                return None

            # 合并所有DataFrame
            df = pd.concat(dfs, ignore_index=True)

            # 重命名列名，避免中文显示问题
            df.columns = ['CANID', 'signal_code', 'chinese_name', 'chinese_explanation', 'english_name', 'precision_convert', 'source_sheet']

            # 删除空行
            df = df.dropna(subset=['signal_code'])

            # 将信号编号转为整数
            df['signal_code'] = df['signal_code'].astype(int)

            print(f"[OK] 总共加载了 {len(df)} 条信号映射数据")

            return df

        except Exception as e:
            print(f"[X] 加载信号对应表失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def match_signals(self, parsed_signals, signal_mapping_df):
        """
        将解析的信号与信号对应表进行匹配

        Args:
            parsed_signals: 解析出的信号列表
            signal_mapping_df: 信号对应表DataFrame

        Returns:
            匹配后的数据列表
        """
        try:
            print("\n匹配信号数据...")

            matched_data = []

            # 创建一个字典，记录每个信号编号当前匹配到第几行
            signal_counters = {}

            for signal in parsed_signals:
                did_code = signal['didCode']
                number = signal['number']
                values = signal['values']

                # 初始化计数器
                if did_code not in signal_counters:
                    signal_counters[did_code] = 0

                # 在信号对应表中查找匹配的行
                matched_rows = signal_mapping_df[signal_mapping_df['signal_code'] == int(did_code)]

                if len(matched_rows) > 0:
                    # 按照计数器获取对应的行
                    row_index = signal_counters[did_code]

                    if row_index < len(matched_rows):
                        matched_row = matched_rows.iloc[row_index]

                        matched_data.append({
                            'CANID': matched_row['CANID'],
                            'signal_code': did_code,
                            'chinese_name': matched_row['chinese_name'],
                            'chinese_explanation': matched_row['chinese_explanation'],
                            'english_name': matched_row['english_name'],
                            'precision_convert': _to_int_str(matched_row['precision_convert']),
                            'number': number,
                            'status': signal['status'],
                            'values': values
                        })

                        # 计数器加1
                        signal_counters[did_code] += 1
                    else:
                        # 如果超出范围，使用最后一行
                        matched_row = matched_rows.iloc[-1]
                        matched_data.append({
                            'CANID': matched_row['CANID'],
                            'signal_code': did_code,
                            'chinese_name': matched_row['chinese_name'],
                            'chinese_explanation': matched_row['chinese_explanation'],
                            'english_name': matched_row['english_name'],
                            'precision_convert': _to_int_str(matched_row['precision_convert']),
                            'number': number,
                            'status': signal['status'],
                            'values': values
                        })
                else:
                    # 未找到匹配
                    matched_data.append({
                        'CANID': 'N/A',
                        'signal_code': did_code,
                        'chinese_name': '未知信号',
                        'chinese_explanation': '未在信号表中找到',
                        'english_name': 'Unknown',
                        'precision_convert': '',
                        'number': number,
                        'status': signal['status'],
                        'values': values
                    })

            print(f"[OK] 匹配完成，共 {len(matched_data)} 条数据")
            return matched_data

        except Exception as e:
            print(f"[X] 信号匹配失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def generate_html(self, matched_data, output_file="signal_report.html", query_info=None):
        """
        生成HTML报告

        Args:
            matched_data: 匹配后的数据列表
            output_file: 输出文件名
            query_info: 可选，报告头显示的查询信息字典，含 vin/app_id/msg_type
        """
        try:
            print("\n生成HTML报告...")

            html_template = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>车辆信号数据报告</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
            background: #f0f2f5;
            color: #333;
            line-height: 1.6;
        }}
        .container {{
            max-width: 1600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            background: linear-gradient(135deg, #1976d2 0%, #1565c0 100%);
            color: white;
            padding: 25px 30px;
            border-radius: 10px;
            margin-bottom: 20px;
            text-align: center;
        }}
        .header h1 {{
            font-size: 24px;
            margin-bottom: 10px;
        }}
        .header .info {{
            font-size: 14px;
            opacity: 0.9;
        }}
        .stats {{
            display: flex;
            justify-content: center;
            gap: 40px;
            margin-top: 15px;
        }}
        .stats-item {{
            text-align: center;
        }}
        .stats-item .value {{
            font-size: 28px;
            font-weight: bold;
        }}
        .stats-item .label {{
            font-size: 12px;
            opacity: 0.8;
        }}
        .query-info {{
            margin-top: 12px;
            font-size: 13px;
            opacity: 0.85;
            display: flex;
            justify-content: center;
            gap: 30px;
        }}
        .table-container {{
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th {{
            background: #1976d2;
            color: white;
            padding: 14px 12px;
            text-align: left;
            font-weight: 600;
            font-size: 13px;
            white-space: nowrap;
            border-right: 1px solid rgba(255,255,255,0.1);
        }}
        th:last-child {{
            border-right: none;
        }}
        td {{
            padding: 10px 12px;
            border-bottom: 1px solid #f0f0f0;
            font-size: 13px;
        }}
        tr:hover {{
            background: #f5f9ff;
        }}
        tr:nth-child(even) {{
            background: #fafbfc;
        }}
        tr:nth-child(even):hover {{
            background: #f0f5ff;
        }}
        .status-ok {{
            color: #52c41a;
            font-weight: bold;
        }}
        .status-error {{
            color: #ff4d4f;
            font-weight: bold;
        }}
        .footer {{
            text-align: center;
            padding: 15px;
            color: #999;
            font-size: 12px;
        }}
        /* 列宽设置 */
        .col-seq {{ width: 60px; }}
        .col-canid {{ width: 80px; }}
        .col-code {{ width: 90px; }}
        .col-name {{ min-width: 150px; }}
        .col-explain {{ min-width: 180px; }}
        .col-english {{ min-width: 160px; }}
        .col-number {{ width: 120px; }}
        .col-status {{ width: 70px; }}
        .col-value {{ min-width: 100px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>车辆信号数据报告</h1>
            <div class="info">生成时间: {timestamp}</div>
            <div class="stats">
                <div class="stats-item">
                    <div class="value">{data_count}</div>
                    <div class="label">数据总条数</div>
                </div>
            </div>
            <div class="query-info">
                <span>VIN: {vin}</span>
                <span>applicationId: {app_id}</span>
                <span>messageType: {msg_type}</span>
            </div>
        </div>

        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th class="col-seq">序号</th>
                        <th class="col-canid">CANID</th>
                        <th class="col-code">信号编号</th>
                        <th class="col-name">中文名称</th>
                        <th class="col-explain">中文解释</th>
                        <th class="col-english">英文名称</th>
                        <th class="col-number">精度转换</th>
                        <th class="col-number">信号编号(number)</th>
                        <th class="col-status">状态</th>
                        <th class="col-value">上报TSP值</th>
                        <th class="col-value">总线值</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
        </div>

        <div class="footer">
            报告生成时间: {timestamp}
        </div>
    </div>
</body>
</html>
"""

            # 生成表格行
            table_rows = ""
            for i, data in enumerate(matched_data, 1):
                status_class = "status-ok" if data['status'] == '0' else "status-error"
                status_text = "正常" if data['status'] == '0' else "异常"

                def _sv(v):
                    """显示空数据为-"""
                    return '-' if pd.isna(v) or v is None or v == '' or v == 'nan' or v == 'NaN' else str(v)

                row = f"""
            <tr>
                <td>{i}</td>
                <td>{_sv(data['CANID'])}</td>
                <td>{_sv(data['signal_code'])}</td>
                <td>{_sv(data['chinese_name'])}</td>
                <td>{_sv(data['chinese_explanation'])}</td>
                <td>{_sv(data['english_name'])}</td>
                <td>{_sv(data['precision_convert'])}</td>
                <td>{_sv(data['number'])}</td>
                <td class="{status_class}">{status_text}</td>
                <td>{_sv(data['values'])}</td>
                <td>{_sv(data.get('bus_value', '-'))}</td>
            </tr>"""
                table_rows += row

            # 生成完整HTML
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            # 获取配置信息
            if query_info:
                vin = query_info.get("vin", "")
                app_id = query_info.get("app_id", "")
                msg_type = query_info.get("msg_type", "")
            else:
                from config import API_QUERY_CONFIG
                payload = API_QUERY_CONFIG.get("payload", {})
                vin = payload.get("vin", "")
                app_id = payload.get("applicationId", "")
                msg_type = payload.get("messageType", "")

            html_content = html_template.format(
                timestamp=timestamp,
                data_count=len(matched_data),
                table_rows=table_rows,
                vin=vin,
                app_id=app_id,
                msg_type=msg_type
            )

            # 保存HTML文件
            import os
            from config import OUTPUT_DIR
            output_dir = OUTPUT_DIR
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)

            filepath = os.path.join(output_dir, output_file)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)

            print(f"[OK] HTML报告已生成: {filepath}")
            return filepath

        except Exception as e:
            print(f"[X] 生成HTML失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return None



# coding=utf-8
"""
信号编号对比分析脚本
对比 API 数据中的 didCode 与信号列表中的信号编号，分析差异
"""
import sys
import os

# 打包成exe后，从exe所在目录加载config.py
if getattr(sys, 'frozen', False):
    sys.path.insert(0, os.path.dirname(sys.executable))

import pandas as pd
import time
import os
from config import SIGNAL_SHEET_NAMES, SIGNAL_LIST_PATH
from api_query import APIQuery
from config import LOGIN_CONFIG, API_QUERY_CONFIG


class SignalComparison:
    """信号对比分析类"""

    def __init__(self):
        """初始化"""
        self.api_query = APIQuery()

    def fetch_api_data(self, vin=None):
        """
        获取 API 数据并提取所有 didCode

        Returns:
            set: didCode 集合
        """
        print("\n" + "=" * 50)
        print("步骤1: 获取 API 数据")
        print("=" * 50)

        # 登录
        print("正在登录...")
        success, token = self.api_query.login_and_get_cookies()
        if not success:
            print("[X] 登录失败")
            return None

        # 查询数据
        print("正在查询 API 数据...")
        result = self.api_query.quick_query()
        if not result:
            print("[X] 查询失败")
            return None

        # 解析数据
        print("正在解析数据...")
        parsed_signals = self.api_query.parse_result_data(result)
        if not parsed_signals:
            print("[X] 解析失败")
            return None

        # 提取所有 didCode
        did_codes = set()
        for signal in parsed_signals:
            did_code = signal.get('didCode')
            if did_code:
                did_codes.add(str(did_code))

        print(f"[OK] 从 API 数据中提取了 {len(did_codes)} 个 didCode")
        return did_codes, parsed_signals

    def load_signal_codes(self, excel_path):
        """
        从信号列表 Excel 中加载所有信号编号

        Args:
            excel_path: Excel 文件路径

        Returns:
            set: 信号编号集合
            dict: 信号编号 -> 详细信息映射
        """
        print("\n" + "=" * 50)
        print("步骤2: 加载信号列表")
        print("=" * 50)

        sheet_names = SIGNAL_SHEET_NAMES

        all_signals = {}  # {信号编号: {详细信息}}
        signal_codes = set()

        for sheet_name in sheet_names:
            try:
                df = pd.read_excel(excel_path, sheet_name=sheet_name)
                print(f"[OK] 读取 '{sheet_name}' 成功，共 {len(df)} 行")

                # 查找信号编号列
                signal_code_col = None
                for col in df.columns:
                    if '信号编号' in str(col):
                        signal_code_col = col
                        break

                if signal_code_col is None:
                    print(f"[!] '{sheet_name}' 中未找到 '信号编号' 列")
                    continue

                # 提取信号编号
                for idx, row in df.iterrows():
                    code = row.get(signal_code_col)
                    if pd.notna(code):
                        code_str = str(int(float(code))) if isinstance(code, float) else str(code)
                        signal_codes.add(code_str)

                        # 保存详细信息
                        all_signals[code_str] = {
                            'sheet': sheet_name,
                            'CANID': row.get('CANID', 'N/A'),
                            'signal_code': code_str,
                            'chinese_name': self._safe_get(row, '中文名称'),
                            'english_name': self._safe_get(row, '英文名称'),
                        }

            except Exception as e:
                print(f"[!] 读取 '{sheet_name}' 失败: {str(e)}")
                continue

        print(f"[OK] 从信号列表中提取了 {len(signal_codes)} 个信号编号")
        return signal_codes, all_signals

    def _safe_get(self, row, col_name):
        """安全获取值，处理 NaN"""
        val = row.get(col_name)
        if pd.isna(val):
            return ''
        return str(val)

    def compare_signals(self, did_codes, signal_codes, all_signals):
        """
        对比两组信号编号

        Args:
            did_codes: API 数据中的 didCode 集合
            signal_codes: 信号列表中的信号编号集合
            all_signals: 信号详细信息映射

        Returns:
            dict: 对比结果
        """
        print("\n" + "=" * 50)
        print("步骤3: 对比分析")
        print("=" * 50)

        # API 有，信号列表没有（多余）
        api_only = did_codes - signal_codes
        print(f"API 数据有，信号列表没有: {len(api_only)} 个")

        # 信号列表有，API 没有（缺失）
        signal_only = signal_codes - did_codes
        print(f"信号列表有，API 数据没有: {len(signal_only)} 个")

        # 两者都有
        common = did_codes & signal_codes
        print(f"两者都有: {len(common)} 个")

        return {
            'api_only': sorted(list(api_only), key=lambda x: int(x) if x.isdigit() else x),
            'signal_only': sorted(list(signal_only), key=lambda x: int(x) if x.isdigit() else x),
            'common': sorted(list(common), key=lambda x: int(x) if x.isdigit() else x),
            'all_signals': all_signals,
        }

    def generate_html_report(self, comparison_result, output_path, query_info=None):
        """
        生成 HTML 对比报告

        Args:
            comparison_result: 对比结果
            output_path: 输出文件路径
            query_info: 可选，报告头显示的查询信息字典，含 vin/app_id/msg_type
        """
        print("\n" + "=" * 50)
        print("步骤4: 生成 HTML 报告")
        print("=" * 50)

        api_only = comparison_result['api_only']
        signal_only = comparison_result['signal_only']
        common = comparison_result['common']
        all_signals = comparison_result['all_signals']

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

        # 统计汇总
        total_api = len(api_only) + len(common)
        total_signal = len(signal_only) + len(common)

        # 生成表格行 - API 有，信号列表没有
        api_only_rows = ""
        for i, code in enumerate(api_only, 1):
            api_only_rows += f"""
            <tr>
                <td>{i}</td>
                <td>{code}</td>
                <td class="warning">信号列表中不存在</td>
            </tr>"""

        if not api_only_rows:
            api_only_rows = '<tr><td colspan="3" class="empty">无数据</td></tr>'

        # 生成表格行 - 信号列表有，API 没有
        signal_only_rows = ""
        for i, code in enumerate(signal_only, 1):
            sig_info = all_signals.get(code, {})
            signal_only_rows += f"""
            <tr>
                <td>{i}</td>
                <td>{code}</td>
                <td>{sig_info.get('chinese_name', '')}</td>
                <td>{sig_info.get('english_name', '')}</td>
                <td>{sig_info.get('CANID', '')}</td>
                <td>{sig_info.get('sheet', '')}</td>
                <td class="error">TSP 数据中不存在</td>
            </tr>"""

        if not signal_only_rows:
            signal_only_rows = '<tr><td colspan="7" class="empty">无数据</td></tr>'

        # 生成表格行 - 两者都有
        common_rows = ""
        for i, code in enumerate(common, 1):
            sig_info = all_signals.get(code, {})
            common_rows += f"""
            <tr>
                <td>{i}</td>
                <td>{code}</td>
                <td>{sig_info.get('chinese_name', '')}</td>
                <td>{sig_info.get('english_name', '')}</td>
                <td class="success">匹配</td>
            </tr>"""

        if not common_rows:
            common_rows = '<tr><td colspan="5" class="empty">无数据</td></tr>'

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>信号编号对比分析报告</title>
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
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            text-align: center;
        }}
        .header h1 {{
            font-size: 28px;
            margin-bottom: 10px;
        }}
        .header .time {{
            font-size: 14px;
            opacity: 0.9;
        }}
        .header .query-info {{
            margin-top: 12px;
            font-size: 13px;
            opacity: 0.85;
            display: flex;
            justify-content: center;
            gap: 30px;
        }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 20px;
            margin-bottom: 30px;
        }}
        .summary-card {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .summary-card .number {{
            font-size: 36px;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        .summary-card .label {{
            font-size: 14px;
            color: #666;
        }}
        .summary-card.total .number {{ color: #1890ff; }}
        .summary-card.match .number {{ color: #52c41a; }}
        .summary-card.missing .number {{ color: #ff4d4f; }}
        .summary-card.extra .number {{ color: #fa8c16; }}

        .section {{
            background: white;
            border-radius: 10px;
            margin-bottom: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .section-header {{
            background: #f8f9fa;
            padding: 15px 20px;
            border-bottom: 1px solid #e8e8e8;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .section-header h2 {{
            font-size: 18px;
            color: #333;
        }}
        .section-header .badge {{
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 14px;
            font-weight: bold;
        }}
        .badge.error {{ background: #fff2f0; color: #ff4d4f; }}
        .badge.warning {{ background: #fff7e6; color: #fa8c16; }}
        .badge.success {{ background: #f6ffed; color: #52c41a; }}

        .section-body {{
            padding: 0;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th {{
            background: #fafafa;
            padding: 12px 15px;
            text-align: left;
            font-weight: 600;
            color: #333;
            border-bottom: 1px solid #e8e8e8;
        }}
        td {{
            padding: 10px 15px;
            border-bottom: 1px solid #f0f0f0;
        }}
        tr:hover {{
            background: #fafafa;
        }}
        tr:nth-child(even) {{
            background: #fafafa;
        }}
        tr:nth-child(even):hover {{
            background: #f0f0f0;
        }}
        .success {{
            color: #52c41a;
            font-weight: bold;
        }}
        .error {{
            color: #ff4d4f;
            font-weight: bold;
        }}
        .warning {{
            color: #fa8c16;
            font-weight: bold;
        }}
        .empty {{
            text-align: center;
            color: #999;
            padding: 20px;
        }}
        .footer {{
            text-align: center;
            padding: 20px;
            color: #999;
            font-size: 12px;
        }}

        /* 标签页样式 */
        .tabs {{
            display: flex;
            background: #f8f9fa;
            border-bottom: 1px solid #e8e8e8;
        }}
        .tab {{
            padding: 15px 30px;
            cursor: pointer;
            border-bottom: 3px solid transparent;
            transition: all 0.3s;
        }}
        .tab:hover {{
            background: #e8e8e8;
        }}
        .tab.active {{
            border-bottom-color: #1890ff;
            color: #1890ff;
            font-weight: bold;
        }}
        .tab-content {{
            display: none;
        }}
        .tab-content.active {{
            display: block;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>信号编号对比分析报告</h1>
            <div class="time">生成时间: {timestamp}</div>
            <div class="query-info">
                <span>VIN: {vin}</span>
                <span>applicationId: {app_id}</span>
                <span>messageType: {msg_type}</span>
            </div>
        </div>

        <!-- 汇总卡片 -->
        <div class="summary">
            <div class="summary-card total">
                <div class="number">{total_api}</div>
                <div class="label">API 数据总量</div>
            </div>
            <div class="summary-card match">
                <div class="number">{len(common)}</div>
                <div class="label">匹配数量</div>
            </div>
            <div class="summary-card missing">
                <div class="number">{len(signal_only)}</div>
                <div class="label">信号列表缺失</div>
            </div>
            <div class="summary-card extra">
                <div class="number">{len(api_only)}</div>
                <div class="label">API 数据多余</div>
            </div>
        </div>

        <!-- 详细对比结果 -->
        <div class="section">
            <div class="tabs">
                <div class="tab active" onclick="showTab('tab1')">
                    📋 匹配成功 ({len(common)})
                </div>
                <div class="tab" onclick="showTab('tab2')">
                    ❌ 上报TSP数据缺失 ({len(signal_only)})
                </div>
                <div class="tab" onclick="showTab('tab3')">
                    ⚠️ TSP 数据多余 ({len(api_only)})
                </div>
            </div>

            <!-- 匹配成功 -->
            <div id="tab1" class="tab-content active">
                <div class="section-header">
                    <h2>✅ 匹配成功</h2>
                    <span class="badge success">{len(common)} 个</span>
                </div>
                <div class="section-body">
                    <table>
                        <thead>
                            <tr>
                                <th style="width:80px; white-space: nowrap;">序号</th>
                                <th style="width:100px">信号编号</th>
                                <th>中文名称</th>
                                <th>英文名称</th>
                                <th style="width:100px">状态</th>
                            </tr>
                        </thead>
                        <tbody>
                            {common_rows}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- 上报TSP数据缺失 -->
            <div id="tab2" class="tab-content">
                <div class="section-header">
                    <h2>❌ 上报TSP数据缺失（信号列表有，TSP 数据没有）</h2>
                    <span class="badge error">{len(signal_only)} 个</span>
                </div>
                <div class="section-body">
                    <table>
                        <thead>
                            <tr>
                                <th style="width:80px; white-space: nowrap;">序号</th>
                                <th style="width:100px">信号编号</th>
                                <th>中文名称</th>
                                <th>英文名称</th>
                                <th style="width:100px">CANID</th>
                                <th style="width:150px">来源 Sheet</th>
                                <th style="width:120px">状态</th>
                            </tr>
                        </thead>
                        <tbody>
                            {signal_only_rows}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- TSP 数据多余 -->
            <div id="tab3" class="tab-content">
                <div class="section-header">
                    <h2>⚠️ TSP 数据多余（TSP 有，信号列表没有）</h2>
                    <span class="badge warning">{len(api_only)} 个</span>
                </div>
                <div class="section-body">
                    <table>
                        <thead>
                            <tr>
                                <th style="width:80px; white-space: nowrap;">序号</th>
                                <th style="width:100px">didCode</th>
                                <th>状态</th>
                            </tr>
                        </thead>
                        <tbody>
                            {api_only_rows}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <div class="footer">
            信号列表: {SIGNAL_LIST_PATH}
        </div>
    </div>

    <script>
        function showTab(tabId) {{
            // 隐藏所有标签页内容
            document.querySelectorAll('.tab-content').forEach(content => {{
                content.classList.remove('active');
            }});
            // 移除所有标签页的 active 状态
            document.querySelectorAll('.tab').forEach(tab => {{
                tab.classList.remove('active');
            }});
            // 显示选中的标签页
            document.getElementById(tabId).classList.add('active');
            // 激活对应的标签
            event.target.classList.add('active');
        }}
    </script>
</body>
</html>"""

        # 保存文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"[OK] HTML 报告已生成: {output_path}")
        return output_path

    def run(self, signal_excel_path, output_dir="comparison_results"):
        """
        运行完整流程

        Args:
            signal_excel_path: 信号列表 Excel 文件路径
            output_dir: 输出目录
        """
        print("""
╔═══════════════════════════════════════════╗
║      信号编号对比分析脚本 v1.0              ║
║   对比 API 数据与信号列表的差异             ║
╚═══════════════════════════════════════════╝
        """)

        # 1. 获取 API 数据
        result = self.fetch_api_data()
        if result is None:
            print("\n[X] 获取 API 数据失败，程序终止")
            return

        did_codes, parsed_signals = result

        # 2. 加载信号列表
        signal_codes, all_signals = self.load_signal_codes(signal_excel_path)

        # 3. 对比分析
        comparison_result = self.compare_signals(did_codes, signal_codes, all_signals)

        # 4. 生成 HTML 报告
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(output_dir, f"signal_comparison_{timestamp}.html")

        self.generate_html_report(comparison_result, output_path)

        # 5. 打印汇总
        print("\n" + "=" * 50)
        print("分析完成！")
        print("=" * 50)
        print(f"API 数据总量:     {len(did_codes)} 个")
        print(f"信号列表总量:     {len(signal_codes)} 个")
        print(f"匹配成功:         {len(comparison_result['common'])} 个")
        print(f"信号列表缺失:     {len(comparison_result['signal_only'])} 个")
        print(f"API 数据多余:     {len(comparison_result['api_only'])} 个")
        print(f"\n报告路径: {output_path}")
        print("=" * 50)


def main():
    """主函数"""
    # 信号列表 Excel 路径
    from config import SIGNAL_LIST_PATH
    signal_excel_path = SIGNAL_LIST_PATH

    # 创建对比分析实例
    comparison = SignalComparison()

    # 运行分析
    comparison.run(signal_excel_path)


if __name__ == "__main__":
    main()
"""
VBA总线信号读取
从信号列表Excel读取CANID和信号名称，通过VBA COM接口读取总线值，生成HTML报告
"""
import sys
import os
import time
import pandas as pd

# 打包成exe后，从exe所在目录加载config.py
if getattr(sys, 'frozen', False):
    sys.path.insert(0, os.path.dirname(sys.executable))

from config import SIGNAL_LIST_PATH, GUOBIAO_SHEET_NAMES, VBA_PROJECT, OUTPUT_DIR


def read_signal_list(excel_path):
    """读取信号列表Excel，获取CANID、中文名称、中文解释、英文名称、精度转换"""
    print(f"加载信号列表: {excel_path}")

    sheet_names = GUOBIAO_SHEET_NAMES
    columns_to_keep = ['CANID', '中文名称', '中文解释', '英文名称', '精度转换']

    dfs = []
    for sheet_name in sheet_names:
        try:
            df = pd.read_excel(excel_path, sheet_name=sheet_name)
            # 只保留需要的列
            df = df[columns_to_keep]
            df['source_sheet'] = sheet_name
            dfs.append(df)
            print(f"[OK] 从 '{sheet_name}' 读取了 {len(df)} 条数据")
        except Exception as e:
            print(f"[!] 读取 '{sheet_name}' 失败: {str(e)}")
            continue

    if not dfs:
        print("[X] 未能读取任何sheet页数据")
        return None

    df = pd.concat(dfs, ignore_index=True)
    # 精度转换列转为整型显示
    if '精度转换' in df.columns:
        df['精度转换'] = df['精度转换'].apply(lambda x: str(int(x)) if pd.notna(x) and isinstance(x, float) else x)
    # 删除英文名称为空的行
    df = df.dropna(subset=['英文名称'])
    print(f"[OK] 总共加载了 {len(df)} 条信号数据")
    return df


def get_bus_values(df):
    """通过 VBA COM 获取总线信号值"""
    print("\n正在通过 VBA COM 获取总线信号值...")
    try:
        import win32com.client
    except ImportError:
        print("[!] 未安装 pywin32，跳过总线值获取")
        df['bus_value'] = '-'
        return df

    try:
        vba = win32com.client.Dispatch("VBACOM")
        project = vba.getProjectByname(VBA_PROJECT)
        if project is None or not project.isStart():
            print("[!] VBA 未连接或未启动，跳过总线值获取")
            df['bus_value'] = '-'
            return df
        can_bus = project.getCANBusModule()
        print("[OK] VBA COM 连接成功")
    except Exception as e:
        print(f"[!] VBA COM 连接失败: {e}，跳过总线值获取")
        df['bus_value'] = '-'
        return df

    success = 0
    failed = 0
    bus_values = []

    for idx, row in df.iterrows():
        can_id_raw = row.get('CANID', '')
        eng_name = row.get('英文名称', '')

        if pd.isna(can_id_raw) or pd.isna(eng_name) or not str(eng_name).strip():
            bus_values.append('-')
            failed += 1
            continue

        can_id_str = str(can_id_raw).strip()
        eng_name_str = str(eng_name).strip()

        # CANID 按十六进制解析，如 "582" → 0x582
        try:
            can_id = int(can_id_str, 16)
        except ValueError:
            bus_values.append('-')
            failed += 1
            continue

        try:
            value = can_bus.getSignalPhyVal("CAN1", can_id, 1, eng_name_str)
            bus_values.append(str(value))
            success += 1
        except Exception as e:
            bus_values.append('-')
            failed += 1

    df['bus_value'] = bus_values
    print(f"[OK] 总线值获取完成: 成功 {success} 条，失败 {failed} 条")
    return df


def generate_html(df, output_file="vba_signal_report.html"):
    """生成HTML报告，按中文名称分组"""
    print("\n生成HTML报告...")

    # 替换NaN为'-'
    df = df.fillna('-')

    # 按中文名称排序，同名的再按英文名称排序
    df = df.sort_values(by=['中文名称', '英文名称'])

    # 按中文名称分组
    grouped = df.groupby('中文名称', sort=False)

    table_rows = ""
    seq = 0
    for chinese_name, group in grouped:
        if chinese_name == '-':
            continue
        # 分组标题行
        group_count = len(group)
        table_rows += f"""
            <tr class="group-header">
                <td colspan="7">▶ {chinese_name}（共 {group_count} 条）</td>
            </tr>"""
        for _, row in group.iterrows():
            seq += 1
            bus_val = row.get('bus_value', '-')
            canid = row['CANID']
            ch_name = row['中文名称']
            ch_exp = row['中文解释']
            en_name = row['英文名称']
            prec = row['精度转换']

            table_rows += f"""
            <tr>
                <td style="text-align:center">{seq}</td>
                <td style="text-align:center">{canid}</td>
                <td>{ch_name}</td>
                <td>{ch_exp}</td>
                <td>{en_name}</td>
                <td style="text-align:center">{prec}</td>
                <td style="text-align:center; font-weight:bold; color:#1976d2">{bus_val}</td>
            </tr>"""

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VBA总线信号值报告</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
            background: #f0f2f5; color: #333; line-height: 1.6;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
        .header {{
            background: linear-gradient(135deg, #1976d2 0%, #1565c0 100%);
            color: white; padding: 25px 30px; border-radius: 10px; margin-bottom: 20px;
            text-align: center;
        }}
        .header h1 {{ font-size: 24px; margin-bottom: 10px; }}
        .header .info {{ font-size: 14px; opacity: 0.9; }}
        .stats {{
            display: flex; justify-content: center; gap: 40px; margin-top: 15px;
        }}
        .stats-item {{ text-align: center; }}
        .stats-item .value {{ font-size: 28px; font-weight: bold; }}
        .stats-item .label {{ font-size: 12px; opacity: 0.8; }}
        .table-container {{
            background: white; border-radius: 10px; overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{
            background: #1976d2; color: white; padding: 14px 12px;
            text-align: left; font-weight: 600; font-size: 13px;
            white-space: nowrap; border-right: 1px solid rgba(255,255,255,0.1);
        }}
        th:last-child {{ border-right: none; }}
        td {{ padding: 10px 12px; border-bottom: 1px solid #f0f0f0; font-size: 13px; }}
        tr:hover td {{ background: #f5f9ff; }}
        tr:nth-child(even) td {{ background: #fafbfc; }}
        tr:nth-child(even):hover td {{ background: #f0f5ff; }}
        .group-header td {{
            background: #e3f2fd !important; font-weight: bold; font-size: 14px;
            color: #1565c0; padding: 10px 15px; border-bottom: 2px solid #90caf9;
        }}
        .footer {{
            text-align: center; padding: 15px; color: #999; font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>VBA 总线信号值报告</h1>
            <div class="info">生成时间: {timestamp}</div>
            <div class="stats">
                <div class="stats-item">
                    <div class="value">{seq}</div>
                    <div class="label">信号总数</div>
                </div>
                <div class="stats-item">
                    <div class="value">{len(grouped)}</div>
                    <div class="label">信号分组数</div>
                </div>
            </div>
        </div>
        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th style="width:60px">序号</th>
                        <th style="width:80px">CANID</th>
                        <th style="min-width:120px">中文名称</th>
                        <th style="min-width:150px">中文解释</th>
                        <th style="min-width:140px">英文名称</th>
                        <th style="width:80px">精度转换</th>
                        <th style="width:120px">总线值</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
        </div>
        <div class="footer">报告生成时间: {timestamp}</div>
    </div>
</body>
</html>"""

    # 保存文件
    output_dir = OUTPUT_DIR
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    filepath = os.path.join(output_dir, output_file)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"[OK] HTML报告已生成: {filepath}")
    return filepath


def run():
    """执行完整流程：读取信号列表 → 获取总线值 → 生成HTML报告"""
    print("=" * 60)
    print("VBA 总线信号读取")
    print("=" * 60)

    # 1. 读取信号列表
    print("\n[步骤1] 读取信号列表...")
    df = read_signal_list(SIGNAL_LIST_PATH)
    if df is None:
        print("\n[X] 读取信号列表失败，程序终止")
        return

    # 2. 获取总线值
    print("\n[步骤2] 通过 VBA COM 获取总线信号值...")
    df = get_bus_values(df)

    # 3. 生成HTML报告
    print("\n[步骤3] 生成HTML报告...")
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_file = f"vba_signal_report_{timestamp}.html"
    filepath = generate_html(df, output_file)

    print("\n" + "=" * 60)
    print("[OK] 全部完成！")
    print("=" * 60)
    print(f"报告: {filepath}")
    print("=" * 60)


if __name__ == "__main__":
    run()
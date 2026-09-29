"""
API查询 → 信号匹配 → 生成报告，同时对比信号列表差异
"""
import sys
import os

# 打包成exe后，从exe所在目录加载config.py
if getattr(sys, 'frozen', False):
    sys.path.insert(0, os.path.dirname(sys.executable))

from api_query import APIQuery
from signal_comparison import SignalComparison
from config import SIGNAL_LIST_PATH, VBA_PROJECT, OUTPUT_DIR
import time


def get_bus_values(matched_data):
    """
    通过 VBA COM 获取总线信号值，追加到 matched_data 中。
    """
    print("\n正在通过 VBA COM 获取总线信号值...")
    try:
        import win32com.client
    except ImportError:
        print("[!] 未安装 pywin32，跳过总线值获取")
        return matched_data

    try:
        vba = win32com.client.Dispatch("VBACOM")
        project = vba.getProjectByname(VBA_PROJECT)
        if project is None or not project.isStart():
            print("[!] VBA 未连接或未启动，跳过总线值获取")
            return matched_data
        can_bus = project.getCANBusModule()
        print("[OK] VBA COM 连接成功")
    except Exception as e:
        print(f"[!] VBA COM 连接失败: {e}，跳过总线值获取")
        return matched_data

    success = 0
    failed = 0
    for item in matched_data:
        can_id_raw = item.get('CANID', '')
        eng_name = item.get('english_name', '')

        if not can_id_raw or not eng_name:
            item['bus_value'] = '-'
            failed += 1
            continue

        # 解析 CANID：信号列表中的数字代表十六进制，如 582 → 0x582
        try:
            can_id_str = str(can_id_raw).strip()
            # 去掉可能的 0x 前缀
            if can_id_str.startswith("0x") or can_id_str.startswith("0X"):
                can_id = int(can_id_str, 16)
            else:
                # 纯数字也按十六进制解析，如 "582" → 0x582
                can_id = int(can_id_str, 16)
        except ValueError:
            item['bus_value'] = '-'
            failed += 1
            continue

        try:
            value = can_bus.getSignalPhyVal("CAN1", can_id, 1, eng_name)
            item['bus_value'] = str(value)
            success += 1
        except Exception as e:
            item['bus_value'] = '-'
            failed += 1

    print(f"[OK] 总线值获取完成: 成功 {success} 条，失败 {failed} 条")
    return matched_data


def run():
    """执行完整流程"""
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    # =============================================
    # 第一部分：登录 + API查询（共用一次）
    # =============================================
    print("正在登录...")
    api_query = APIQuery()
    success, token = api_query.login_and_get_cookies()
    if not success:
        print("\n[X] 登录失败，程序终止")
        return

    print("\n登录成功，开始查询 API 数据...")
    result = api_query.quick_query()
    if not result:
        print("\n[X] 查询失败，程序终止")
        return

    # 解析数据
    print("\n解析 API 数据...")
    parsed_signals = api_query.parse_result_data(result)
    if not parsed_signals:
        print("\n[X] 数据解析失败，程序终止")
        return

    # 提取 didCode（供后续对比使用）
    did_codes = set()
    for signal in parsed_signals:
        did_code = signal.get('didCode')
        if did_code:
            did_codes.add(str(did_code))
    print(f"[OK] 从 API 数据中提取了 {len(did_codes)} 个 didCode")

    # =============================================
    # 第二部分：信号对比分析（signal_comparison 功能）
    # =============================================
    print("\n" + "=" * 60)
    print("第二部分：信号编号对比分析")
    print("=" * 60)

    comparison = SignalComparison()

    # 加载信号列表
    signal_codes, all_signals = comparison.load_signal_codes(SIGNAL_LIST_PATH)

    # 对比分析
    comparison_result = comparison.compare_signals(did_codes, signal_codes, all_signals)

    # 生成对比报告
    from config import LOGIN_CONFIG, API_QUERY_CONFIG
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    comparison_html = os.path.join(OUTPUT_DIR, f"signal_comparison_{timestamp}.html")
    comparison.generate_html_report(comparison_result, comparison_html)
    print(f"\n[OK] 对比报告已生成: {comparison_html}")

    # =============================================
    # 第三部分：信号匹配 + HTML报告（原query_signal_report功能）
    # =============================================
    print("\n" + "=" * 60)
    print("第三部分：信号匹配与报告生成")
    print("=" * 60)

    # 加载信号对应表
    signal_mapping = api_query.load_signal_mapping(SIGNAL_LIST_PATH)
    if signal_mapping is None:
        print("\n[X] 加载信号对应表失败，程序终止")
        return

    # 匹配信号
    matched_data = api_query.match_signals(parsed_signals, signal_mapping)
    if not matched_data:
        print("\n[X] 信号匹配失败，程序终止")
        return

    # 获取总线值（通过 VBA COM）
    matched_data = get_bus_values(matched_data)

    # 生成HTML报告
    report_html = api_query.generate_html(matched_data, f"signal_report_{timestamp}.html")
    if not report_html:
        print("\n[X] HTML生成失败，程序终止")
        return

    # =============================================
    # 汇总
    # =============================================
    print("\n" + "=" * 60)
    print("[OK] 全部完成！")
    print("=" * 60)
    print(f"对比报告:     {comparison_html}")
    print(f"信号报告:     {report_html}")
    print("=" * 60)



if __name__ == "__main__":
    run()
import win32com.client
import time
import datetime

vba = win32com.client.Dispatch("VBACOM")
project = vba.getProjectByname("ELD")
if project is None or not project.isStart():
    print("VBA 未连接")
    exit()

can_bus = project.getCANBusModule()
print("[OK] VBA 已连接")

test_signals = [
    ("CAN1", 0x582, "TBOX_Year"),
    ("CAN1", 0x582, "TBOX_Month"),
    ("CAN1", 0x582, "TBOX_Hour"),
    ("CAN1", 0x582, "TBOX_Minute"),
]

cycle_count = 1000
interval = 0.02  # 20ms

start = time.time()
fail_count = 0

for cycle in range(cycle_count):
    last_date = datetime.datetime.now()
    for can, can_id, sig_name in test_signals:
        try:
            value = can_bus.getSignalPhyVal(can, can_id, 1, sig_name)
        except Exception as e:
            fail_count += 1
            print(f"[X] 第 {cycle+1} 次 {sig_name}: {e}")

    if (cycle + 1) % 100 == 0:
        elapsed = time.time() - start
        avg = elapsed / (cycle + 1)
        print(f"[{cycle+1}/{cycle_count}] 已用 {elapsed:.1f}s，平均每轮 {avg*1000:.1f}ms，失败 {fail_count} 次")

    if cycle < cycle_count - 1:
        # 计算实际耗时，确保间隔为 20ms
        elapsed_cycle = (datetime.datetime.now() - last_date).total_seconds()
        sleep_time = interval - elapsed_cycle
        if sleep_time > 0:
            time.sleep(sleep_time)

elapsed = time.time() - start
print(f"\n完成！总耗时 {elapsed:.1f}s，平均每轮 {elapsed/cycle_count*1000:.1f}ms，失败 {fail_count} 次")
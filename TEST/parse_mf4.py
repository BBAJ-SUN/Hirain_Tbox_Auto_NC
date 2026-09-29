"""解析 MF4 文件，根据英文信号名检测快发三帧"""
import numpy as np

mf4_path = r"D:\实车半自动化\Test_AUTO\TEST\capture.mf4"
signal_name = "VCU_VehChg_STS"  # 要检测的英文信号名

print("=" * 60)
print(f"快发三帧检测")
print(f"  MF4: {mf4_path}")
print(f"  信号: {signal_name}")
print("=" * 60)

from asammdf import MDF
mdf = MDF(mf4_path)

# 找匹配的信号通道（MF4通道名格式: CAN1::DB::Msg_0xID::信号名）
target_ch = None
for ch in mdf.channels_db.keys():
    print(ch)
    if ch.endswith(f"::{signal_name}"):
        target_ch = ch
        #break

if target_ch is None:
    print(f"\n[X] 未找到信号 '{signal_name}'")
    mdf.close()
    exit()

print(f"\n匹配通道: {target_ch}")

try:
    signal = mdf.get(target_ch)
    data = np.array(signal.samples, dtype=float)
    timestamps = np.array(signal.timestamps, dtype=float)

    if len(data) < 3:
        print("\n  TBOX请求未发出（数据不足3帧）")
        mdf.close()
        exit()

    base_val = data[0]

    # 找第一个值变化的位置
    change_idx = -1
    for i in range(1, len(data)):
        if data[i] != base_val:
            change_idx = i
            break

    if change_idx == -1:
        print(f"\n  TBOX请求未发出（信号始终为 {base_val}，无变化）")
        mdf.close()
        exit()

    # 取变化点及之后共 3 帧
    end_idx = min(change_idx + 3, len(data))
    frame_count = end_idx - change_idx

    changed_values = data[change_idx:end_idx]
    changed_times = timestamps[change_idx:end_idx]

    # 计算帧间隔
    intervals = []
    for i in range(1, len(changed_times)):
        intervals.append((changed_times[i] - changed_times[i-1]) * 1000)  # ms

    print(f"\n  基准值: {base_val}")
    print(f"  变化点: 第 {change_idx+1} 帧（{changed_times[0]:.3f}s）")
    print(f"  快发帧数: {frame_count} 帧")
    for i in range(frame_count):
        print(f"    帧 {i+1}: 值={changed_values[i]}  时间={changed_times[i]:.3f}s")
    if intervals:
        avg_interval = sum(intervals) / len(intervals)
        print(f"  帧间隔: {[f'{x:.1f}ms' for x in intervals]}")
        print(f"  平均周期: {avg_interval:.1f}ms")

except Exception as e:
    print(f"\n[X] 读取失败: {e}")

mdf.close()
print(f"\n[OK] 检测完成")
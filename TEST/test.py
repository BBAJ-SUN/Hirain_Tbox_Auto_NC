import win32com.client
import time
import datetime

vba = win32com.client.Dispatch("VBACOM")

project = vba.getProjectByname("CX835KSA_ENV_test")
if project is not None:
    res = project.isStart()
    can_bus = project.getCANBusModule()
    print(can_bus.getSignalPhyVal("CAN1", 0x582, 1, "TBOX_Year"))

    #采集指定信号数据
    # network = project.getNetworkByName("CAN1", 0)
    # vbus_database = network.getDatabaseByName("TCANFD")
    # dbcSignals1 = vbus_database.getSignalsByMsg(0x614, 1)
    # dbcSignals2 = vbus_database.getSignalsByMsg(0x582, 1)
    # path = r"D:\实车半自动化\Test_AUTO\TEST\capture.mf4"
    #
    # dbcSignals = dbcSignals1 + dbcSignals2
    # res = can_bus.startCapture(dbcSignals, path)
    # print(res.getInfo())
    #
    #
    # time.sleep(10)
    #
    # res = can_bus.stopCapture(res.getInfo())
    # print(res)


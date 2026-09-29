"""
统一入口 - 远程控制工具 + 车况信号比对工具
"""
import tkinter as tk
from tkinter import ttk
import sys
import os

# 将两个工具目录加入路径
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "Remote_Control"))
sys.path.insert(0, os.path.join(BASE_DIR, "Vehicle_Condition_report"))

from remote_control_gui import RemoteControlApp
from gui_tool import ToolApp


def main():
    root = tk.Tk()
    root.title("JMC钛码平台实车测试工具v1.1")
    root.geometry("850x600")
    root.minsize(750, 500)

    notebook = ttk.Notebook(root)
    notebook.pack(fill=tk.BOTH, expand=True)

    # Tab 1: 远程控制
    tab1 = ttk.Frame(notebook)
    notebook.add(tab1, text="远程控制")
    RemoteControlApp(tab1)

    # Tab 2: 车况信号比对
    tab2 = ttk.Frame(notebook)
    notebook.add(tab2, text="车况信号比对")
    ToolApp(tab2)

    root.mainloop()


if __name__ == "__main__":
    main()
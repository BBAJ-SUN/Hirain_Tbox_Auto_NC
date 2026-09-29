# Test_AUTO — 车辆信号自动化测试工具

## 项目概述

车辆信号自动化测试工具，用于从 TSP 平台 API 获取车辆信号数据，与信号列表进行对比分析，并生成 HTML 报告。

---

## 目录结构

```
Test_AUTO/
├── config.py                # 配置文件（登录信息、API地址、VIN码）
├── api_query.py             # API 查询模块（登录、请求、解析、匹配、生成报告）
├── query_signal_report.py   # 查询脚本：API 查询 → 信号匹配 → 生成 HTML 报告
├── signal_comparison.py     # 对比分析脚本：对比 API 数据与信号列表的差异
├── merge_html_files.py      # HTML 合并脚本：将两个 HTML 按英文名称合并
├── requirements.txt         # 依赖包列表
├── README.md                # 本文件
├── .venv/                   # Python 虚拟环境
├── query_results/           # API 查询结果输出目录（自动生成）
└── comparison_results/      # 对比分析结果输出目录（自动生成）
```

---

## 功能说明

### 1. query_signal_report.py — API 数据查询 + 对比分析 + 报告生成

**流程：**
```
Selenium 登录 TSP 平台 → POST 查询 API → 解析响应数据
    ├→ 对比分析（API didCode vs 信号列表）→ 生成对比报告
    └→ 匹配信号列表 → 生成信号报告
```

**执行方式：**
```bash
python query_signal_report.py
```

**生成结果：**
- `query_results/query_result_时间戳.json` — API 原始响应数据
- `query_results/signal_report_时间戳.html` — 信号数据报告
- `comparison_results/signal_comparison_时间戳.html` — 对比分析报告

---

### 2. signal_comparison.py — 信号编号对比分析

**功能：**
对比 API 数据中的 didCode 与信号列表 Excel 中的信号编号，找出差异：
- API 有但信号列表没有的（多余）
- 信号列表有但 API 没有的（缺失）

**执行方式：**
```bash
python signal_comparison.py
```

**生成结果：**
- `comparison_results/signal_comparison_时间戳.html` — 对比分析报告（含标签页切换）

---

### 3. merge_html_files.py — HTML 报告合并

**功能：**
将两个 HTML 报告文件按"英文名称"列进行匹配合并，将第二个 HTML 的"信号值"列合并到第一个 HTML 中。

**执行方式：**
```bash
python merge_html_files.py
```

**配置：**
在 `config.py` 的 `MERGE_HTML_CONFIG` 中配置两个 HTML 文件的路径：
```python
MERGE_HTML_CONFIG = {
    "html1": r"D:\...\signal_report.html",      # 第一个HTML（TSP数据）
    "html2": r"D:\...\信号值结果.html",           # 第二个HTML（总线数据）
    "output_dir": r"D:\实车半自动化\VBA_Signal",  # 输出目录
    ...
}
```

**生成结果：**
- `D:\实车半自动化\VBA_Signal\总线与TSP数据合并_时间戳.html`

---

## 配置文件说明

### config.py

```python
LOGIN_CONFIG = {
    "url": "http://jmcoperuat.jmc.com.cn/port/welcome",  # 登录地址
    "username": "hirainuat",                               # 用户名
    "password": "prewkhp5qn",                              # 密码
}

API_QUERY_CONFIG = {
    "url": "https://jmcoperuat.jmc.com.cn/port/getData",  # API地址
    "payload": {
        "applicationId": 3,       # 应用ID
        "messageType": 7,         # 消息类型
        "vin": "LA9AEPG2XHHLJK001"  # VIN码（统一在此配置）
    }
}

SIGNAL_LIST_PATH = r"D:\PROJECT\E326\JMC-OTA-E326信号列表-20260605改.xlsx"  # 信号列表路径

SIGNAL_SHEET_NAMES = ["基础车况信号平台化", "新能源法规（新）"]  # 信号列表的sheet页名称
```

---

## 环境要求

- Python 3.7+
- Chrome 浏览器
- 内网可访问 TSP 平台

## 安装依赖

```bash
pip install -r requirements.txt
```

## 注意事项

1. 所有配置项统一在 `config.py` 中修改，无需改动其他脚本
2. 首次运行会自动下载 ChromeDriver
3. 所有 HTML 报告生成在各自对应的输出目录中
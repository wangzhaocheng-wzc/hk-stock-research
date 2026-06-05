# HK Stock Research Skill

用于 OpenClaw / Codex 的港股资讯研究 skill。它可以根据一只或多只港股代码，收集并整理行情、估值、财务、分红、新闻、港交所公告、南向资金和南向持仓等信息，并输出带来源说明的 Markdown 报告。

## 能做什么

- 查询单只港股资讯，例如 `00700` 腾讯控股。
- 批量生成多只港股报告，例如 `00700 03690 09988`。
- 从股票池文件生成每日报告。
- 输出实时/盘中快照、K 线趋势、估值分位、财务趋势、分红派息、HKEX 公告、新闻、南向资金和南向个股持仓。
- 在报告顶部生成“核心解析”，用飞书友好的方式展示核心快照、走势、相对指数、沽空、估值财务、新闻公告、南向持仓和一句话总结。
- 展示指数相对强弱、HKEX 沽空成交、南向持仓趋势和公司行动雷达。
- 增加技术面看板：MA、MACD、RSI、量能、20日支撑/压力和 0-100 技术状态评分。
- 明确显示数据来源、数据日期和失败提示。
- 不编造缺失数据；上游接口不可用时会显示 `N/A` 或错误原因。

## 安装到 OpenClaw / Codex

OpenClaw 服务器推荐安装到 `~/.openclaw/skills`：

```bash
mkdir -p ~/.openclaw/skills
git clone git@github.com:wangzhaocheng-wzc/hk-stock-research.git ~/.openclaw/skills/hk-stock-research
python3.11 -m pip install --user -r ~/.openclaw/skills/hk-stock-research/requirements.txt
```

如果使用 HTTPS：

```bash
mkdir -p ~/.openclaw/skills
git clone https://github.com/wangzhaocheng-wzc/hk-stock-research.git ~/.openclaw/skills/hk-stock-research
python3.11 -m pip install --user -r ~/.openclaw/skills/hk-stock-research/requirements.txt
```

Codex 本机使用时，可以安装到 `~/.codex/skills`：

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/wangzhaocheng-wzc/hk-stock-research.git ~/.codex/skills/hk-stock-research
python3 -m pip install --user -r ~/.codex/skills/hk-stock-research/requirements.txt
```

运行脚本需要 Python 3.8+。如果服务器默认 `python3` 太旧，可以设置 `HK_STOCK_PYTHON`：

```bash
HK_STOCK_PYTHON=python3.11 ~/.openclaw/skills/hk-stock-research/scripts/hk_research 00700
```

## 自然语言调用示例

安装后，可以在 OpenClaw / Codex 里这样说：

```text
帮我查一下 00700 的港股资讯
```

```text
生成腾讯、美团、阿里今天的港股资讯报告
```

```text
每天上午 10 点生成 00700、03690、09988 的港股资讯
```

如果只给公司名，模型需要能确认对应港股代码；不能确认时应让用户补充股票代码，不要猜。

## 命令行使用

单只股票：

```bash
~/.openclaw/skills/hk-stock-research/scripts/hk_research 00700
```

多只股票：

```bash
~/.openclaw/skills/hk-stock-research/scripts/hk_research 00700 03690 09988
```

逗号分隔股票池：

```bash
~/.openclaw/skills/hk-stock-research/scripts/hk_research --symbols 00700,03690,09988
```

写入报告目录：

```bash
~/.openclaw/skills/hk-stock-research/scripts/hk_research \
  --symbols 00700,03690,09988 \
  --output-dir ./reports
```

输出 JSON：

```bash
~/.openclaw/skills/hk-stock-research/scripts/hk_research 00700 --json
```

要求行情必须为今天：

```bash
~/.openclaw/skills/hk-stock-research/scripts/hk_research 00700 --require-today
```

如果最新行情日期不是今天，脚本会返回非 0 状态，并在报告里写明日期检查未通过。

## 资讯展示示例

下面是报告中的部分展示效果示例，实际数值会随接口返回和日期变化：

```markdown
# 港股研究快照：00700

- 生成日期：2026-06-05
- 公司：腾讯控股有限公司 / Tencent Holdings Limited
- 行业：软件服务
- 最新交易日：2026-06-05
- 收盘价：457.80 HKD
- 当日涨跌幅：-0.26%

## 价格与交易

### 实时/盘中快照
来源：新浪港股实时行情，经 AkShare `stock_hk_spot` 收集；免费源可能延迟，以数据时间为准。

- 数据时间：2026/06/05 14:33:57
- 现价/涨跌幅：455.80 HKD / -0.70%
- 买一/卖一：455.60 / 455.80
- 今日高/低：466.20 / 452.20
- 成交量/成交额：17,283,121 / 7,928,718,706

### 日线与K线趋势
- 5日/20日/60日涨跌幅：7.16% / -4.11% / -11.79%
- 5日/20日/60日均价：460.16 / 452.17 / 487.45
- 当前回看区间高/低：578 / 420.40
- 20日年化波动率：46.47%

## 估值快照
- 总市值（2026-06-04）：41,852.19｜近一年变化：-11.57%｜近一年分位：5.21%
- 市盈率(TTM)（2026-06-04）：15.72｜近一年变化：-28.02%｜近一年分位：4.93%
- 市净率（2026-06-04）：3.28｜近一年变化：-21.90%｜近一年分位：5.48%

## 资讯整理

### 信息概览
- 最新新闻：2026-06-04 21:33:00，证券时报网 报道「腾讯控股00700.HK)连续13日回购，累计斥资57.40亿港元」。
- 最新官方公告：04/06/2026 17:52，Next Day Disclosure Return，类别为 Next Day Disclosure Returns - [Share Buyback]。
- 回购相关公告：当前展示范围内识别到 4 条包含 Share Buyback / buyback 的公告。
- 风险提示关键词：当前展示范围内识别到 0 条停牌/盈利预警/诉讼/监管类关键词命中。

### 公司相关新闻
来源：东方财富个股新闻搜索，经 AkShare `stock_news_em` 收集。

1. 2026-06-04 21:33:00｜证券时报网｜腾讯控股00700.HK)连续13日回购，累计斥资57.40亿港元
   摘要：证券时报·数据宝统计，腾讯控股在港交所公告显示，6月4日回购股份...
   链接：http://finance.eastmoney.com/a/202606043760675869.html

### 港交所公告
来源：HKEXnews 官方公告标题搜索；这里只展示公告元数据和 PDF 链接，未解析 PDF 正文。

1. 04/06/2026 17:52｜Next Day Disclosure Return｜Next Day Disclosure Returns - [Share Buyback]｜PDF 90KB
   链接：https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0604/2026060401856.pdf

### 南向资金背景
来源：东方财富沪深港通资金流，经 AkShare 收集。此处为市场级数据，不代表个股专属资金流。

- 当日汇总：2026-06-05｜港股通(沪)｜成交净买额：45.23｜相关指数：恒生指数 -0.92%
- 当日汇总：2026-06-05｜港股通(深)｜成交净买额：-28.14｜相关指数：恒生指数 -0.92%

### 南向个股持仓
来源：东方财富南向持股每日个股统计，经 AkShare `stock_hsgt_stock_statistics_em` 收集；通常为 T+1 数据。

- 2026-06-04｜腾讯控股｜持股数量：1,055,696,768｜持股市值：484,564,816,512｜占发行股比例：11.57%
```

## 股票池文件

创建 `watchlist.txt`：

```text
00700 # 腾讯控股
03690 # 美团
09988 # 阿里巴巴
01810 # 小米集团
01024 # 快手
```

运行：

```bash
~/.openclaw/skills/hk-stock-research/scripts/hk_research \
  --watchlist-file ./watchlist.txt \
  --output-dir ./reports
```

输出示例：

```text
reports/
├── 00700.md
├── 03690.md
├── 09988.md
├── 01810.md
├── 01024.md
└── index.md
```

## 定时任务示例

每天 10 点生成股票池报告时，可以让 OpenClaw / Codex 创建定时任务，任务内容类似：

```bash
~/.openclaw/skills/hk-stock-research/scripts/hk_research \
  --watchlist-file /path/to/watchlist.txt \
  --output-dir /path/to/reports/$(date +%Y-%m-%d)
```

建议定时任务提示词写清楚：

```text
每天上午 10 点，根据 /path/to/watchlist.txt 里的港股代码生成资讯报告，
输出到 /path/to/reports/当天日期/。报告必须保留数据来源、链接和数据日期；
拿不到的数据标为 N/A 或写明错误原因，不要编造。
```

## 常用参数

| 参数 | 作用 |
| --- | --- |
| `--lookback-days 120` | 日线和趋势的回看自然日数 |
| `--news-limit 5` | 新闻条数 |
| `--announcement-days 31` | 港交所公告检索天数 |
| `--announcement-limit 5` | 港交所公告展示条数 |
| `--dividend-limit 5` | 分红派息展示条数 |
| `--southbound-trend-days 20` | 南向持仓趋势观察行数 |
| `--skip-short-selling` | 跳过 HKEX 沽空成交查询 |
| `--skip-index-context` | 跳过指数相对强弱查询 |
| `--output-dir ./reports` | 写入报告目录 |
| `--json` | 输出 JSON 而不是 Markdown |
| `--require-today` | 要求最新行情日期必须为今天 |
| `--require-date YYYY-MM-DD` | 要求最新行情日期必须为指定日期 |

## 报告包含的信息

- 实时/盘中快照：数据时间、现价、买一/卖一、今日高低、成交量、成交额。
- 日线与 K 线趋势：5/20/60 日涨跌幅、均线、波动率、区间高低点。
- 证券资料：上市日期、每手股数、ISIN、沪港通/深港通标的状态。
- 估值区间：总市值、PE、PB、近一年变化、近一年分位。
- 财务摘要和趋势：营收、毛利、经营溢利、股东应占溢利、同比、利润率。
- 分红派息：股息方案、除净日、派息日、股息率。
- 公司相关新闻：发布时间、来源、标题、摘要和链接。
- 港交所公告：公告时间、类型、PDF 链接、公告分类统计、风险关键词。
- 公司行动雷达：回购、业绩/财报、融资/配售、董事变动、分红和风险类公告命中。
- 南向资金：市场级港股通资金流。
- 南向个股持仓：持股数量、持股市值、占发行股比例，通常为 T+1 数据。
- 南向持仓趋势：最近可得日期的持股数量、市值和占比变化。
- 指数相对强弱：个股相对恒指、国指、恒生科技指数的 5/20 日超额表现。
- 沽空成交：HKEX 主板沽空成交股数、金额和占成交额比例。

## 数据来源与真实性说明

主要数据来源包括：

- AkShare 聚合的东方财富、百度股市通、新浪港股等公开数据。
- HKEXnews 官方公告标题搜索。
- 东方财富沪深港通资金流和南向持股统计。
- HKEX Short Selling Turnover 当前主板沽空报告。
- 新浪港股指数历史行情。

重要限制：

- 免费公开行情源可能延迟或临时不可用。
- 港交所公告目前展示标题、分类、时间和 PDF 链接，不自动解析 PDF 正文。
- 南向资金分为市场级资金流和个股持仓；市场级资金流不能解释为个股专属资金流。
- 南向持仓趋势通常为延迟数据，不能解释为实时买卖流。
- HKEX 沽空报告在盘中可能只覆盖至午间收市，需看报告标题和交易日。
- 指数相对强弱只做表现对比，不代表因果归因。
- 数据用于研究辅助，不构成投资建议或交易指令。
- 脚本不会编造数据；拿不到的数据会显示 `N/A` 或错误提示。

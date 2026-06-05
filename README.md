# HK Stock Research Skill

面向 OpenClaw / Codex 培训使用的港股资讯研究 skill。它可以根据一只或多只港股代码，收集并整理行情、估值、财务、分红、新闻、港交所公告、南向资金和南向持仓等信息，并输出带来源说明的 Markdown 报告。

## 能做什么

- 查询单只港股资讯，例如 `00700` 腾讯控股。
- 批量生成多只港股报告，例如 `00700 03690 09988`。
- 从股票池文件生成每日报告。
- 输出实时/盘中快照、K 线趋势、估值分位、财务趋势、分红派息、HKEX 公告、新闻、南向资金和南向个股持仓。
- 明确显示数据来源、数据日期和失败提示。
- 不编造缺失数据；上游接口不可用时会显示 `N/A` 或错误原因。

## 安装到 OpenClaw / Codex

把这个仓库克隆到本地 skills 目录：

```bash
mkdir -p ~/.codex/skills
git clone git@github.com:wangzhaocheng-wzc/hk-stock-research.git ~/.codex/skills/hk-stock-research
```

如果使用 HTTPS：

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/wangzhaocheng-wzc/hk-stock-research.git ~/.codex/skills/hk-stock-research
```

安装 Python 依赖：

```bash
python3 -m pip install --user akshare pandas requests
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
python3 ~/.codex/skills/hk-stock-research/scripts/hk_research.py 00700
```

多只股票：

```bash
python3 ~/.codex/skills/hk-stock-research/scripts/hk_research.py 00700 03690 09988
```

逗号分隔股票池：

```bash
python3 ~/.codex/skills/hk-stock-research/scripts/hk_research.py --symbols 00700,03690,09988
```

写入报告目录：

```bash
python3 ~/.codex/skills/hk-stock-research/scripts/hk_research.py \
  --symbols 00700,03690,09988 \
  --output-dir ./reports
```

输出 JSON：

```bash
python3 ~/.codex/skills/hk-stock-research/scripts/hk_research.py 00700 --json
```

要求行情必须为今天：

```bash
python3 ~/.codex/skills/hk-stock-research/scripts/hk_research.py 00700 --require-today
```

如果最新行情日期不是今天，脚本会返回非 0 状态，并在报告里写明日期检查未通过。

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
python3 ~/.codex/skills/hk-stock-research/scripts/hk_research.py \
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
python3 ~/.codex/skills/hk-stock-research/scripts/hk_research.py \
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
- 南向资金：市场级港股通资金流。
- 南向个股持仓：持股数量、持股市值、占发行股比例，通常为 T+1 数据。

## 数据来源与真实性说明

主要数据来源包括：

- AkShare 聚合的东方财富、百度股市通、新浪港股等公开数据。
- HKEXnews 官方公告标题搜索。
- 东方财富沪深港通资金流和南向持股统计。

重要限制：

- 免费公开行情源可能延迟或临时不可用。
- 港交所公告目前展示标题、分类、时间和 PDF 链接，不自动解析 PDF 正文。
- 南向资金分为市场级资金流和个股持仓；市场级资金流不能解释为个股专属资金流。
- 数据用于培训和研究辅助，不构成投资建议或交易指令。
- 脚本不会编造数据；拿不到的数据会显示 `N/A` 或错误提示。

## 培训建议

可以让学生完成以下观察：

- 这只股票最近的核心事件是什么？
- 新闻和港交所公告是否能相互印证？
- 当前 PE/PB 处在近一年高位还是低位？
- 南向资金是市场背景还是个股持仓？
- 哪些数据是实时数据，哪些是 T+1 或可能延迟？
- 报告中哪些部分不能作为交易依据？

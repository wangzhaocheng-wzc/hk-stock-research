---
name: hk-stock-research
description: Research Hong Kong-listed stocks with AkShare and public market data. Use when Codex or OpenClaw needs to answer natural-language requests about HK stocks, such as "查一下 00700 的资讯", "生成腾讯和美团今天的港股资讯", "每天汇总 00700 03690 09988", normalize HK tickers such as 00700/700/00700.HK/HK:700, fetch real-time/daily price action, company profile, valuation snapshots, financial statement highlights, HKEX announcements, news, dividends, Stock Connect status, southbound flow, or produce one or more Hong Kong equity research briefs.
---

# HK Stock Research

## Overview

Use this skill to produce fast, source-aware Hong Kong stock research briefs. Prefer the bundled script for deterministic data collection, then add judgment and caveats in the final narrative.

## Quick Start

Run the bundled script with a Hong Kong ticker:

```bash
python3 /Users/wik/.codex/skills/hk-stock-research/scripts/hk_research.py 00700
```

Batch examples:

```bash
python3 /Users/wik/.codex/skills/hk-stock-research/scripts/hk_research.py 00700 03690 09988
python3 /Users/wik/.codex/skills/hk-stock-research/scripts/hk_research.py --symbols 00700,03690,09988 --output-dir ./reports
python3 /Users/wik/.codex/skills/hk-stock-research/scripts/hk_research.py --watchlist-file ./watchlist.txt --output-dir ./reports
```

Useful options:

```bash
python3 /Users/wik/.codex/skills/hk-stock-research/scripts/hk_research.py HK:700 --lookback-days 90
python3 /Users/wik/.codex/skills/hk-stock-research/scripts/hk_research.py 00700 --require-today
python3 /Users/wik/.codex/skills/hk-stock-research/scripts/hk_research.py 00700 --require-date 2026-06-05
python3 /Users/wik/.codex/skills/hk-stock-research/scripts/hk_research.py 00700 --news-limit 8 --announcement-days 45 --announcement-limit 8
python3 /Users/wik/.codex/skills/hk-stock-research/scripts/hk_research.py 00700 --json
```

## Natural Language Use

When users ask in natural language, extract any HK stock codes or names, normalize codes, and run the script. Examples:

- "帮我看一下 00700 的资讯" -> run `hk_research.py 00700`
- "生成腾讯、美团、阿里的港股资讯" -> map known codes if obvious (`00700`, `03690`, `09988`) and run a batch report.
- "每天 10 点给我 00700、03690、09988 的资讯" -> create or suggest a scheduled task that runs the batch command with `--output-dir`.

If a company name cannot be confidently mapped to a HK code, ask for the code rather than guessing.

## Workflow

1. Normalize the user's ticker to a 5-digit Hong Kong code.
2. Fetch recent daily prices with AkShare `stock_hk_hist`.
3. Fetch company profile with `stock_hk_company_profile_em`.
4. Fetch valuation series with `stock_hk_valuation_baidu`.
5. Fetch annual financial statement rows with `stock_financial_hk_report_em`.
6. Fetch latest financial indicators with `stock_hk_financial_indicator_em`.
7. Fetch security profile and Stock Connect eligibility with `stock_hk_security_profile_em`.
8. Fetch dividend/payout records with `stock_hk_dividend_payout_em`.
9. Fetch recent news with AkShare `stock_news_em`.
10. Fetch official HKEXnews announcements by resolving HKEX `stockId` and calling `titleSearchServlet.do`.
11. Fetch market-level southbound Stock Connect data with `stock_hsgt_fund_flow_summary_em` and `stock_hsgt_hist_em`.
12. Summarize market action, valuation, security profile, dividends, business profile, financial highlights, news, announcements, and southbound flow.
13. Clearly label data-source limitations and avoid giving personalized investment advice.

## Interpretation Guidelines

- Treat AkShare and scraped public endpoints as research inputs, not authoritative trading infrastructure.
- When the user requires same-day data, run the script with `--require-today` or `--require-date YYYY-MM-DD` and report failure if the strict date check fails.
- Mention if a section failed because a remote endpoint was unavailable.
- HKEX announcements are official title-search results, but the script only lists titles, timestamps, categories, and PDF links; do not summarize PDF contents unless explicitly fetched and read.
- Southbound flow is market-level by default; do not describe it as stock-specific holding/flow unless a stock-specific source is added.
- Show price and trading details as dated data: open/high/low/close, turnover, volume, 5/20-day returns, period high/low, and average turnover.
- Show dividend records and Stock Connect eligibility as factual fields from the upstream source.
- For Hong Kong stocks, prioritize liquidity, southbound flow, announcements, valuation, dividend/buyback activity, and China macro sensitivity.
- Keep the final conclusion framed as research, not as a buy/sell recommendation.

## Scheduled Task Pattern

For training deployments, use a daily task that runs the script with a watchlist and output directory:

```bash
python3 /path/to/hk-stock-research/scripts/hk_research.py --watchlist-file /path/to/watchlist.txt --output-dir /path/to/reports/$(date +%Y-%m-%d)
```

Example `watchlist.txt`:

```text
00700 # Tencent
03690 # Meituan
09988 # Alibaba
01810 # Xiaomi
```

When setting a daily 10:00 task, use the student's local timezone and make the prompt/output expectation explicit: generate Markdown reports, preserve source links, and do not fabricate missing data.

## Resources

- `scripts/hk_research.py`: Fetches one or more HK stock research reports and prints Markdown/JSON or writes files with `--output-dir`.
- `references/data-sources.md`: Notes on current data-source coverage and upgrade paths.

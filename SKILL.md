---
name: hk-stock-research
description: Research Hong Kong-listed stocks with AkShare and public market data. Use when Codex or OpenClaw needs to answer natural-language requests about HK stocks, such as "查一下 00700 的资讯", "生成腾讯和美团今天的港股资讯", "每天汇总 00700 03690 09988", normalize HK tickers such as 00700/700/00700.HK/HK:700, fetch real-time/daily price action, company profile, valuation snapshots, financial statement highlights, HKEX announcements, news, dividends, Stock Connect status, southbound flow, or produce one or more Hong Kong equity research briefs.
---

# HK Stock Research

## Overview

Use this skill to produce fast, source-aware Hong Kong stock research briefs. Prefer the bundled script for deterministic data collection, then add judgment and caveats in the final narrative.

## Quick Start

Resolve paths relative to this skill directory. Do not use a developer machine's absolute path such as `/Users/...`.

The runner requires Python 3.8+. It auto-selects `python3.12`, `python3.11`, `python3.10`, `python3.9`, `python3.8`, then `python3`, or uses `HK_STOCK_PYTHON` when set. Install dependencies with the same interpreter, for example:

```bash
python3.11 -m pip install --user -r requirements.txt
```

Run the bundled wrapper from the skill directory with a Hong Kong ticker:

```bash
./scripts/hk_research 00700
```

Batch examples:

```bash
./scripts/hk_research 00700 03690 09988
./scripts/hk_research --symbols 00700,03690,09988 --output-dir ./reports
./scripts/hk_research --watchlist-file ./watchlist.txt --output-dir ./reports
```

Useful options:

```bash
./scripts/hk_research HK:700 --lookback-days 90
./scripts/hk_research 00700 --require-today
./scripts/hk_research 00700 --require-date 2026-06-05
./scripts/hk_research 00700 --news-limit 8 --announcement-days 45 --announcement-limit 8
./scripts/hk_research 00700 --json
```

## Natural Language Use

When users ask in natural language, extract any HK stock codes or names, normalize codes, and run the script. Examples:

- "帮我看一下 00700 的资讯" -> run `scripts/hk_research 00700` from this skill directory.
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
12. Fetch stock-specific southbound holding trend with `stock_hsgt_stock_statistics_em`.
13. Fetch HK index context with `stock_hk_index_daily_sina` and compare 5/20-day relative strength against HSI, HSCEI, and HSTECH.
14. Fetch HKEX current short-selling turnover and compute short turnover as a percentage of the latest stock turnover when available.
15. Structure HKEX announcement titles into company-action categories such as buybacks, financial results, financing/placing, director changes, dividends, and risk hits.
16. Summarize market action, valuation, security profile, dividends, business profile, financial highlights, news, announcements, southbound flow, short selling, and index-relative strength.
17. Clearly label data-source limitations and avoid giving personalized investment advice.

## Interpretation Guidelines

- Treat AkShare and scraped public endpoints as research inputs, not authoritative trading infrastructure.
- When the user requires same-day data, run the script with `--require-today` or `--require-date YYYY-MM-DD` and report failure if the strict date check fails.
- Mention if a section failed because a remote endpoint was unavailable.
- HKEX announcements are official title-search results, but the script only lists titles, timestamps, categories, and PDF links; do not summarize PDF contents unless explicitly fetched and read.
- Southbound flow is market-level by default; do not describe it as stock-specific holding/flow unless a stock-specific source is added.
- Southbound holding and holding trend are stock-specific, but usually delayed; do not describe them as real-time flow.
- HKEX short-selling turnover can be a half-day report during market hours; preserve the report title and trading date.
- Index-relative strength is a benchmark comparison, not an attribution model.
- Show price and trading details as dated data: open/high/low/close, turnover, volume, 5/20-day returns, period high/low, and average turnover.
- Show dividend records and Stock Connect eligibility as factual fields from the upstream source.
- For Hong Kong stocks, prioritize liquidity, southbound flow, announcements, valuation, dividend/buyback activity, and China macro sensitivity.
- Keep the final conclusion framed as research, not as a buy/sell recommendation.

## Scheduled Task Pattern

For training deployments, use a daily task that runs the script with a watchlist and output directory:

```bash
SKILL_DIR="$HOME/.openclaw/skills/hk-stock-research"
"$SKILL_DIR/scripts/hk_research" --watchlist-file /path/to/watchlist.txt --output-dir /path/to/reports/$(date +%Y-%m-%d)
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

- `scripts/hk_research`: Portable wrapper that resolves this skill directory and runs the Python collector.
- `scripts/hk_research.py`: Fetches one or more HK stock research reports and prints Markdown/JSON or writes files with `--output-dir`.
- `requirements.txt`: Python dependencies for OpenClaw/Codex hosts.
- `references/data-sources.md`: Notes on current data-source coverage and upgrade paths.

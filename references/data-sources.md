# HK Stock Data Sources

## Current Prototype

- AkShare `stock_hk_hist`: recent daily price bars from Eastmoney.
- AkShare `stock_hk_company_profile_em`: company profile fields from Eastmoney HK F10.
- AkShare `stock_hk_valuation_baidu`: valuation series from Baidu stock data.
- AkShare `stock_financial_hk_report_em`: annual Hong Kong financial statement rows from Eastmoney.
- AkShare `stock_news_em`: recent Eastmoney stock-news search results.
- HKEXnews `prefix.do` and `titleSearchServlet.do`: official listed-company announcement title search.
- AkShare `stock_hsgt_fund_flow_summary_em` and `stock_hsgt_hist_em`: market-level southbound Stock Connect summaries and history.
- AkShare `stock_hsgt_stock_statistics_em`: stock-specific southbound holding snapshots and recent trend.
- AkShare `stock_hk_index_daily_sina`: Hang Seng, HSCEI, and Hang Seng Tech index history for relative strength.
- HKEX Short Selling Turnover `MSHTMAIN.HTM`: current main-board short selling turnover text report.

## Known Limitations

- Public endpoints may fail, throttle, or change fields without warning.
- Market data may be delayed and should not be used for live trading.
- Valuation units are inherited from the upstream source; preserve the source label if unsure.
- Southbound flow is market-level in the current version, not stock-specific.
- HKEX announcement title search lists metadata and PDF links; PDF contents are not parsed automatically.
- HKEX short-selling turnover may be a half-day report during the trading day; preserve the report title and trading date.
- Southbound holding trend is based on public T+1-style rows and can be unavailable around holidays or upstream outages.

## Upgrade Path

Add these modules when the user wants a fuller research system:

- Parse HKEX announcement PDFs for buyback details, AGM resolutions, financial reports, and circular content.
- Add stock-specific southbound transaction flow from a licensed or stable source.
- Add licensed news providers or user-approved web sources.
- Watchlist batch mode with CSV output.
- Commercial data-provider adapters for production reliability.

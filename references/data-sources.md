# HK Stock Data Sources

## Current Prototype

- AkShare `stock_hk_hist`: recent daily price bars from Eastmoney.
- AkShare `stock_hk_company_profile_em`: company profile fields from Eastmoney HK F10.
- AkShare `stock_hk_valuation_baidu`: valuation series from Baidu stock data.
- AkShare `stock_financial_hk_report_em`: annual Hong Kong financial statement rows from Eastmoney.
- AkShare `stock_news_em`: recent Eastmoney stock-news search results.
- HKEXnews `prefix.do` and `titleSearchServlet.do`: official listed-company announcement title search.
- AkShare `stock_hsgt_fund_flow_summary_em` and `stock_hsgt_hist_em`: market-level southbound Stock Connect summaries and history.

## Known Limitations

- Public endpoints may fail, throttle, or change fields without warning.
- Market data may be delayed and should not be used for live trading.
- Valuation units are inherited from the upstream source; preserve the source label if unsure.
- Southbound flow is market-level in the current version, not stock-specific.
- HKEX announcement title search lists metadata and PDF links; PDF contents are not parsed automatically.

## Upgrade Path

Add these modules when the user wants a fuller research system:

- Parse HKEX announcement PDFs for buyback details, AGM resolutions, financial reports, and circular content.
- Add stock-specific southbound holdings/flow from a licensed or stable source.
- Add licensed news providers or user-approved web sources.
- Watchlist batch mode with CSV output.
- Commercial data-provider adapters for production reliability.

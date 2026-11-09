# Generality test: Sales (Snowflake TPC-H sample)

Question: can the flow be used on data that is not tickets or claims? Test data: SNOWFLAKE_SAMPLE_DATA.TPCH_SF1
(ORDERS, CUSTOMER, LINEITEM), read from another database than the one in .env. Metabase only.

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | All nine gates complete with no code edits during the run | PASS | Three fixes were made before the run (neutral example KPIs, per-workspace source database, any date column as time column). The run itself needed no further code change. |
| 2 | Design picks a time column and a month-over-month comparison | PASS, with a caveat | ORDER_MONTH chosen, month_over_month. The view already had a month column, so the daily-date path was NOT exercised. |
| 3 | Dashboard built from the approved design; QA passes | PASS | 12 of 12 KPIs matched Snowflake exactly (qa_report.md). Dashboard 11 in Metabase. |
| 4 | AI summary passes the number check | PASS | Spot-checked: top segment revenue, 100% open in recent months, returns by year, late rate by priority. |
| 5 | Chatbot answers 3 business-word questions correctly | PASS | Net sales for 1997 and high-priority buyers in 1998 recomputed from the raw TPC-H tables: both match. Backlog by segment uses the approved KPI formula. |
| 6 | Support and Claims unchanged | PASS | `facts` output identical before and after the code fixes, both subjects. |

## Findings (gaps, not fixed)
- The source schema name leaked into suggestions: the unsupported-KPI list included CSAT, response time and SLA because the view lives in a database called <DATABASE>.
- A partial last month (data ends 2 Aug 1998) makes month-over-month arrows and the last chart point misleading. Not detected by the code.
- The nation filter shows codes 0 to 24; NATION and REGION were not joined.
- "This year" in chat means the latest year in the data (a partial year).
- The summary says order age drives returns; that is how the sample data was generated, not a business finding.

## Not verified
- Dashboard on screen (API checks only).
- Whether Metabot uses the pushed column descriptions.
- A daily-only date column (no month column).
- Tableau with the code changes.
- The Metabase first-run setup scripts are not in the repository.

## Verdict
The flow worked end to end on a third, unrelated dataset in another database, on Snowflake with Metabase, with no code
change during the run. It is general-purpose for that scope. The gaps above are the next fixes.

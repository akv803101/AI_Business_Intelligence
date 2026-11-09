# QA report

Each KPI was re-computed with plain SQL straight from Snowflake and compared with the value
Metabase returns for its dashboard card (no filters), and with the expected value in the spec.
Tolerance applied: Metabase must match Snowflake within 0.000001 (stricter than exact counts / 0.01 rates).
The spec's expected values are rounded, so Snowflake is rounded to the expected value's decimals first.

| KPI | Snowflake | Metabase | Expected | Result |
|---|---|---|---|---|
| Total Orders | 1500000.0000 | 1500000.0000 | n/a | PASS |
| Net Revenue | 218102223885.0001 | 218102223885.0001 | n/a | PASS |
| Average Order Value | 145401.4826 | 145401.4826 | n/a | PASS |
| Active Customers | 99996.0000 | 99996.0000 | n/a | PASS |
| Orders per Customer | 15.0006 | 15.0006 | n/a | PASS |
| Order Fulfillment Rate | 0.4863 | 0.4863 | n/a | PASS |
| Open Order Rate | 0.4880 | 0.4880 | n/a | PASS |
| Partial Order Rate | 0.0257 | 0.0257 | n/a | PASS |
| Late Line Rate | 0.6321 | 0.6321 | n/a | PASS |
| Returned Line Rate | 0.2464 | 0.2464 | n/a | PASS |
| Average Discount (Line-Weighted) | 0.0500 | 0.0500 | n/a | PASS |
| High Priority Order Share | 0.4003 | 0.4003 | n/a | PASS |

**Overall: ALL PASS**

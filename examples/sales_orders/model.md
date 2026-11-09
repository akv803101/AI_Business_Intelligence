# Model: ORDERS_ANALYSIS

Base table: ORDERS

| Check | Result | OK |
|---|---|---|
| Base rows | 1,500,000 | yes |
| CUSTOMER.C_CUSTKEY is unique (many-to-one is safe) | 150,000 rows, 150,000 distinct | yes |
| Base rows with no CUSTOMER match | 0 (0.0%) | yes |
| Base rows with no LINEITEM rows (rollup LINEITEM_ROLLUP) | 0 (0.0%) | yes |
| Rows after joining equal base rows (no fan-out) | 1,500,000 vs 1,500,000 | yes |

SQL: model.sql. To create the view, run create_view.sql with your own rights, then: python flow.py model verify

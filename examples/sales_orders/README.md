# Worked example: sales orders (Snowflake TPC-H sample)

A finished run of the nine-step flow on Snowflake's free sample data (`SNOWFLAKE_SAMPLE_DATA.TPCH_SF1`:
ORDERS, CUSTOMER, LINEITEM). It shows what each step produces:

| File | Step |
|---|---|
| `profile.md` | 2 profile |
| `model.md`, `model.yaml`, `model.sql`, `create_view.sql` | 3 model (LINEITEM is rolled up per order; CUSTOMER is a safe many-to-one join) |
| `kpis.yaml` | 4 kpis (12 KPIs, each tested in Snowflake) |
| `semantic_model.yaml` | 5 semantic (meanings, synonyms, glossary) |
| `design.md`, `design.yaml` | 6 design |
| `narrative.md`, `qa_report.md` | 8 build (AI summary; all 12 KPIs matched Snowflake) |
| `generality_results.md` | The test: does the flow work on data that is not tickets or claims? |
| `source.env` | Raw tables read from another database (no secrets) |

Names in these files are placeholders: `<DATABASE>`, `<SCHEMA>`, `<READ_ONLY_ROLE>`. To run it yourself, make a
workspace and start at step 1:

```bash
mkdir -p workspaces/sales && cp examples/sales_orders/source.env workspaces/sales/
FLOW_WORKSPACE=sales python flow.py connect
```

Needs a Snowflake account that has the sample database (`SNOWFLAKE_SAMPLE_DATA`) and a read-only role with
`IMPORTED PRIVILEGES` on it. Your own approvals start empty; this folder is a reference, not a saved run.

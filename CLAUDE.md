# BI Flow Agent: Project Instructions

## Goal
Take a learner from "I have data in Snowflake" to a QA'd, leadership-ready dashboard plus a chatbot, in nine guided
steps, with a human approval at every step. The learner picks the BI tool (Metabase is ready; Tableau and Power BI
are planned). This is a teaching project: "this is how it is done, automated". Keep code small, readable, reusable.

## The flow (one command per step, all driven by `flow.py`)
| # | Step | What happens | Output |
|---|---|---|---|
| 1 | connect | Test the Snowflake login (read-only), list the tables | `approvals.yaml` |
| 2 | profile | One or more tables/views: columns, types, row count, date range, null rates, distinct values | `profile.json`, `profile.md` |
| 3 | model | One object: nothing to join. Several: Claude proposes a base table, many-to-one joins and rollups (or the learner edits `model.xlsx`); row-multiplication checks run in Snowflake; a `CREATE VIEW` script is written for the learner to run with their own rights, then `model verify` | `model.yaml`, `model.xlsx`, `model.sql`, `create_view.sql`, `view_profile.json` |
| 4 | kpis | Claude suggests KPIs, or the learner imports `kpis_template.xlsx`. Every formula is tested in Snowflake | `kpis.yaml`, `kpis.xlsx` |
| 5 | semantic | Claude drafts `semantic_model.xlsx` (meanings, synonyms, glossary); the learner edits; it converts to YAML | `semantic_model.yaml` |
| 6 | design | Claude proposes the dashboard layout on the 24-column grid | `design.yaml`, `design.md` |
| 7 | tool | The learner chooses the BI tool | `tool.json` |
| 8 | build | AI summary, dashboard in the chosen tool, then QA against Snowflake | `narrative.md`, `qa_report.md` |
| 9 | chatbot | The chatbot learns the semantic model (`ask`, and Metabase field descriptions for Metabot) | none |

Joins rule: never join a table that has many rows per base row (it multiplies rows and silently breaks every count).
Summarise it into a rollup at the base grain instead. Each subject (for example orders, returns) is its own model,
view and dashboard; shared dimension tables such as customers are joined into each. The agent stays read-only:
never run the `CREATE VIEW` yourself, give the script to the learner. Flag any thresholds or flags Claude invented
in derived columns (for example a score cut-off) so the learner reviews them at the gate.

Each subject has its own workspace: `FLOW_WORKSPACE=orders python flow.py <step>` keeps that subject's approvals and
files in `workspaces/orders/` (also for `build_dashboard.py`). With no variable, the project root is the workspace.
`python flow.py status` shows where the learner is. `python flow.py reset <step|all> [--yes]` starts again from a step
(archives files, nothing is deleted; without `--yes` it only shows what would change). Command list: top of `flow.py`.

## Hard rules
1. **Approval gate at every step.** After a step runs, show the result and STOP. Run `python flow.py approve <step>`
   only after the learner says in chat that they approve. Never approve for them. Never skip or reorder steps; the
   code refuses to run a step until the previous one is approved.
2. **Credentials**: read only from `.env`. Never print, log, echo or commit secrets (not even in an error message:
   do not echo a command whose failure could print a key). `.env` must be in `.gitignore`.
3. **Read-only data access**: the Snowflake user is read-only. Never run DDL/DML. Generated SQL must be a single SELECT.
4. **No browser driving.** Everything goes through APIs. Verify by API, and tell the learner you have not looked at
   the dashboard on screen.
5. **QA gate**: every KPI is re-computed with plain SQL straight from Snowflake and compared with the value the BI tool
   returns. Do not report success if any KPI differs.
6. **Check AI-written numbers.** Text written by Claude (summary card, chat answers) must pass the number check (every
   number is a rounding of a real value). Spot-check claims against Snowflake before telling the learner they are right.
7. **Generic design**: nothing dataset-specific in code. KPIs, filters, layout, meanings and caveats come from the
   approved files. `examples/` holds finished worked runs.
8. **Strict scope**: do only what the current step describes. No extra dashboards, files or "helpful additions".
9. **Report faithfully**: say what was not verified, what failed, and what was skipped.

## Learner inputs
- `.env` (copy `.env.example`): Snowflake and Metabase admin settings, `ANTHROPIC_API_KEY`. Never ask the learner to
  paste a secret into chat.
- Optional: `kpis_template.xlsx` (their own KPIs and formulas), edits to `semantic_model.xlsx`.

## Metabase API notes
- Check the running version at `/api/session/properties` before coding; field names change across versions.
- Auth header: `X-API-KEY: <key>`. First run: `/api/setup`, then create a key with `/api/api-key`, save it in `.env`.
- Layout: PUT `/api/dashboard/:id` with a `dashcards` array (negative `id` for new cards, `card_id`, `row`, `col`,
  `size_x`, `size_y`, `parameter_mappings`, `visualization_settings`). Text cards use `visualization_settings.virtual_card`.
- Dashboard filters need a `dimension` template-tag on the SQL; filter type `string` must be sent as `string/=`.
- KPI tiles are `scalar` cards showing the overall value, with the month-over-month change and an arrow in the title.
- Metabot (Metabase's AI assistant) is configured by the learner in Admin settings, AI. Never type their API key.

## Design standards
- One accent colour for primary series; grey for context; red/amber only for threshold breaches (never colour alone:
  add arrows or labels).
- No chart clutter: minimal gridlines, no 3D, readable labels, consistent number formats (percent with 1 decimal,
  minutes with 1 decimal, counts with thousands separators).
- Chart titles state what the chart shows, with units. A target is drawn as a goal line only if the KPI has one.
- Top-left holds the most important KPI. Header shows title and data period; footer shows caveats.

## Definition of done (per run of the flow)
All nine gates approved, dashboard exists and matches the approved design, QA all pass, `qa_report.md` written,
dashboard URL given, no secrets in any file.

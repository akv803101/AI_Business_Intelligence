# AI Business Intelligence: from Snowflake data to a QA'd dashboard and a chatbot

A guided, automated flow. You bring data in Snowflake; Claude Code runs nine steps, and **you approve every step**
before the next one runs. The result is a leadership-ready Metabase dashboard whose numbers are checked against
Snowflake, an AI-written summary whose numbers are checked too, and a chatbot that answers questions in your own
business words.

| # | Step | What happens |
|---|---|---|
| 1 | connect | Test the read-only Snowflake login, list the tables |
| 2 | profile | Columns, types, row counts, date range, null rates |
| 3 | model | Safe joins (never one-to-many); you run the `CREATE VIEW` script |
| 4 | kpis | Claude suggests KPIs, or import your own Excel list; every formula is tested |
| 5 | semantic | Meanings, synonyms and a glossary in Excel, converted to YAML |
| 6 | design | Dashboard layout on a 24-column grid |
| 7 | tool | Choose the BI tool (Metabase is ready) |
| 8 | build | AI summary, dashboard, then QA against Snowflake |
| 9 | chatbot | Ask questions in plain words; Metabot gets the meanings too |

## What you need
- A Snowflake account and a **read-only** role and user (the agent never writes to Snowflake).
- Docker (runs Metabase locally).
- Python 3.9 or newer.
- An Anthropic API key (for the summary and the chatbot).
- [Claude Code](https://claude.com/claude-code), to run the project the guided way.

## Set up
```bash
pip install -r requirements.txt
cp .env.example .env        # then fill it in. Never commit .env and never paste its values into chat.
docker compose up -d        # Metabase on http://localhost:3000
```

Then open this folder in Claude Code and paste `STARTER_PROMPT.md` (fill in your table or view name).
`CLAUDE.md` holds the rules Claude follows: approval at every step, read-only data, QA before success.

## Run it yourself
```bash
python flow.py status                 # where am I?
python flow.py connect                # then: python flow.py approve connect
python flow.py profile <TABLE> [TABLE ...]
```
The full command list is at the top of `flow.py`. `python flow.py reset <step|all>` starts again from a step
(files are archived, nothing is deleted).

## Several subjects
Each subject (for example orders, claims) gets its own workspace:
`FLOW_WORKSPACE=orders python flow.py <step>` keeps its files in `workspaces/orders/`.
If the raw tables live in a different database or schema than your `.env`, put `SOURCE_DATABASE` and
`SOURCE_SCHEMA` (no secrets) in `workspaces/<name>/source.env`. Views and dashboards always use the `.env` ones.

## Good to know
- Joins: a table with many rows per base row is summarised first (a rollup), because joining it directly
  silently multiplies rows and breaks every count.
- Every derived flag or threshold that Claude invents is shown to you at the gate to review.
- Dashboards are built and checked through APIs. Look at them on screen before you share them.
- Tableau: `tableau_build.py` generates a workbook from the approved design. It needs a template workbook on your
  published data source and a Claude session with the Tableau connector, and it is not part of `flow.py build`.
  Power BI is not built.
- `dashboard_spec.yaml` is the worked example from the first version of this project.

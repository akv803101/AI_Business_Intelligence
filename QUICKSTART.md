# Quick start: your first run on Snowflake's free sample data

No data of your own yet? Run the whole flow on Snowflake's free TPC-H sample (orders, customers, order lines).
You will end up with a checked dashboard and a chatbot, and you will have seen every gate once.
Allow about an hour the first time; the large sample tables take a while to profile.

## 1. Snowflake (once)

1. In a Snowflake worksheet, open `snowflake_setup.sql`, **change the password**, and run the whole script as
   ACCOUNTADMIN. It creates a read-only role (`BI_READER`), a user (`BI_AGENT`), a warehouse (`BI_WH`), a database
   (`BI_DEMO`) and schema (`BI`), and gives the role access to the sample data.
2. Check that the sample data is visible:
   ```sql
   SELECT COUNT(*) FROM SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.ORDERS;   -- 1,500,000
   ```
   If your account has no sample data share, use your own tables instead and skip step 4 below.

## 2. Get the project

On GitHub click **Use this template**, then clone your copy and open the folder in a terminal.

## 3. Set up (one command)

```bash
python setup.py
```

It installs the packages, asks for your settings (account, `BI_AGENT`, password, `BI_WH`, `BI_DEMO`, `BI`,
`BI_READER`, a Metabase admin email and password you choose, and your Anthropic key), starts Metabase in Docker,
does the one-time Metabase setup, and runs `python flow.py doctor`. Fix anything marked FAIL and run it again;
it skips what is already done.

## 4. Point a workspace at the sample data

The sample tables live in another database, so tell the flow where to read them from:

```bash
mkdir -p workspaces/sales
printf 'SOURCE_DATABASE=SNOWFLAKE_SAMPLE_DATA\nSOURCE_SCHEMA=TPCH_SF1\n' > workspaces/sales/source.env
export FLOW_WORKSPACE=sales
```

(On Windows PowerShell use `$env:FLOW_WORKSPACE="sales"`.) Every command below then works inside that workspace.

## 5. Run the flow, one gate at a time

**Guided:** open the folder in Claude Code and paste `STARTER_PROMPT.md`. Use `ORDERS CUSTOMER LINEITEM` as the
tables and Metabase as the tool. Claude runs one step, shows the result and waits for your "approve".

**By hand:**

```bash
python flow.py connect      # read the result, then:  python flow.py approve connect
python flow.py profile ORDERS CUSTOMER LINEITEM
python flow.py approve profile
python flow.py model suggest
```

`model suggest` writes `create_view.sql`. **You** run that script in a Snowflake worksheet with your admin role (the
agent's role is read-only on purpose). Then:

```bash
python flow.py model verify
python flow.py approve model
python flow.py kpis suggest     # then approve kpis
python flow.py semantic draft   # edit semantic_model.xlsx if you like, then:
python flow.py semantic convert # then approve semantic
python flow.py design           # then approve design
python flow.py tool metabase    # then approve tool
python flow.py build            # then approve build
python flow.py chatbot          # then approve chatbot
```

Read each result before you approve. That is the point of the gates.

## 6. See the result

Open http://localhost:3000, log in with the admin email and password you chose, and open the new dashboard.
Compare with `examples/sales_orders/`, a finished run. Your KPIs and layout will differ a little, because Claude's
suggestions are not identical every time.

## If something goes wrong

- `python flow.py doctor` says what is wrong and what to run.
- `python flow.py status` shows where you are; `python flow.py reset <step> --yes` starts again from a step.
- More in the Troubleshooting table of the README.

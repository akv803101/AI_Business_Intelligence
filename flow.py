"""Guided BI flow: connect -> profile -> model -> KPIs -> semantic model -> design -> tool -> build -> chatbot.

Every step must be approved before the next one runs.

  python flow.py init                   # ask for your settings and write .env (once, before step 1)
  python flow.py doctor                 # check the setup: Docker, Metabase, Snowflake login, keys
  python flow.py status                 # show each step and its gate
  python flow.py connect                # test the Snowflake connection and list the tables
  python flow.py profile <T1> [T2 ...]  # profile one or more tables/views (profile.json, profile.md)
  python flow.py model suggest [BASE]   # one object: nothing to join. Several: Claude proposes joins and rollups
  python flow.py model import <file>    # or load your own model.xlsx; both run the row-multiplication checks
  python flow.py model verify           # after you run create_view.sql, check the view and use it from here on
  python flow.py kpis suggest           # Claude proposes KPIs (also writes kpis.xlsx to edit)
  python flow.py kpis template          # blank kpis_template.xlsx for your own KPI list
  python flow.py kpis import <file>     # load your KPI Excel; formulas are tested in Snowflake
  python flow.py semantic draft         # Claude drafts semantic_model.xlsx (meanings, synonyms, glossary)
  python flow.py semantic convert       # semantic_model.xlsx -> semantic_model.yaml, with checks
  python flow.py design                 # Claude proposes the dashboard layout (design.yaml, design.md)
  python flow.py tool [name]            # list BI tools, or choose one (metabase is ready)
  python flow.py build                  # AI summary + dashboard in the chosen tool + QA against Snowflake
  python flow.py chatbot                # chatbot learns the semantic model; tested with business words
  python flow.py reset <step|all> [--yes] # start again from a step: clears its gate and later ones, archives files
  python flow.py approve <step>         # record your approval of a finished step

Credentials come from .env only; Snowflake access is read-only.
"""
import datetime, json, os, sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
# Each subject (for example orders, returns) can have its own workspace: FLOW_WORKSPACE=orders keeps its approvals and
# files in workspaces/orders/. Without it, the project root is the workspace. Code and .env always stay in the root.
WORK = os.path.join(HERE, "workspaces", os.environ["FLOW_WORKSPACE"]) if os.environ.get("FLOW_WORKSPACE") else HERE
os.makedirs(WORK, exist_ok=True)
STEPS = ["connect", "profile", "model", "kpis", "semantic", "design", "tool", "build", "chatbot"]
GATES = os.path.join(WORK, "approvals.yaml")


# ---------------------------------------------------------------- gates
def load_gates():
    return yaml.safe_load(open(GATES)) if os.path.exists(GATES) else {}


def save_gates(g):
    yaml.safe_dump(g, open(GATES, "w"), sort_keys=False)


def require(step):
    """Stop unless every step before `step` is approved."""
    g = load_gates()
    for s in STEPS[:STEPS.index(step)]:
        if not g.get(s, {}).get("approved"):
            sys.exit(f"Step '{s}' is not approved yet. Finish and approve it before running '{step}'.")


def done(step, note):
    g = load_gates()
    g[step] = {"done": datetime.datetime.now().isoformat(timespec="seconds"), "approved": None, "note": note}
    save_gates(g)
    print(f"\nStep '{step}' finished. Review it, then approve with: python flow.py approve {step}")


def approve(step):
    g = load_gates()
    if step not in STEPS:
        sys.exit(f"Unknown step. Choose from: {', '.join(STEPS)}")
    if not g.get(step, {}).get("done"):
        sys.exit(f"Step '{step}' has not been run yet.")
    if step == "model":
        m = yaml.safe_load(open(os.path.join(WORK, "model.yaml")))
        if not m.get("single") and not os.path.exists(os.path.join(WORK, "view_profile.json")):
            sys.exit("Create the view (run create_view.sql with your own rights), then run: python flow.py model verify")
    g[step]["approved"] = datetime.datetime.now().isoformat(timespec="seconds")
    save_gates(g)
    print(f"Approved: {step}")


STEP_FILES = {"profile": ["profile.json", "profile.md"],
              "model": ["model.yaml", "model.xlsx", "model.sql", "create_view.sql", "model.md", "view_profile.json"],
              "kpis": ["kpis.yaml", "kpis.xlsx"],
              "semantic": ["semantic_model.xlsx", "semantic_model.yaml"], "design": ["design.yaml", "design.md"],
              "tool": ["tool.json"], "build": ["narrative.md", "qa_report.md"]}


def reset(step, confirmed):
    """Start again from `step`: clear its gate and every later gate, and archive their files (nothing is deleted)."""
    if step != "all" and step not in STEPS:
        sys.exit(f"Choose a step ({', '.join(STEPS)}) or 'all'.")
    later = STEPS if step == "all" else STEPS[STEPS.index(step):]
    g, files = load_gates(), [f for s in later for f in STEP_FILES.get(s, []) if os.path.exists(os.path.join(WORK, f))]
    print(f"Reset from '{later[0]}': clears the gates for {', '.join(s for s in later if s in g) or 'nothing'}.")
    print("Files moved to archive/: " + (", ".join(files) or "none"))
    print("Not touched: .env, Snowflake, and dashboards already built in the BI tool (remove those there).")
    if not confirmed:
        sys.exit("Nothing changed. Run again with --yes to do it.")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(WORK, "archive", stamp)
    os.makedirs(dest, exist_ok=True)
    for f in files:
        os.rename(os.path.join(WORK, f), os.path.join(dest, f))
    for s in later:
        g.pop(s, None)
    save_gates(g)
    print(f"Done. Archived to archive/{stamp}. Next: run the '{later[0]}' step again (commands are listed at the top of flow.py).")


def status():
    g = load_gates()
    for s in STEPS:
        e = g.get(s, {})
        state = "APPROVED" if e.get("approved") else "waiting for approval" if e.get("done") else "not run"
        print(f"  {s:<10} {state:<22} {e.get('note', '')}")


# ---------------------------------------------------------------- snowflake
def load_env(path=os.path.join(HERE, ".env")):
    env = {}
    for line in open(path):
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.rstrip("\n").split("=", 1)
            env[k] = v
    # Optional workspace file source.env: SOURCE_DATABASE / SOURCE_SCHEMA say where the raw tables live when that is
    # not the .env database and schema. Views and dashboards always use the .env ones. No secrets in this file.
    own = os.path.join(WORK, "source.env")
    if os.path.exists(own):
        for line in open(own):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.strip().split("=", 1)
                if k in ("SOURCE_DATABASE", "SOURCE_SCHEMA"):
                    env[k] = v
    return env


def src(e):
    """(database, schema) of the raw tables: source.env if the workspace has one, else the .env defaults."""
    return e.get("SOURCE_DATABASE") or e["SNOWFLAKE_DATABASE"], (e.get("SOURCE_SCHEMA") or e["SNOWFLAKE_SCHEMA"]).upper()


def connect_snowflake():
    import snowflake.connector
    e = load_env()
    return snowflake.connector.connect(
        account=e["SNOWFLAKE_ACCOUNT"].strip().removeprefix("https://").removesuffix("/").removesuffix(".snowflakecomputing.com"),
        user=e["SNOWFLAKE_USER"], password=e["SNOWFLAKE_PASSWORD"], warehouse=e["SNOWFLAKE_WAREHOUSE"],
        role=e["SNOWFLAKE_ROLE"], database=e["SNOWFLAKE_DATABASE"], schema=e["SNOWFLAKE_SCHEMA"]), e


def query(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchall()


# ---------------------------------------------------------------- steps
def connect():
    require("connect")
    conn, e = connect_snowflake()
    cur = conn.cursor()
    who = query(cur, "SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE()")[0]
    sdb, sschema = src(e)
    tables = query(cur, f"SELECT TABLE_NAME, TABLE_TYPE, ROW_COUNT FROM {sdb}.INFORMATION_SCHEMA.TABLES "
                        "WHERE TABLE_SCHEMA = %s ORDER BY TABLE_NAME", (sschema,))
    print(f"Connected as user {who[0]}, role {who[1]}, warehouse {who[2]}")
    print(f"Objects in {sdb}.{sschema}:")
    for name, kind, rows in tables:
        print(f"  {name:<20} {kind:<10} {rows if rows is not None else '-'} rows")
    done("connect", f"{len(tables)} objects visible")


def profile(*views):
    """Profile one or more tables/views. One object keeps the original profile.json shape."""
    require("profile")
    conn, e = connect_snowflake()
    cur = conn.cursor()
    objs, md = [], []
    for v in views:
        o, lines = profile_one(cur, e, v)
        objs.append(o)
        md += lines + [""]
    out = {"objects": objs}
    if len(objs) == 1:
        out.update(objs[0])
    json.dump(out, open(os.path.join(WORK, "profile.json"), "w"), indent=1)
    open(os.path.join(WORK, "profile.md"), "w").write("\n".join(md))
    print("\n".join(md))
    done("profile", ", ".join(f"{o['source'].split('.')[-1]}: {o['rows']:,} rows, {len(o['columns'])} columns"
                              for o in objs))


def active_profile():
    """The profile later steps use: the verified model view if there is one, else the single profiled object."""
    vp = os.path.join(WORK, "view_profile.json")
    if os.path.exists(vp):
        return json.load(open(vp))
    p = json.load(open(os.path.join(WORK, "profile.json")))
    objs = p.get("objects")
    if objs and len(objs) > 1:
        sys.exit("Several tables are profiled. Finish the model step (create the view, then 'model verify') first.")
    return objs[0] if objs else p


def profile_one(cur, e, view, raw=True):
    db, schema = src(e) if raw else (e["SNOWFLAKE_DATABASE"], e["SNOWFLAKE_SCHEMA"].upper())
    view = view.upper()
    full = f"{db}.{schema}.{view}"
    cols = query(cur, f"SELECT COLUMN_NAME, DATA_TYPE FROM {db}.INFORMATION_SCHEMA.COLUMNS "
                      "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION", (schema, view))
    if not cols:
        sys.exit(f"No columns found for {full}. Check the name with: python flow.py connect")
    n = query(cur, f"SELECT COUNT(*) FROM {full}")[0][0]
    out = {"source": full, "rows": n, "columns": []}
    for name, typ in cols:
        nulls, distinct = query(cur, f'SELECT COUNT_IF("{name}" IS NULL), COUNT(DISTINCT "{name}") FROM {full}')[0]
        col = {"name": name, "type": typ, "null_rate": round(nulls / n, 4) if n else None, "distinct": distinct}
        if typ in ("DATE", "TIMESTAMP_NTZ", "TIMESTAMP_LTZ", "TIMESTAMP_TZ", "NUMBER", "FIXED", "FLOAT", "REAL"):
            lo, hi = query(cur, f'SELECT MIN("{name}"), MAX("{name}") FROM {full}')[0]
            col["min"], col["max"] = str(lo), str(hi)
        if typ in ("TEXT", "VARCHAR") and 0 < distinct <= 20:
            col["values"] = {str(v): c for v, c in query(cur, f'SELECT "{name}", COUNT(*) FROM {full} '
                                                              f'GROUP BY 1 ORDER BY 2 DESC')}
        out["columns"].append(col)
    lines = [f"# Profile of {full}", "", f"Rows: {n:,}", "",
             "| Column | Type | Null rate | Distinct | Range or values |", "|---|---|---|---|---|"]
    for c in out["columns"]:
        extra = f"{c['min']} to {c['max']}" if "min" in c else ", ".join(f"{k} ({v})" for k, v in c.get("values", {}).items())
        lines.append(f"| {c['name']} | {c['type']} | {c['null_rate']:.1%} | {c['distinct']:,} | {extra} |")
    return out, lines


KPI_FILE = os.path.join(WORK, "kpis.yaml")
KPI_COLS = ["id", "name", "definition", "sql", "format", "target", "target_note"]
FORMATS = "integer, percent, minutes, decimal2"


def ask_claude(prompt):
    import urllib.request, urllib.error
    e = load_env()
    if not e.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is empty in .env")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", method="POST",
        data=json.dumps({"model": e.get("ANTHROPIC_MODEL", "claude-sonnet-5-5"), "max_tokens": 8000,
                         "messages": [{"role": "user", "content": prompt}]}).encode(),
        headers={"content-type": "application/json", "x-api-key": e["ANTHROPIC_API_KEY"],
                 "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=240) as r:
            out = json.loads(r.read())
    except urllib.error.HTTPError as err:
        sys.exit(f"Claude API -> {err.code}: {err.read().decode()[:300]}")
    if out.get("stop_reason") == "max_tokens":
        sys.exit("Claude response was cut off (max_tokens)")
    return "".join(b["text"] for b in out["content"] if b["type"] == "text")


def show(v, fmt):
    return {"percent": f"{v:.1%}", "integer": f"{v:,.0f}", "minutes": f"{v:,.1f}"}.get(fmt, f"{v:,.2f}")


def validate(cur, source, kpis):
    """Run each KPI formula in Snowflake (read-only). Fills k['value']; returns {id: error} for failures."""
    bad = {}
    for k in kpis:
        try:
            v = query(cur, f"SELECT {k['sql']} FROM {source}")[0][0]
            if v is None:
                raise ValueError("returned no value")
            k["value"] = round(float(v), 4)
        except Exception as ex:
            k.pop("value", None)
            bad[k["id"]] = str(ex).splitlines()[0][:160]
    return bad


def save_kpis(source, kpis, unsupported):
    import openpyxl
    yaml.safe_dump({"source": source, "status": "proposed", "kpis": kpis, "unsupported": unsupported},
                   open(KPI_FILE, "w"), sort_keys=False, allow_unicode=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "KPIs"
    ws.append(KPI_COLS)
    for k in kpis:
        ws.append([k.get(c) for c in KPI_COLS])
    wb.save(os.path.join(WORK, "kpis.xlsx"))
    print(f"\nKPIs for {source}\n")
    print(f"  {'KPI':<28} {'Value':>10}  Definition")
    for k in kpis:
        print(f"  {k['name']:<28} {show(k['value'], k['format']):>10}  {k['definition']}")
    for u in unsupported:
        print(f"  Not supported by this data: {u['name']} ({u['reason']})")
    done("kpis", f"{len(kpis)} KPIs proposed in kpis.yaml / kpis.xlsx")


def kpis_suggest():
    require("kpis")
    prof = active_profile()
    brief = {"source": prof["source"], "rows": prof["rows"], "columns": [
        {k: v for k, v in c.items() if k in ("name", "type", "null_rate", "min", "max", "values")}
        for c in prof["columns"]]}
    prompt = (
        "You are a BI analyst. Propose KPIs for a leadership dashboard from this data profile.\n"
        "Return JSON only, shaped as {\"kpis\": [{\"id\", \"name\", \"definition\", \"sql\", \"format\", "
        "\"target\", \"target_note\"}], \"unsupported\": [{\"name\", \"reason\"}]}.\n"
        f"Rules: 8 to 12 KPIs. sql is ONE Snowflake aggregate expression over the columns below with no FROM "
        f"clause (example: SUM(IS_X)/NULLIF(COUNT(DISTINCT ID),0)). Use only columns that exist. Rates are "
        f"fractions. format is one of: {FORMATS}. definition is one plain sentence. Add target and target_note "
        "only when a target is obvious from the data, otherwise leave them null. In unsupported, list common KPIs "
        "for this domain that the data cannot support, with the reason.\n\nPROFILE:\n" + json.dumps(brief))
    conn, _ = connect_snowflake()
    cur, feedback = conn.cursor(), ""
    for _ in range(3):
        text = ask_claude(prompt + feedback).strip()
        text = text[text.index("{"): text.rindex("}") + 1]
        data = json.loads(text)
        bad = validate(cur, prof["source"], data["kpis"])
        if not bad:
            break
        feedback = f"\n\nThese formulas failed in Snowflake, fix them: {json.dumps(bad)}"
    else:
        sys.exit(f"Some formulas still fail after 3 tries: {bad}")
    save_kpis(prof["source"], data["kpis"], data.get("unsupported", []))


def kpis_template():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "KPIs"
    ws.append(KPI_COLS)
    ws.append(["row_count", "Rows", "Number of rows", "COUNT(*)", "integer", None, None])
    try:  # a second example built from the profiled data: the average of its first numeric column
        num = next(c["name"] for c in active_profile()["columns"] if c["type"] in ("NUMBER", "FIXED", "FLOAT", "REAL"))
        ws.append([f"avg_{num.lower()}", f"Average {num.lower()}", f"Average of {num}", f"AVG({num})", "decimal2", None, None])
    except (StopIteration, OSError, KeyError, SystemExit):
        pass
    h = wb.create_sheet("Help")
    for line in ["One KPI per row on the KPIs sheet. Replace the example rows with your own.",
                 "sql: ONE Snowflake aggregate expression over your view's columns, with no FROM clause.",
                 f"format: one of {FORMATS}.", "target and target_note are optional.",
                 "Then run: python flow.py kpis import <your file>.xlsx"]:
        h.append([line])
    wb.save(os.path.join(WORK, "kpis_template.xlsx"))
    print("Wrote kpis_template.xlsx. Fill it in, then: python flow.py kpis import <file>.xlsx")


def kpis_import(path):
    import openpyxl
    require("kpis")
    prof = active_profile()
    rows = list(openpyxl.load_workbook(path)["KPIs"].iter_rows(values_only=True))
    head, kpis = [str(h).strip() for h in rows[0]], []
    for r in rows[1:]:
        if r and r[0]:
            k = {h: v for h, v in zip(head, r) if h in KPI_COLS and v is not None}
            kpis.append(k)
    missing = [k.get("id", "?") for k in kpis if not all(k.get(c) for c in ("id", "name", "sql", "format"))]
    if missing:
        sys.exit(f"Rows missing id, name, sql or format: {missing}")
    conn, _ = connect_snowflake()
    bad = validate(conn.cursor(), prof["source"], kpis)
    if bad:
        sys.exit("These formulas failed in Snowflake:\n" + "\n".join(f"  {k}: {v}" for k, v in bad.items()))
    for k in kpis:
        k.setdefault("definition", k["name"])
    save_kpis(prof["source"], kpis, [])


SEM_XLSX, SEM_YAML = os.path.join(WORK, "semantic_model.xlsx"), os.path.join(WORK, "semantic_model.yaml")
ROLES = "identifier, dimension, measure, flag, date"


def semantic_draft():
    """Claude drafts the semantic model into semantic_model.xlsx; the learner edits it, then runs `convert`."""
    import openpyxl
    require("semantic")
    prof = active_profile()
    kp = yaml.safe_load(open(KPI_FILE))
    table = prof["source"].split(".")[-1]
    brief = {"source": prof["source"], "rows": prof["rows"], "columns": [
        {k: v for k, v in c.items() if k in ("name", "type", "min", "max", "values")} for c in prof["columns"]],
        "kpis": [{f: k.get(f) for f in ("id", "name", "definition", "sql", "value")} for k in kp["kpis"]]}
    prompt = (
        "You write the semantic model (business meaning of the data) for a BI project. Return JSON only:\n"
        "{\"table\": {\"description\", \"grain\"}, \"columns\": [{\"column\", \"role\", \"description\", "
        "\"synonyms\": []}], \"metrics\": [{\"id\", \"description\", \"synonyms\": []}], "
        "\"glossary\": [{\"term\", \"meaning\"}]}.\n"
        f"Rules: one entry for EVERY column, using the exact column names; role is one of: {ROLES}. Describe only what "
        "the names, types, values and KPI results support. Where a meaning is a guess, end the text with "
        "\"(assumed)\". synonyms are words a business user might type. Glossary: 6 to 10 business terms "
        "(for example how a key status or flag is defined), grounded in the data. Keep each text under 25 words.\n\n"
        + json.dumps(brief))
    d = json.loads((t := ask_claude(prompt))[t.index("{"): t.rindex("}") + 1])
    names = {c["name"] for c in prof["columns"]}
    unknown = [c["column"] for c in d["columns"] if c["column"] not in names]
    if unknown:
        sys.exit(f"Claude named columns that do not exist: {unknown}")
    by_col, by_met = {c["column"]: c for c in d["columns"]}, {m["id"]: m for m in d["metrics"]}
    wb = openpyxl.Workbook()
    sheets = {
        "Tables": (["table", "description", "grain"], [[table, d["table"]["description"], d["table"]["grain"]]]),
        "Columns": (["table", "column", "type", "role", "description", "synonyms"],
                    [[table, c["name"], c["type"], by_col.get(c["name"], {}).get("role"),
                      by_col.get(c["name"], {}).get("description"),
                      ", ".join(by_col.get(c["name"], {}).get("synonyms", []))] for c in prof["columns"]]),
        "Metrics": (["id", "name", "description", "sql", "synonyms"],
                    [[k["id"], k["name"], by_met.get(k["id"], {}).get("description", k["definition"]), k["sql"],
                      ", ".join(by_met.get(k["id"], {}).get("synonyms", []))] for k in kp["kpis"]]),
        "Relationships": (["from_table", "from_column", "to_table", "to_column", "type"], []),
        "Glossary": (["term", "meaning"], [[g["term"], g["meaning"]] for g in d["glossary"]]),
    }
    wb.remove(wb.active)
    for name, (head, rows) in sheets.items():
        ws = wb.create_sheet(name)
        ws.append(head)
        for r in rows:
            ws.append(r)
    wb.save(SEM_XLSX)
    print(f"Wrote semantic_model.xlsx: {len(prof['columns'])} columns, {len(kp['kpis'])} metrics, "
          f"{len(d['glossary'])} glossary terms. Edit it in Excel, then: python flow.py semantic convert")


def semantic_convert():
    """Excel -> semantic_model.yaml, with checks against the profile and the approved KPIs."""
    import openpyxl
    require("semantic")
    prof = active_profile()
    kp = yaml.safe_load(open(KPI_FILE))
    wb = openpyxl.load_workbook(SEM_XLSX)

    def rows(sheet):
        r = list(wb[sheet].iter_rows(values_only=True))
        head = [str(h).strip() for h in r[0]]
        return [dict(zip(head, x)) for x in r[1:] if any(v not in (None, "") for v in x)]
    syn = lambda s: [w.strip() for w in str(s or "").split(",") if w.strip()]
    errors, warnings = [], []
    cols = rows("Columns")
    names = {c["name"] for c in prof["columns"]}
    for c in cols:
        if c["column"] not in names:
            errors.append(f"Columns: '{c['column']}' is not in the profiled view")
        if c["role"] not in ROLES.split(", "):
            errors.append(f"Columns: '{c['column']}' has role '{c['role']}', expected one of {ROLES}")
        if not c.get("description"):
            warnings.append(f"Columns: '{c['column']}' has no description")
    missing = names - {c["column"] for c in cols}
    errors += [f"Columns: '{m}' is missing" for m in sorted(missing)]
    approved = {k["id"] for k in kp["kpis"]}
    metrics = rows("Metrics")
    errors += [f"Metrics: '{m['id']}' is not an approved KPI" for m in metrics if m["id"] not in approved]
    errors += [f"Metrics: approved KPI '{i}' is missing" for i in sorted(approved - {m["id"] for m in metrics})]
    if errors:
        sys.exit("Fix these in semantic_model.xlsx:\n" + "\n".join(f"  - {e}" for e in errors))
    t = rows("Tables")[0]
    out = {"source": prof["source"], "status": "proposed",
           "tables": [{"name": t["table"], "description": t["description"], "grain": t["grain"],
                       "columns": [{"name": c["column"], "type": c["type"], "role": c["role"],
                                    "description": c.get("description"), "synonyms": syn(c.get("synonyms"))}
                                   for c in cols]}],
           "metrics": [{"id": m["id"], "name": m["name"], "description": m.get("description"), "sql": m["sql"],
                        "synonyms": syn(m.get("synonyms"))} for m in metrics],
           "relationships": [{k: r.get(k) for k in ("from_table", "from_column", "to_table", "to_column", "type")}
                             for r in rows("Relationships")],
           "glossary": [{"term": g["term"], "meaning": g["meaning"]} for g in rows("Glossary")]}
    yaml.safe_dump(out, open(SEM_YAML, "w"), sort_keys=False, allow_unicode=True)
    for w in warnings:
        print("  warning:", w)
    print(f"Wrote semantic_model.yaml: {len(cols)} columns, {len(metrics)} metrics, "
          f"{len(out['glossary'])} glossary terms, {len(out['relationships'])} relationships")
    done("semantic", f"semantic_model.yaml with {len(cols)} columns, {len(metrics)} metrics")


DESIGN_FILE, DESIGN_MD = os.path.join(WORK, "design.yaml"), os.path.join(WORK, "design.md")
STYLE = {"accent": "#2F5D8A", "context": "#B8C2CC", "alert": "#C0392B"}


def check_layout(layout, kpi_ids, columns):
    """Problems with a proposed layout: unknown ids/columns, off-grid items, overlaps."""
    errs, taken, seen = [], {}, set()
    for it in layout:
        if it["id"] in seen:
            errs.append(f"duplicate id {it['id']}")
        seen.add(it["id"])
        if it["type"] == "kpi" and it.get("kpi") not in kpi_ids:
            errs.append(f"{it['id']}: unknown kpi {it.get('kpi')}")
        if it["type"] in ("line", "bar"):
            if it.get("y") not in kpi_ids:
                errs.append(f"{it['id']}: unknown kpi {it.get('y')} for y")
            if it.get("x") not in columns:
                errs.append(f"{it['id']}: unknown column {it.get('x')} for x")
            if it.get("goal") is not None and not isinstance(it["goal"], (int, float)):
                errs.append(f"{it['id']}: goal must be a number")
        if it["type"] not in ("text", "kpi", "line", "bar"):
            errs.append(f"{it['id']}: unknown type {it['type']}")
        if it["col"] < 0 or it["col"] + it["size_x"] > 24 or it["row"] < 0 or it["size_x"] < 1 or it["size_y"] < 1:
            errs.append(f"{it['id']}: outside the 24-column grid")
            continue
        for r in range(it["row"], it["row"] + it["size_y"]):
            for c in range(it["col"], it["col"] + it["size_x"]):
                if (r, c) in taken:
                    errs.append(f"{it['id']} overlaps {taken[(r, c)]}")
                    break
                taken[(r, c)] = it["id"]
    return sorted(set(errs))


def wireframe(layout, names):
    rows = max(i["row"] + i["size_y"] for i in layout)
    canvas = [[" "] * 72 for _ in range(rows)]
    for it in layout:
        r0, r1, c0, c1 = it["row"], it["row"] + it["size_y"] - 1, it["col"] * 3, (it["col"] + it["size_x"]) * 3 - 1
        for c in range(c0, c1 + 1):
            canvas[r0][c] = canvas[r1][c] = "-"
        for r in range(r0, r1 + 1):
            canvas[r][c0] = canvas[r][c1] = "|"
        label = names.get(it["id"], it["id"])[: c1 - c0 - 1]
        mid = r0 + (r1 - r0) // 2 if r1 > r0 else r0
        for k, ch in enumerate(label):
            canvas[mid if r1 - r0 > 1 else r0][c0 + 1 + k] = ch
    return "\n".join("".join(r).rstrip() for r in canvas)


def design_propose():
    require("design")
    prof = active_profile()
    kp, sem = yaml.safe_load(open(KPI_FILE)), yaml.safe_load(open(SEM_YAML))
    cols = {c["name"]: c for c in sem["tables"][0]["columns"]}
    usable = {n: c for n, c in cols.items() if c["role"] in ("dimension", "date")}
    # The time column: a date/timestamp column the learner can filter on (a month-named one first). Months of data
    # come from its range, so a daily date column works as well as a month column.
    dates = [c for c in prof["columns"] if c["name"] in usable and c["type"].startswith(("DATE", "TIMESTAMP")) and "min" in c]
    dates.sort(key=lambda c: "MONTH" not in c["name"])
    tcol, months = (dates[0]["name"], 0) if dates else (None, 0)
    if dates:
        (y1, m1), (y2, m2) = (int(dates[0]["min"][:4]), int(dates[0]["min"][5:7])), (int(dates[0]["max"][:4]), int(dates[0]["max"][5:7]))
        months = (y2 - y1) * 12 + m2 - m1 + 1
    brief = {
        "kpis": [{f: k.get(f) for f in ("id", "name", "format", "value", "target", "target_note")} for k in kp["kpis"]],
        "columns_for_charts_and_filters": [
            {"name": n, "role": c["role"], "description": c["description"],
             "distinct": next(p["distinct"] for p in prof["columns"] if p["name"] == n)} for n, c in usable.items()],
        "time_column": tcol, "months_of_data": months, "caveats_from_data": [u["name"] + ": " + u["reason"] for u in kp["unsupported"]]}
    prompt = (
        "Design a leadership dashboard for these approved KPIs. Return JSON only:\n"
        "{\"title\", \"audience\", \"comparison\", \"filters\": [{\"id\", \"column\", \"type\"}], \"layout\": "
        "[{\"id\", \"type\", ...}], \"rationale\"}.\n"
        "Layout items use a 24-column grid with row, col, size_x, size_y. Types: text, kpi, line, bar. "
        "kpi items: {id, type:'kpi', kpi:<kpi id>, ...}. Chart items: {id, type, title, x:<column>, y:<kpi id>, "
        "optional goal:<number>}. Text items: {id, type:'text', text}.\n"
        "Rules: row 0 is a header text item (24 wide, 2 high) with text '{{title}} — {{period_label}}'. Row 2 holds "
        "exactly 6 KPI tiles (4 wide, 3 high), the most important top-left. Then 6 to 8 charts (line only for time "
        "on time_column, bar otherwise; x must be a column listed below with a small number of distinct values). "
        "Then a text item with text '{{narrative}}' (24 wide, 5 high, the AI-written summary), and last a footer "
        "text item with text '{{caveats}}' (24 wide, 2 high). Chart titles state what the chart shows including "
        "units. Use goal only for a KPI that has a target. filters: one per useful dimension plus the month; "
        "type is 'date/month-year' for time_column, 'string' otherwise. If time_column is null there is no month filter and no line chart. comparison: 'month_over_month' when "
        "months_of_data >= 2, else 'none'. rationale: 2 to 3 sentences on why this layout suits the audience. "
        "No overlaps.\n\nINPUT:\n" + json.dumps(brief))
    feedback = ""
    for _ in range(3):
        text = ask_claude(prompt + feedback).strip()
        d = json.loads(text[text.index("{"): text.rindex("}") + 1])
        errs = check_layout(d["layout"], {k["id"] for k in kp["kpis"]}, set(usable))
        errs += [f"filter {f['id']}: unknown column {f['column']}" for f in d["filters"] if f["column"] not in usable]
        if not errs:
            break
        feedback = f"\n\nYour layout was rejected: {errs}. Fix these."
    else:
        sys.exit(f"Layout still invalid after 3 tries: {errs}")
    kname = {k["id"]: k["name"] for k in kp["kpis"]}
    names = {i["id"]: (kname[i["kpi"]] if i["type"] == "kpi" else i.get("title") or i["id"]) for i in d["layout"]}
    spec = {"meta": {"title": d["title"], "status": "proposed", "audience": d["audience"], "source": kp["source"],
                     "date_column": next((f["column"] for f in d["filters"] if f["type"] == "date/month-year"), None),
                     "comparison": d["comparison"], "period_label": "auto",
                     "caveats": [u["name"] + " is not available in this data." for u in kp["unsupported"][:3]]},
            "filters": d["filters"], "kpis": kp["kpis"], "layout": d["layout"], "style": STYLE}
    yaml.safe_dump(spec, open(DESIGN_FILE, "w"), sort_keys=False, allow_unicode=True)
    md = ["# Dashboard design (proposed)", "", f"**{d['title']}** for {d['audience']}. Comparison: {d['comparison']}.", "",
          d["rationale"], "", "Filters: " + ", ".join(f"{f['id']} ({f['column']})" for f in d["filters"]), "",
          "```", wireframe(d["layout"], names), "```", "", "| Item | Type | Shows |", "|---|---|---|"]
    for i in sorted(d["layout"], key=lambda i: (i["row"], i["col"])):
        shows = kname.get(i.get("kpi")) or (f"{kname.get(i.get('y'))} by {i.get('x')}" if i["type"] in ("line", "bar")
                                           else i.get("text", ""))
        md.append(f"| {names[i['id']]} | {i['type']} | {shows}{' (goal ' + str(i['goal']) + ')' if i.get('goal') else ''} |")
    open(DESIGN_MD, "w").write("\n".join(md) + "\n")
    print("\n".join(md))
    done("design", f"{len(d['layout'])} items in design.yaml / design.md")


def build():
    """Write the AI summary, build the dashboard in the chosen tool from design.yaml, then QA it."""
    import subprocess
    require("build")
    tool = json.load(open(os.path.join(WORK, "tool.json")))["tool"]
    if tool != "metabase":
        sys.exit(f"No builder for {tool} yet.")
    env = dict(os.environ, DASHBOARD_SPEC="design.yaml")

    def run(*args):
        r = subprocess.run([sys.executable, "-W", "ignore", "build_dashboard.py", *args], cwd=HERE, env=env,
                           capture_output=True, text=True)
        out = "\n".join(l for l in (r.stdout + r.stderr).splitlines() if "Warning" not in l and "warnings.warn" not in l)
        print(out)
        return r.returncode, out
    for args in (["narrate"], ["build"]):
        code, out = run(*args)
        if code:
            sys.exit(f"'{args[0]}' failed")
    url = next(l.split(": ", 1)[1] for l in out.splitlines() if l.startswith("Dashboard:"))
    code, out = run("qa")
    if code:
        sys.exit("QA failed. See qa_report.md. The dashboard exists but is not approved.")
    done("build", f"{url}, QA all pass")


MODEL_FILE, MODEL_XLSX = os.path.join(WORK, "model.yaml"), os.path.join(WORK, "model.xlsx")
MODEL_SHEETS = {"Joins": ["table", "from_column", "to_column", "type"],
                "Derived": ["alias", "expr"], "Rollups": ["name", "table", "key", "base_key", "alias", "expr"]}


def fq(e, t, raw=True):
    """Full name of a raw table (default) or, with raw=False, of an object we create: the view."""
    db, schema = src(e) if raw else (e["SNOWFLAKE_DATABASE"], e["SNOWFLAKE_SCHEMA"].upper())
    return f"{db}.{schema}.{t.upper()}"


def table_columns(cur, e, t, raw=True):
    db, schema = src(e) if raw else (e["SNOWFLAKE_DATABASE"], e["SNOWFLAKE_SCHEMA"].upper())
    return [c[0] for c in query(cur, f"SELECT COLUMN_NAME FROM {db}.INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = %s "
                                     "AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION", (schema, t.upper()))]


def model_sql(m, e, cols):
    """SELECT for the model: base (+ derived columns), many-to-one joins, and one-to-many rollups summarised first.
    Joining only 'one' sides, or summaries at the base grain, keeps one output row per base row."""
    taken = {c.upper() for c in cols[m["base"]]} | {d["alias"].upper() for d in m["derived"]}
    inner = ", ".join(["t.*"] + [f"{d['expr']} AS {d['alias']}" for d in m["derived"]])
    select, joins = ["b.*"], []
    for i, j in enumerate(m["joins"]):
        a = f"j{i}"
        for c in cols[j["table"]]:
            if c.upper() == j["to_column"].upper():
                continue
            name = c if c.upper() not in taken else f"{j['table'].upper()}_{c}"
            taken.add(name.upper())
            select.append(f"{a}.{c} AS {name}")
        joins.append(f"LEFT JOIN {fq(e, j['table'])} {a} ON b.{j['from_column']} = {a}.{j['to_column']}")
    for i, r in enumerate(m["rollups"]):
        a = f"r{i}"
        aggs = ", ".join(f"{c['expr']} AS {c['alias']}" for c in r["columns"])
        for c in r["columns"]:
            zero = c["expr"].strip().upper().startswith(("COUNT", "SUM"))
            select.append(f"COALESCE({a}.{c['alias']}, 0) AS {c['alias']}" if zero else f"{a}.{c['alias']} AS {c['alias']}")
        joins.append(f"LEFT JOIN (SELECT {r['key']} AS K, {aggs} FROM {fq(e, r['table'])} GROUP BY {r['key']}) {a} "
                     f"ON b.{r['base_key']} = {a}.K")
    return (f"SELECT {', '.join(select)}\nFROM (SELECT {inner} FROM {fq(e, m['base'])} t) b\n" + "\n".join(joins)).strip()


def model_check(m, cur, e):
    """Run the safety checks in Snowflake. Returns (rows for the report, list of blocking problems, columns, sql)."""
    tables = {m["base"]} | {j["table"] for j in m["joins"]} | {r["table"] for r in m["rollups"]}
    cols = {t: table_columns(cur, e, t) for t in tables}
    missing = [t for t, c in cols.items() if not c]
    if missing:
        return [], [f"Unknown table: {', '.join(missing)}"], cols, ""
    n = query(cur, f"SELECT COUNT(*) FROM {fq(e, m['base'])}")[0][0]
    rows, bad = [("Base rows", f"{n:,}", True)], []
    for j in m["joins"]:
        total, distinct = query(cur, f"SELECT COUNT(*), COUNT(DISTINCT {j['to_column']}) FROM {fq(e, j['table'])}")[0]
        ok = total == distinct
        rows.append((f"{j['table']}.{j['to_column']} is unique (many-to-one is safe)", f"{total:,} rows, {distinct:,} distinct", ok))
        if not ok:
            bad.append(f"{j['table']}.{j['to_column']} is not unique, so joining it would multiply rows. "
                       "Make it a rollup instead.")
        orphans = query(cur, f"SELECT COUNT_IF(j.{j['to_column']} IS NULL) FROM {fq(e, m['base'])} b "
                             f"LEFT JOIN {fq(e, j['table'])} j ON b.{j['from_column']} = j.{j['to_column']}")[0][0]
        rows.append((f"Base rows with no {j['table']} match", f"{orphans:,} ({orphans / n:.1%})", orphans == 0))
    for r in m["rollups"]:
        orphans = query(cur, f"SELECT COUNT_IF(r.K IS NULL) FROM {fq(e, m['base'])} b LEFT JOIN "
                             f"(SELECT {r['key']} AS K FROM {fq(e, r['table'])} GROUP BY {r['key']}) r "
                             f"ON b.{r['base_key']} = r.K")[0][0]
        rows.append((f"Base rows with no {r['table']} rows (rollup {r['name']})", f"{orphans:,} ({orphans / n:.1%})", orphans == 0))
    sql = model_sql(m, e, cols)
    try:
        after = query(cur, f"SELECT COUNT(*) FROM ({sql})")[0][0]
    except Exception as ex:
        return rows, [f"The model SQL failed in Snowflake: {str(ex).splitlines()[0][:200]}"], cols, sql
    rows.append(("Rows after joining equal base rows (no fan-out)", f"{after:,} vs {n:,}", after == n))
    if after != n:
        bad.append(f"The model returns {after:,} rows but the base has {n:,}: rows are being multiplied.")
    return rows, bad, cols, sql


def save_model(m, rows, sql, e):
    import openpyxl
    yaml.safe_dump(m, open(MODEL_FILE, "w"), sort_keys=False)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Model"
    ws.append(["base", "view_name"])
    ws.append([m["base"], m["view_name"]])
    for name, head in MODEL_SHEETS.items():
        ws = wb.create_sheet(name)
        ws.append(head)
        if name == "Joins":
            data = [[j["table"], j["from_column"], j["to_column"], j["type"]] for j in m["joins"]]
        elif name == "Derived":
            data = [[d["alias"], d["expr"]] for d in m["derived"]]
        else:
            data = [[r["name"], r["table"], r["key"], r["base_key"], c["alias"], c["expr"]]
                    for r in m["rollups"] for c in r["columns"]]
        for d in data:
            ws.append(d)
    wb.save(MODEL_XLSX)
    md = [f"# Model: {m['view_name']}", "", f"Base table: {m['base']}", "", "| Check | Result | OK |", "|---|---|---|"]
    md += [f"| {c} | {r} | {'yes' if ok else 'warning'} |" for c, r, ok in rows]
    if sql:
        open(os.path.join(WORK, "model.sql"), "w").write(sql + ";\n")
        open(os.path.join(WORK, "create_view.sql"), "w").write(
            "-- Run this with a Snowflake role that can create views. The agent's role is read-only and cannot.\n"
            f"CREATE OR REPLACE VIEW {fq(e, m['view_name'], raw=False)} AS\n{sql};\n"
            f"-- The agent's role must be able to read the view, or it will not see it:\n"
            f"GRANT SELECT ON VIEW {fq(e, m['view_name'], raw=False)} TO ROLE {e['SNOWFLAKE_ROLE']};\n")
        md += ["", "SQL: model.sql. To create the view, run create_view.sql with your own rights, then: "
                   "python flow.py model verify"]
    open(os.path.join(WORK, "model.md"), "w").write("\n".join(md) + "\n")
    print("\n".join(md))


def model_from_xlsx(path):
    import openpyxl
    wb = openpyxl.load_workbook(path)

    def rows(sheet):
        r = list(wb[sheet].iter_rows(values_only=True))
        head = [str(h).strip() for h in r[0]]
        return [dict(zip(head, x)) for x in r[1:] if any(v not in (None, "") for v in x)]
    top = rows("Model")[0]
    roll = {}
    for r in rows("Rollups"):
        g = roll.setdefault(r["name"], {"name": r["name"], "table": r["table"], "key": r["key"],
                                        "base_key": r["base_key"], "columns": []})
        g["columns"].append({"alias": r["alias"], "expr": r["expr"]})
    return {"base": top["base"], "view_name": top["view_name"], "derived": rows("Derived"),
            "joins": [{**j, "type": j.get("type") or "many_to_one"} for j in rows("Joins")],
            "rollups": list(roll.values())}


def model_finish(m, cur, e):
    rows, bad, cols, sql = model_check(m, cur, e)
    if bad:
        return bad
    save_model(m, rows, sql, e)
    done("model", f"{m['view_name']}: base {m['base']}, {len(m['joins'])} joins, {len(m['rollups'])} rollups")
    return []


def model_cmd(sub, arg=None):
    require("model")
    conn, e = connect_snowflake()
    cur = conn.cursor()
    prof = json.load(open(os.path.join(WORK, "profile.json")))
    objs = prof.get("objects") or [prof]
    if sub == "import":
        bad = model_finish(model_from_xlsx(arg), cur, e)
        if bad:
            sys.exit("Fix these in the Excel file:\n  - " + "\n  - ".join(bad))
        return
    if sub == "verify":
        m = yaml.safe_load(open(MODEL_FILE))
        view = m["view_name"]
        if not table_columns(cur, e, view, raw=False):
            sys.exit(f"{view} is not visible to the agent's read-only role. Either it was not created yet, or it was "
                     f"created without the GRANT SELECT line at the end of create_view.sql. Run the whole script "
                     f"with your own Snowflake rights, then verify again.")
        o, lines = profile_one(cur, e, view, raw=False)
        base_n = query(cur, f"SELECT COUNT(*) FROM {fq(e, m['base'])}")[0][0]
        if o["rows"] != base_n:
            sys.exit(f"{view} has {o['rows']:,} rows but the base table has {base_n:,}. Recreate the view.")
        json.dump(o, open(os.path.join(WORK, "view_profile.json"), "w"), indent=1)
        print(f"Verified {view}: {o['rows']:,} rows, {len(o['columns'])} columns. Later steps now use this view.")
        return
    if sub != "suggest":
        sys.exit("Use: model suggest | model import <file.xlsx> | model verify")
    if len(objs) == 1:  # one view or table: nothing to join
        src = objs[0]["source"].split(".")[-1]
        m = {"base": src, "view_name": src, "single": True, "derived": [], "joins": [], "rollups": []}
        yaml.safe_dump(m, open(MODEL_FILE, "w"), sort_keys=False)
        done("model", f"single object {src}, no joins")
        return
    brief = [{"name": o["source"].split(".")[-1], "rows": o["rows"], "columns": [
        {k: v for k, v in c.items() if k in ("name", "type", "distinct", "null_rate", "min", "max", "values")}
        for c in o["columns"]]} for o in objs]
    prompt = (
        "Design a join model for a BI dashboard from these profiled Snowflake tables. Return JSON only:\n"
        "{\"base\": <table name>, \"view_name\": <new view name, uppercase>, \"derived\": [{\"alias\", \"expr\"}], "
        "\"joins\": [{\"table\", \"from_column\", \"to_column\", \"type\": \"many_to_one\"}], "
        "\"rollups\": [{\"name\", \"table\", \"key\", \"base_key\", \"columns\": [{\"alias\", \"expr\"}]}]}.\n"
        + (f"The base table must be {arg}.\n" if arg else "Choose as base the table whose rows are the thing to analyse.\n") +
        "Rules: NEVER join a table that has many rows per base row; summarise it with a rollup instead (key = its "
        "column that matches the base, base_key = the base column, each column an aggregate such as COUNT(*) or "
        "COUNT_IF(EVENT_TYPE = 'x') using values seen in the profile). joins are only for tables with one row per key "
        "(for example a customer table). derived: Snowflake expressions over BASE columns only, such as flags "
        "IFF(STATUS = 'Closed', 1, 0) AS IS_CLOSED and durations DATEDIFF('minute', A, B). Aliases UPPERCASE with "
        "underscores. Use only tables and columns that exist. Tables that do not belong in this subject (for example "
        "a different business process) are left out.\n\nPROFILE:\n" + json.dumps(brief))
    feedback = ""
    for _ in range(3):
        text = ask_claude(prompt + feedback).strip()
        m = json.loads(text[text.index("{"): text.rindex("}") + 1])
        m["base"] = m["base"].split(".")[-1].upper()
        for j in m["joins"]:
            j["table"], j["type"] = j["table"].upper(), "many_to_one"
        for r in m["rollups"]:
            r["table"] = r["table"].upper()
        bad = model_finish(m, cur, e)
        if not bad:
            return
        feedback = f"\n\nYour model failed these checks, fix them: {bad}"
    sys.exit("The model still fails after 3 tries:\n  - " + "\n  - ".join(bad))


def test_questions(sem):
    """Three questions in the learner's own words (synonyms from the semantic model), not column names."""
    t = sem["tables"][0]
    brief = {"table": t["description"], "columns": [{"column": c["name"], "synonyms": c["synonyms"]}
                                                      for c in t["columns"] if c["synonyms"]],
             "metrics": [{"name": m["name"], "synonyms": m["synonyms"]} for m in sem["metrics"]]}
    text = ask_claude(
        "Write 3 short business questions to test a data chatbot. Each must use a synonym from the lists below "
        "instead of the exact column or metric name, and be answerable with one SELECT. Make the second one a "
        "breakdown by a dimension. Return JSON only: {\"questions\": [...]}.\n\n" + json.dumps(brief)).strip()
    return json.loads(text[text.index("{"): text.rindex("}") + 1])["questions"][:3]


def chatbot():
    """Give the chatbot the semantic model: push meanings into Metabase (for Metabot), test `ask` in business words."""
    import subprocess, urllib.request
    require("chatbot")
    env, sem = load_env(), yaml.safe_load(open(SEM_YAML))
    headers = {"Content-Type": "application/json", "X-API-KEY": env["METABASE_API_KEY"]}

    def api(method, path, body=None):
        req = urllib.request.Request(env["METABASE_URL"].rstrip("/") + path, method=method, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
        return json.loads(urllib.request.urlopen(req, timeout=120).read() or b"{}")
    db = next(d["id"] for d in api("GET", "/api/database")["data"] if d["engine"] == "snowflake")
    t = sem["tables"][0]
    table = next(x for x in api("GET", f"/api/database/{db}/metadata?include_hidden=true")["tables"]
                 if x["name"] == t["name"])
    api("PUT", f"/api/table/{table['id']}", {"description": f"{t['description']} Grain: {t['grain']}"})
    by_name = {c["name"]: c for c in t["columns"]}
    for f in table["fields"]:
        c = by_name.get(f["name"])
        if c:
            also = f" Also called: {', '.join(c['synonyms'])}." if c["synonyms"] else ""
            api("PUT", f"/api/field/{f['id']}", {"description": f"{c['description']}{also}"})
    print(f"Pushed meanings of {len(by_name)} columns into Metabase (for Metabot to use).")
    questions = test_questions(sem)
    for q in questions:  # one fresh session per question, so earlier questions cannot add filters to later ones
        r = subprocess.run([sys.executable, "-W", "ignore", "build_dashboard.py", "ask", q], cwd=HERE,
                           env=dict(os.environ, DASHBOARD_SPEC="design.yaml"), capture_output=True, text=True)
        print("\n".join(l for l in (r.stdout + r.stderr).splitlines() if "arning" not in l and "warn(" not in l))
        if r.returncode:
            sys.exit("A test question failed.")
    done("chatbot", f"semantic model loaded into ask and Metabase; {len(questions)} business-word questions tested")


TOOLS = {"metabase": "ready: built and QA'd through the Metabase API",
         "tableau": "planned: tableau_build.py generates and publishes a workbook (session only); not wired into flow.py build",
         "powerbi": "planned: not available yet"}


def choose_tool(name=None):
    require("tool")
    if name is None:
        print("BI tools:")
        for t, s in TOOLS.items():
            print(f"  {t:<10} {s}")
        print("Choose one with: python flow.py tool <name>")
        return
    if name not in TOOLS:
        sys.exit(f"Unknown tool. Choose from: {', '.join(TOOLS)}")
    if not TOOLS[name].startswith("ready"):
        sys.exit(f"{name} is not ready yet ({TOOLS[name]}). Choose a ready tool.")
    json.dump({"tool": name}, open(os.path.join(WORK, "tool.json"), "w"))
    done("tool", f"{name} chosen")


if __name__ == "__main__":
    cmd, args = (sys.argv[1] if len(sys.argv) > 1 else "status"), sys.argv[2:]
    {"init": lambda: __import__("preflight").init_env(), "doctor": lambda: __import__("preflight").doctor(),
     "status": lambda: status(), "connect": lambda: connect(), "profile": lambda: profile(*args),
     "approve": lambda: approve(args[0]),
     "kpis": lambda: {"suggest": kpis_suggest, "template": kpis_template,
                      "import": lambda: kpis_import(args[1])}[args[0]](),
     "semantic": lambda: {"draft": semantic_draft, "convert": semantic_convert}[args[0]](),
     "model": lambda: model_cmd(args[0], args[1] if len(args) > 1 else None),
     "design": lambda: design_propose(),
     "tool": lambda: choose_tool(args[0] if args else None),
     "build": lambda: build(),
     "chatbot": lambda: chatbot(),
     "reset": lambda: reset(args[0], "--yes" in args)}[cmd]()

"""Build the Metabase dashboard described in dashboard_spec.yaml, or QA it.

  python build_dashboard.py build   # cards + dashboard + layout
  python build_dashboard.py narrate # Claude writes narrative.md from the data (needs ANTHROPIC_API_KEY)
  python build_dashboard.py ask     # chat with the data in plain English (needs ANTHROPIC_API_KEY)
  python build_dashboard.py qa      # re-compute KPIs in Snowflake, compare with Metabase, write qa_report.md

Everything dataset-specific comes from the spec; credentials come from .env.
"""
import json, os, re, sys, time, urllib.request, urllib.error
from decimal import Decimal, ROUND_HALF_UP

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
# Each subject (tickets, claims, ...) can have its own workspace: FLOW_WORKSPACE=claims keeps its approvals and files
# in workspaces/claims/. Without it, the project root is the workspace. Code and .env always stay in the root.
WORK = os.path.join(HERE, "workspaces", os.environ["FLOW_WORKSPACE"]) if os.environ.get("FLOW_WORKSPACE") else HERE
os.makedirs(WORK, exist_ok=True)
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def load_env(path=os.path.join(HERE, ".env")):
    env = {}
    for line in open(path):
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.rstrip("\n").split("=", 1)
            env[k] = v
    return env


def month_col():
    """The spec's time column (the filter of type date/month-year), or None when the data has no date to filter on."""
    return next((f["column"] for f in SPEC["filters"] if f["type"] == "date/month-year"), None)


def month_sql(col):
    """Group a date, timestamp or month column by calendar month (a month column stays as it is)."""
    return f"DATE_TRUNC('month', {col})"


ENV = load_env()
SPEC = yaml.safe_load(open(os.path.join(WORK, os.environ.get("DASHBOARD_SPEC", "dashboard_spec.yaml"))))
BASE = ENV["METABASE_URL"].rstrip("/")
SOURCE = SPEC["meta"]["source"].replace("${SNOWFLAKE_DATABASE}", ENV["SNOWFLAKE_DATABASE"]).replace(
    "${SNOWFLAKE_SCHEMA}", ENV["SNOWFLAKE_SCHEMA"])
VIEW = SOURCE.split(".")[-1]
KPIS = {k["id"]: k for k in SPEC["kpis"]}
STYLE = SPEC["style"]


def label(f):
    """Filter label shown in Metabase: the spec's label, else the column name in words."""
    return f.get("label") or f["column"].replace("_", " ").title()
for _f in SPEC["filters"]:  # spec says "string"; Metabase wants an operator
    _f["type"] = {"string": "string/="}.get(_f["type"], _f["type"])


def api(method, path, body=None):
    req = urllib.request.Request(
        BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "X-API-KEY": ENV["METABASE_API_KEY"]})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {path} -> {e.code}: {e.read().decode()[:400]}")


def run_sql(db_id, sql):
    d = api("POST", "/api/dataset", {"database": db_id, "type": "native", "native": {"query": sql}})
    if d.get("error"):
        sys.exit("SQL error: " + str(d["error"])[:300])
    return d["data"]["rows"]


def find_db():
    return next(d["id"] for d in api("GET", "/api/database")["data"] if d["engine"] == "snowflake")


def fmt_settings(fmt):
    s = {"number_style": "percent", "decimals": 1} if fmt == "percent" else \
        {"decimals": 1} if fmt == "minutes" else {"decimals": 2} if fmt == "decimal2" else {"decimals": 0}
    return {'["name","value"]': s}


# ---------------------------------------------------------------- build
def tags(fields):
    out = {}
    for f in SPEC["filters"]:
        out[f["id"]] = {"id": f"tag-{f['id']}", "name": f["id"], "display-name": label(f),
                        "type": "dimension", "dimension": ["field", fields[f["column"]], None],
                        "widget-type": f["type"]}
    return out


def where():
    return "WHERE 1=1 " + " ".join(f"[[AND {{{{{f['id']}}}}}]]" for f in SPEC["filters"])


def card_for(item, db_id, fields):
    """One native-SQL card for a kpi tile or a chart."""
    kpi = KPIS[item["kpi"] if item["type"] == "kpi" else item["y"]]
    if item["type"] == "kpi":
        sql, display, name = f"SELECT {kpi['sql']} AS value FROM {SOURCE} {where()}", "scalar", kpi["name"]
        vs = {"scalar.field": "value", "column_settings": fmt_settings(kpi["format"])}
    else:
        x = item["x"]
        xs = month_sql(x) if x == month_col() else x
        order = "1" if item["type"] == "line" else "2 DESC"
        sql = f"SELECT {xs} AS dim, {kpi['sql']} AS value FROM {SOURCE} {where()} GROUP BY 1 ORDER BY {order}"
        display, name = ("line" if item["type"] == "line" else "bar"), item["title"]
        vs = {"graph.dimensions": ["dim"], "graph.metrics": ["value"], "graph.show_values": item["type"] == "bar",
              "graph.x_axis.title_text": x.replace("_", " ").title(), "graph.y_axis.title_text": kpi["name"],
              "series_settings": {"value": {"color": STYLE["accent"], "title": kpi["name"]}},
              "column_settings": fmt_settings(kpi["format"]), "legend.is_reversed": False}
        if item.get("goal"):
            vs.update({"graph.show_goal": True, "graph.goal_value": item["goal"],
                       "graph.goal_label": kpi.get("target_note", "Target")})
    return api("POST", "/api/card", {
        "name": name, "type": "question", "display": display, "visualization_settings": vs,
        "dataset_query": {"database": db_id, "type": "native",
                          "native": {"query": sql, "template-tags": tags(fields)}}})


def period_label(db_id):
    if not SPEC["meta"].get("date_column"):
        return ""
    lo, hi = run_sql(db_id, f"SELECT MIN({SPEC['meta']['date_column']}), MAX({SPEC['meta']['date_column']}) FROM {SOURCE}")[0]
    (y1, m1), (y2, m2) = (int(lo[:4]), int(lo[5:7])), (int(hi[:4]), int(hi[5:7]))
    return f"{MONTHS[m1-1]}–{MONTHS[m2-1]} {y2}" if y1 == y2 else f"{MONTHS[m1-1]} {y1}–{MONTHS[m2-1]} {y2}"


def mom_title(db_id, kpi):
    """Latest month vs previous month, as text with an arrow (used when the tile is a plain scalar)."""
    if not month_col():
        return kpi["name"]
    rows = run_sql(db_id, f"SELECT {month_sql(month_col())} m, {kpi['sql']} "
                          f"FROM {SOURCE} GROUP BY 1 ORDER BY 1 DESC LIMIT 2")
    if len(rows) < 2:
        return kpi["name"]
    (m_now, now), (m_prev, prev) = rows[0], rows[1]
    d = float(now) - float(prev)
    arrow = "▲" if d > 0 else "▼" if d < 0 else "►"
    delta = f"{abs(d) * 100:.1f}pp" if kpi["format"] == "percent" else f"{abs(d) / float(prev) * 100:.1f}%"
    return f"{kpi['name']}  {arrow} {delta} vs {MONTHS[int(str(m_prev)[5:7]) - 1]}"


def text_card(n, item, content):
    return {"id": -n, "card_id": None, "row": item["row"], "col": item["col"], "size_x": item["size_x"],
            "size_y": item["size_y"], "parameter_mappings": [],
            "visualization_settings": {"virtual_card": {"name": None, "display": "text", "archived": False,
                                                        "dataset_query": {}, "visualization_settings": {}},
                                       "text": content}}


def ensure_synced(db_id):
    """Dashboard filters need the view's fields in Metabase. A view created after setup must be synced first."""
    for attempt in range(40):
        if any(t["name"] == VIEW for t in api("GET", f"/api/database/{db_id}/metadata?include_hidden=true")["tables"]):
            return
        if attempt == 0:
            api("POST", f"/api/database/{db_id}/sync_schema")
            print(f"Asked Metabase to sync {VIEW}...")
        time.sleep(5)
    sys.exit(f"Metabase has not synced {VIEW} after 200 seconds. Check Admin settings, Databases.")


def build():
    db_id = find_db()
    ensure_synced(db_id)
    meta = api("GET", f"/api/database/{db_id}/metadata?include_hidden=true")
    table = next(t for t in meta["tables"] if t["name"] == VIEW)
    fields = {f["name"]: f["id"] for f in table["fields"]}
    period = period_label(db_id)
    params = [{"id": f["id"], "name": label(f), "slug": f["id"], "type": f["type"]} for f in SPEC["filters"]]
    dash = api("POST", "/api/dashboard", {"name": SPEC["meta"]["title"], "parameters": params,
                                          "description": f"Data period {period}"})
    cards, n = [], 0
    for item in SPEC["layout"]:
        n += 1
        place = {k: item[k] for k in ("row", "col", "size_x", "size_y")}
        if item["type"] == "text":
            text = item["text"].replace("{{title}}", SPEC["meta"]["title"]).replace(" — {{period_label}}", f" — {period}" if period else "").replace("{{period_label}}", period)
            if "{{narrative}}" in text:
                text = open(os.path.join(WORK, "narrative.md")).read()
            elif "{{caveats}}" in text:
                text = "**Caveats:** " + " ".join(SPEC["meta"]["caveats"])
            else:
                text = f"# {text}"
            cards.append(text_card(n, item, text))
            continue
        card = card_for(item, db_id, fields)
        vs = {}
        if item["type"] == "kpi":
            vs["card.title"] = mom_title(db_id, KPIS[item["kpi"]])
        cards.append({"id": -n, "card_id": card["id"], **place, "visualization_settings": vs,
                      "parameter_mappings": [{"parameter_id": f["id"], "card_id": card["id"],
                                              "target": ["dimension", ["template-tag", f["id"]]]}
                                             for f in SPEC["filters"]]})
    api("PUT", f"/api/dashboard/{dash['id']}", {"dashcards": cards})
    placed = {i["kpi"] for i in SPEC["layout"] if i["type"] == "kpi"}
    for kid in KPIS.keys() - placed:  # every KPI gets a card (used by QA), even if not on the dashboard
        card_for({"type": "kpi", "kpi": kid}, db_id, fields)
    print(f"Dashboard: {BASE}/dashboard/{dash['id']}")


# ---------------------------------------------------------------- facts
def get_facts():
    """The numbers an AI needs to write the dashboard narrative (read-only, via Metabase)."""
    db_id = find_db()
    mc = month_col()
    out = {"period": period_label(db_id), "kpis": {}, "by_month": {}, "by_dimension": {}}
    for kid, k in KPIS.items():
        out["kpis"][k["name"]] = round(float(run_sql(db_id, f"SELECT {k['sql']} FROM {SOURCE}")[0][0]), 4)
    for r in (run_sql(db_id, f"SELECT {month_sql(mc)}, " + ", ".join(k["sql"] for k in KPIS.values()) +
                      f" FROM {SOURCE} GROUP BY 1 ORDER BY 1") if mc else []):
        out["by_month"][str(r[0])[:7]] = {k["name"]: round(float(v), 4) for k, v in zip(KPIS.values(), r[1:])}
    for item in SPEC["layout"]:
        if item.get("x") and item["x"] != mc:
            k = KPIS[item["y"]]
            out["by_dimension"][item["title"]] = {
                str(a): round(float(b), 4) for a, b in
                run_sql(db_id, f"SELECT {item['x']}, {k['sql']} FROM {SOURCE} GROUP BY 1 ORDER BY 2 DESC")}
    return out


def facts():
    print(json.dumps(get_facts(), indent=1))


def narrate():
    """Ask Claude to write narrative.md from the facts. Run before `build` so the dashboard picks it up."""
    if not ENV.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is empty in .env")
    f = get_facts()
    sem_path = os.path.join(WORK, "semantic_model.yaml")
    defs = ""
    if os.path.exists(sem_path):  # what the numbers mean, including any assumptions the learner recorded
        sem = yaml.safe_load(open(sem_path))
        defs = ("\nDEFINITIONS AND ASSUMPTIONS:\n" + sem["tables"][0]["grain"] + "\n"
                + "\n".join(f"- {m['name']}: {m['description']}" for m in sem["metrics"]) + "\n"
                + "\n".join(f"- {g['term']}: {g['meaning']}" for g in sem["glossary"]) + "\n")
    prompt = (
        f"You write the summary card for a leadership dashboard titled '{SPEC['meta']['title']}'.\n"
        f"Data period: {f['period']}. Caveats from the data owner: {' '.join(SPEC['meta']['caveats'])}\n\n"
        "Write markdown only, in exactly this shape:\n"
        f"Line 1: **AI-written summary** · {f['period']}, <number of rows> <what one row is>. Written by Claude "
        "from this dashboard's data; check before sharing.\n"
        "Then a blank line and 3 to 4 bullets, each starting with a bold label (for example Volume, Performance, "
        "Quality, Watch next). Add an arrow (▲ or ▼) wherever a metric moved or breaches a target.\n\n"
        "Rules: use only numbers present in the facts or simple rounding of them; percentages with 1 decimal; "
        "thousands separators on counts and amounts; other numbers with at most 2 decimals. Name the biggest "
        "driver you find in the breakdowns. Do not invent causes. If the definitions say a metric depends on an "
        "assumption, say so briefly next to it. Plain, short sentences. Under 140 words.\n"
        f"{defs}\nFACTS (JSON):\n{json.dumps(f)}")
    feedback = ""
    for _ in range(3):  # redraft if any number is not a plain rounding of a fact
        text = ask_claude(prompt + feedback).strip()
        bad = unsupported_numbers(text, f)
        short = len(re.findall(r"^- ", text, flags=re.M)) < 3
        if not bad and not short:
            break
        feedback = (f"\n\nYour previous draft was rejected. Numbers that are not roundings of the facts: {bad}. "
                    f"Fewer than 3 bullets: {short}. Round to the nearest value (never truncate), use only values "
                    "from the facts, and write 3 to 4 bullets.")
    else:
        sys.exit(f"Narrative rejected after 3 tries (unsupported numbers: {bad}, too few bullets: {short})")
    open(os.path.join(WORK, "narrative.md"), "w").write(text + "\n")
    print(text)


def ask_claude(messages, system=""):
    """messages: a prompt string or a chat history [{role, content}, ...]."""
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    body = {"model": ENV.get("ANTHROPIC_MODEL", "claude-sonnet-5-5"), "max_tokens": 4000, "messages": messages}
    if system:
        body["system"] = system
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", method="POST", data=json.dumps(body).encode(),
        headers={"content-type": "application/json", "x-api-key": ENV["ANTHROPIC_API_KEY"],
                 "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            out = json.loads(r.read())
        if out.get("stop_reason") == "max_tokens":  # thinking tokens count toward the limit
            sys.exit("Claude response was cut off (max_tokens); raise it in ask_claude")
        return "".join(b["text"] for b in out["content"] if b["type"] == "text")
    except urllib.error.HTTPError as e:
        sys.exit(f"Claude API -> {e.code}: {e.read().decode()[:300]}")


def unsupported_numbers(text, f):
    """Numbers in the text (after the header line) that are not a rounding of a fact or a spec target."""
    vals, stack = [k["target"] for k in KPIS.values() if isinstance(k.get("target"), (int, float))], [f]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            stack += list(x.values())
        elif isinstance(x, (list, tuple)):
            stack += list(x)
        elif isinstance(x, (int, float)) and not isinstance(x, bool):
            vals.append(x)
    ok = set()
    for v in vals:
        for scale in (1, 100):  # as-is, or as a percentage
            for d in (0, 1, 2):
                q = (Decimal(str(v)) * scale).quantize(Decimal(1).scaleb(-d), ROUND_HALF_UP)
                ok |= {format(q, "f"), format(q, ",f")}
    body = text.split("\n", 1)[1] if "\n" in text else text
    return [n for n in re.findall(r"\d[\d,]*\.?\d*", body) if n.rstrip(".,") not in ok]


# ---------------------------------------------------------------- ask (natural language questions)
def ask_context(db_id):
    """System prompt: the table, its columns, allowed dimension values and the KPI definitions from the spec."""
    meta = api("GET", f"/api/database/{db_id}/metadata?include_hidden=true")
    table = next(t for t in meta["tables"] if t["name"] == VIEW)
    dims = sorted(({i["x"] for i in SPEC["layout"] if i.get("x")} | {f["column"] for f in SPEC["filters"]}) - {month_col()})
    values = {d: [r[0] for r in run_sql(db_id, f"SELECT DISTINCT {d} FROM {SOURCE} ORDER BY 1")] for d in dims}
    sem_path = os.path.join(WORK, "semantic_model.yaml")
    sem = yaml.safe_load(open(sem_path)) if os.path.exists(sem_path) else None
    meaning = ""
    if sem:  # the learner's semantic model: what the data means and the words people use for it
        t = sem["tables"][0]
        also = lambda s: f" Also called: {', '.join(s)}." if s else ""
        meaning = (
            f"\nWhat the data means. Table: {t['description']} Grain: {t['grain']}\n"
            + "\n".join(f"- {c['name']}: {c['description']}{also(c['synonyms'])}" for c in t["columns"])
            + "\nMetric names people use:\n"
            + "\n".join(f"- {m['name']}: {m['description']}{also(m['synonyms'])}" for m in sem["metrics"])
            + "\nGlossary:\n" + "\n".join(f"- {g['term']}: {g['meaning']}" for g in sem["glossary"]) + "\n"
            "Map the user's words to these columns and metrics, using synonyms and the glossary.\n")
    return (
        f"You answer business questions about {SPEC['meta']['title']} data by writing Snowflake SQL.\n"
        f"Table: {SOURCE}. Columns: "
        + ", ".join(f"{f['name']} ({f['database_type']})" for f in table["fields"]) + ".\n"
        f"Allowed values: {json.dumps(values)}. Month column: {month_col() or 'none'}.\n"
        + meaning +
        "KPI definitions, use these expressions exactly so answers match the dashboard:\n"
        + "\n".join(f"- {k['name']}: {k['sql']}" for k in KPIS.values()) + "\n"
        f"Caveats: {' '.join(SPEC['meta']['caveats'])}\n\n"
        "Rules: reply with one short sentence of intent and exactly one ```sql block. Only a single SELECT on the "
        "table above. Rates are fractions. A follow-up (for example 'only for East') changes the previous query, "
        "keeping its earlier filters. If the data cannot answer the question, say so and write no SQL.")


def safe_select(sql):
    s = sql.strip().rstrip(";").strip()
    banned = r"\b(insert|update|delete|merge|drop|create|alter|truncate|grant|revoke|call|copy|put)\b"
    if ";" in s or not re.match(r"(?is)^(select|with)\b", s) or re.search("(?i)" + banned, s):
        return None
    return s if re.search(r"(?i)\blimit\s+\d+", s) else f"SELECT * FROM ({s}) LIMIT 50"


def show_table(cols, rows):
    cells = [[str(c) for c in cols]] + [["" if v is None else f"{v:.4g}" if isinstance(v, float) else str(v)[:40]
                                         for v in r] for r in rows]
    widths = [max(len(r[i]) for r in cells) for i in range(len(cols))]
    for n, r in enumerate(cells):
        print("  " + "  ".join(c.ljust(w) for c, w in zip(r, widths)))
        if n == 0:
            print("  " + "  ".join("-" * w for w in widths))


def ask():
    """Chat with the data: python build_dashboard.py ask ["question" "follow-up" ...]. Blank line quits."""
    if not ENV.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is empty in .env")
    db_id, queue = find_db(), sys.argv[2:]
    system, history = ask_context(db_id), []
    while True:
        if queue:
            q = queue.pop(0)
            print(f"\n> {q}")
        else:
            try:
                q = input("\n> ").strip()
            except EOFError:
                break
            if not q:
                break
        history.append({"role": "user", "content": q})
        for _ in range(3):  # retry when the SQL is unsafe or fails
            reply = ask_claude(history, system)
            history.append({"role": "assistant", "content": reply})
            m = re.search(r"```sql\s*(.*?)```", reply, flags=re.S)
            if not m:
                print(reply.strip())
                break
            sql = safe_select(m.group(1))
            err = "Only a single read-only SELECT is allowed." if not sql else None
            if sql:
                d = api("POST", "/api/dataset", {"database": db_id, "type": "native", "native": {"query": sql}})
                err = str(d["error"])[:300] if d.get("error") else None
            if err:
                history.append({"role": "user", "content": f"That failed: {err} Fix the SQL."})
                continue
            cols, rows = [c["name"] for c in d["data"]["cols"]], d["data"]["rows"]
            print("SQL:\n  " + m.group(1).strip().replace("\n", "\n  "))
            show_table(cols, rows)
            history.append({"role": "user", "content": f"Result columns {cols}, rows {json.dumps(rows[:50])}. "
                            "Answer my question in 1 to 3 plain sentences using only numbers from this result "
                            "(percentages with 1 decimal, minutes with 1 decimal). Do not write SQL."})
            answer = ask_claude(history, system).strip()
            history.append({"role": "assistant", "content": answer})
            bad = unsupported_numbers("\n" + answer, rows)
            if bad:  # one redraft, e.g. when a number was truncated instead of rounded
                history.append({"role": "user", "content": f"These numbers are not roundings of the result: {bad}. "
                                "Rewrite the answer, rounding to the nearest value."})
                answer = ask_claude(history, system).strip()
                history.append({"role": "assistant", "content": answer})
                bad = unsupported_numbers("\n" + answer, rows)
            print("\n" + answer + (f"\n(check these numbers, not found in the result: {bad})" if bad else ""))
            break


# ---------------------------------------------------------------- qa
def qa():
    import snowflake.connector
    conn = snowflake.connector.connect(
        account=ENV["SNOWFLAKE_ACCOUNT"].removesuffix(".snowflakecomputing.com"), user=ENV["SNOWFLAKE_USER"],
        password=ENV["SNOWFLAKE_PASSWORD"], warehouse=ENV["SNOWFLAKE_WAREHOUSE"], role=ENV["SNOWFLAKE_ROLE"],
        database=ENV["SNOWFLAKE_DATABASE"], schema=ENV["SNOWFLAKE_SCHEMA"])
    cur = conn.cursor()
    by_name = {}  # newest live scalar card per KPI name
    for c in sorted(api("GET", "/api/card"), key=lambda c: c["id"]):
        if not c.get("archived") and c["display"] == "scalar":
            by_name[c["name"]] = c["id"]
    rows, ok = [], True
    for kid, k in KPIS.items():
        cur.execute(f"SELECT {k['sql']} FROM {SOURCE}")
        sf = float(cur.fetchone()[0])
        card_id = by_name.get(k["name"])
        mb = float(api("POST", f"/api/card/{card_id}/query")["data"]["rows"][0][0]) if card_id else None
        exp = SPEC.get("qa_expected", {}).get(kid)
        # Metabase must equal Snowflake to 1e-6 (stricter than the 0.01 rate tolerance); the spec's expected
        # value is rounded, so compare Snowflake rounded to the expected value's own decimals.
        decimals = len(str(exp).split(".")[1]) if exp is not None and "." in str(exp) else 0
        passed = mb is not None and abs(sf - mb) <= 1e-6 and (exp is None or abs(round(sf, decimals) - exp) < 1e-9)
        ok &= passed
        rows.append((k["name"], sf, mb, exp, passed))
    cur.close(); conn.close()
    lines = ["# QA report", "",
             "Each KPI was re-computed with plain SQL straight from Snowflake and compared with the value",
             "Metabase returns for its dashboard card (no filters), and with the expected value in the spec.",
             "Tolerance applied: Metabase must match Snowflake within 0.000001 (stricter than exact counts / 0.01 rates).",
             "The spec's expected values are rounded, so Snowflake is rounded to the expected value's decimals first.", "",
             "| KPI | Snowflake | Metabase | Expected | Result |", "|---|---|---|---|---|"]
    for name, sf, mb, exp, passed in rows:
        f = lambda v: "n/a" if v is None else f"{v:.4f}"
        lines.append(f"| {name} | {f(sf)} | {f(mb)} | {f(exp)} | {'PASS' if passed else 'FAIL'} |")
    lines += ["", f"**Overall: {'ALL PASS' if ok else 'FAILURES PRESENT'}**"]
    open(os.path.join(WORK, "qa_report.md"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    {"build": build, "qa": qa, "facts": facts, "narrate": narrate, "ask": ask}[sys.argv[1] if len(sys.argv) > 1 else "build"]()

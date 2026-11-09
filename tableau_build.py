"""Generate a Tableau workbook (.twb) from the approved design.yaml.

  python tableau_build.py translate              # Claude turns each KPI's SQL into a Tableau calculation
  python tableau_build.py build <template.twb>   # write tableau.twb: one sheet per tile/chart, and the dashboard

The template is any workbook (.twb or .twbx) that already connects to your PUBLISHED data source, for example an empty
one saved from Tableau. Its data source section is reused as is, because Tableau wrote it. Publishing needs the Tableau
connector, so it is done from a Claude session: upload the .twb, publish it, then compare each KPI with Snowflake.
Use FLOW_WORKSPACE=<name> to pick the subject, like flow.py.
"""
import hashlib, json, os, re, sys, uuid, zipfile
from xml.sax.saxutils import escape

import yaml

from flow import WORK, ask_claude, active_profile

DESIGN, CALCS, OUT = (os.path.join(WORK, f) for f in ("design.yaml", "tableau_calcs.yaml", "tableau.twb"))
FORMATS = {"percent": ("real", "p0.0%"), "integer": ("integer", "n#,##0"),
           "minutes": ("real", "n#,##0.0;-#,##0.0"), "decimal2": ("real", "n#,##0.00")}
ATTR = {"'": "&apos;", '"': "&quot;"}
STYLE = ("<zone-style><format attr='border-color' value='#000000' /><format attr='border-style' value='none' />"
         "<format attr='border-width' value='0' /><format attr='margin' value='4' /></zone-style>")


def attr(s):
    return escape(str(s), ATTR)


# ---------------------------------------------------------------- translate
def translate():
    d = yaml.safe_load(open(DESIGN))
    cols = {c["name"]: c["type"] for c in active_profile()["columns"]}
    prompt = (
        "Translate these Snowflake SQL aggregate expressions into Tableau calculated-field formulas. Return JSON only: "
        "{\"<kpi id>\": \"<formula>\"}.\nRules: refer to columns as [COLUMN_NAME] exactly as listed. Use Tableau "
        "syntax: COUNTD([X]) for COUNT(DISTINCT X); IF cond THEN 1 ELSE 0 END for IFF; MEDIAN, AVG, SUM, "
        "PERCENTILE([X], 0.9); ZN() or a check such as IF SUM(...) = 0 THEN NULL ELSE ... END for NULLIF. Keep each "
        "result a single aggregated expression, so that it works in a view grouped by any dimension.\n\n"
        f"COLUMNS: {json.dumps(cols)}\nKPIS: {json.dumps({k['id']: k['sql'] for k in d['kpis']})}")
    text = ask_claude(prompt).strip()
    calcs = json.loads(text[text.index("{"): text.rindex("}") + 1])
    for kid, f in calcs.items():
        bad = [c for c in re.findall(r"\[([^\]]+)\]", f) if c not in cols]
        if bad:
            sys.exit(f"{kid}: formula uses unknown columns {bad}")
    missing = {k["id"] for k in d["kpis"]} - set(calcs)
    if missing:
        sys.exit(f"No formula for: {sorted(missing)}")
    yaml.safe_dump(calcs, open(CALCS, "w"), sort_keys=False, width=200)
    for k in d["kpis"]:
        print(f"  {k['name']:<32} {calcs[k['id']]}")
    print(f"\nWrote {os.path.basename(CALCS)}. These are not checked yet: after publishing, compare every KPI with Snowflake.")


# ---------------------------------------------------------------- build
def read_template(path):
    if path.lower().endswith(".twbx"):
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".twb") and "/" not in n)
            return z.read(name).decode("utf-8")
    return open(path, encoding="utf-8").read()


def period_label(d):
    col = next((f["column"] for f in d["filters"] if f["type"] == "date/month-year"), None)
    if not col:
        return ""
    c = next(c for c in active_profile()["columns"] if c["name"] == col)
    months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    (y1, m1), (y2, m2) = (int(c["min"][:4]), int(c["min"][5:7])), (int(c["max"][:4]), int(c["max"][5:7]))
    return f"{months[m1-1]}–{months[m2-1]} {y2}" if y1 == y2 else f"{months[m1-1]} {y1}–{months[m2-1]} {y2}"


def calc_id(kid):
    return "Calculation_" + str(int(hashlib.md5(kid.encode()).hexdigest(), 16))[:16]


def text_zone(zid, it, runs, place):
    first = " bold='true' fontsize='16'" if it.get("id") == "header" else ""  # the dashboard title is larger
    body = "".join(f"<run{first if i == 0 else ''}>{escape(t)}</run><run>Æ&#10;</run>" for i, t in enumerate(runs) if t)
    return f"<zone {place(it)} id='{zid}' type-v2='text'><formatted-text>{body}</formatted-text>{STYLE}</zone>"


def build(template_path):
    d, tpl = yaml.safe_load(open(DESIGN)), read_template(template_path)
    calcs = yaml.safe_load(open(CALCS))
    kpis = {k["id"]: k for k in d["kpis"]}
    ds_block = re.search(r"<datasource caption='([^']+)' inline='true' name='(sqlproxy[^']*)'.*?</datasource>", tpl, flags=re.S)
    if not ds_block:
        sys.exit("The template has no published data source (sqlproxy) section.")
    caption, ds = ds_block.group(1), ds_block.group(2)
    raw = {m.group(1): m.group(0) for m in re.finditer(r"<column [^>]*name='\[([A-Z0-9_]+)\]'[^>]*/>", ds_block.group(0))}
    need = {c for f in calcs.values() for c in re.findall(r"\[([^\]]+)\]", f)} | \
           {i["x"] for i in d["layout"] if i.get("x")}
    missing = sorted(need - set(raw))
    if missing:
        sys.exit(f"The template's data source lacks these columns: {missing}. Use a template on the right data source.")

    def calc_column(kid):
        k = kpis[kid]
        dt, fmt = FORMATS.get(k["format"], FORMATS["decimal2"])
        return (f"<column caption='{attr(k['name'])}' datatype='{dt}' default-format='{fmt}' name='[{calc_id(kid)}]' "
                f"role='measure' type='quantitative'><calculation class='tableau' formula='{attr(calcs[kid])}' /></column>")

    def dim(x):
        """How a dimension is used in a view: dates are truncated to the month, everything else is a plain category."""
        if "datatype='date'" in raw[x] or "datatype='datetime'" in raw[x]:
            return "Month-Trunc", "tmn", "qk", "quantitative"
        return "None", "none", "nk", "nominal"

    filters = d.get("filters", [])
    bad = [f["column"] for f in filters if f["column"] not in raw]
    if bad:
        sys.exit(f"The template's data source lacks the filter columns: {bad}")

    def fdim(f):
        """A filter lists the members of a column: months become month names, the rest stay as they are."""
        if f["type"] == "date/month-year":
            return "Month", "mn", "ok", "ordinal"
        return "None", "none", "nk", "nominal"

    def deps(kid, x=None):
        cols = {c for c in re.findall(r"\[([^\]]+)\]", calcs[kid])} | ({x} if x else set()) | {f["column"] for f in filters}
        insts = {}
        if x:
            deriv, pre, suf, typ = dim(x)
            insts[f"{pre}:{x}:{suf}"] = f"<column-instance column='[{x}]' derivation='{deriv}' name='[{pre}:{x}:{suf}]' pivot='key' type='{typ}' />"
        for f in filters:
            deriv, pre, suf, typ = fdim(f)
            insts[f"{pre}:{f['column']}:{suf}"] = (f"<column-instance column='[{f['column']}]' derivation='{deriv}' "
                                                   f"name='[{pre}:{f['column']}:{suf}]' pivot='key' type='{typ}' />")
        insts["calc"] = (f"<column-instance column='[{calc_id(kid)}]' derivation='User' name='[usr:{calc_id(kid)}:qk]' "
                         "pivot='key' type='quantitative' />")
        return "".join([raw[c] for c in sorted(cols)] + [calc_column(kid)] + list(insts.values()))

    def view_filters():
        """The same filters on every sheet, so the dashboard filters can steer all of them."""
        out, slices = "", ""
        for f in filters:
            _, pre, suf, _ = fdim(f)
            inst_ = f"{pre}:{f['column']}:{suf}"
            out += (f"<filter class='categorical' column='[{ds}].[{inst_}]'><groupfilter function='level-members' "
                    f"level='[{inst_}]' user:ui-enumeration='all' user:ui-marker='enumerate' /></filter>")
            slices += f"<column>[{ds}].[{inst_}]</column>"
        return out + (f"<slices>{slices}</slices>" if slices else "")

    def inst(x):
        _, pre, suf, _ = dim(x)
        return f"[{ds}].[{pre}:{x}:{suf}]"

    sheets, used = [], set()
    for it in d["layout"]:
        if it["type"] not in ("kpi", "line", "bar"):
            continue
        kid = it["kpi"] if it["type"] == "kpi" else it["y"]
        name = it.get("title") or kpis[kid]["name"]
        while name in used:
            name += " "
        used.add(name)
        it["_sheet"] = name
        measure = f"[{ds}].[usr:{calc_id(kid)}:qk]"
        if it["type"] == "kpi":
            pane, rows_, cols_ = f"<mark class='Text' /><encodings><text column='{measure}' /></encodings>", "", ""
            dep = deps(kid)
        else:
            pane = f"<mark class='{'Line' if it['type'] == 'line' else 'Bar'}' />"
            rows_, cols_ = (measure, inst(it["x"])) if it["type"] == "line" else (inst(it["x"]), measure)
            dep = deps(kid, it["x"])
        # a small grey sheet title, so a narrow tile is not filled by its own name
        size = 9 if it["type"] == "kpi" else 11
        title = (f"<layout-options><title><formatted-text><run fontcolor='#5b6b7a' fontsize='{size}'>&lt;Sheet Name&gt;</run>"
                 "</formatted-text></title></layout-options>")
        value_style = ("<style><style-rule element='cell'><format attr='font-size' value='22' />"
                       "<format attr='font-weight' value='bold' /></style-rule></style>") if it["type"] == "kpi" else ""
        sheets.append(
            f"<worksheet name='{attr(name)}'>{title}<table><view><datasources><datasource caption='{attr(caption)}' name='{ds}' />"
            f"</datasources><datasource-dependencies datasource='{ds}'>{dep}</datasource-dependencies>"
            f"{view_filters()}<aggregation value='true' /></view><style />"
            f"<panes><pane selection-relaxation-option='selection-relaxation-allow'><view><breakdown value='auto' /></view>"
            f"{pane}{value_style}</pane></panes><rows>{rows_}</rows><cols>{cols_}</cols></table>"
            f"<simple-id uuid='{{{str(uuid.uuid4()).upper()}}}' /></worksheet>")

    rows = max(i["row"] + i["size_y"] for i in d["layout"])
    top = 7200 if filters else 800  # a strip of filters sits above the design's layout

    def place(it):
        return (f"h='{round(it['size_y'] / rows * (99200 - top)) - 2}' w='{round(it['size_x'] / 24 * 98400)}' "
                f"x='{round(it['col'] / 24 * 98400) + 800}' y='{round(it['row'] / rows * (99200 - top)) + top}'")
    narrative = open(os.path.join(WORK, "narrative.md"), encoding="utf-8").read() if os.path.exists(os.path.join(WORK, "narrative.md")) else ""
    zones, zid = [], 10
    for it in d["layout"]:
        zid += 1
        if it["type"] == "text":
            t = it["text"]
            if "{{narrative}}" in t:
                runs = [re.sub(r"\*\*|^- ", "", l).strip() for l in narrative.splitlines()]
            elif "{{caveats}}" in t:
                runs = ["Caveats: " + " ".join(d["meta"]["caveats"])]
            else:
                runs = [t.replace("{{title}}", d["meta"]["title"]).replace("{{period_label}}", period_label(d))]
            zones.append(text_zone(zid, it, runs, place))
        else:
            zones.append(f"<zone {place(it)} id='{zid}' name='{attr(it['_sheet'])}'>{STYLE}</zone>")
    host = sorted(used)[0] if used else ""
    for i, f in enumerate(filters):  # one drop-down per filter, side by side along the top
        zid += 1
        _, pre, suf, _ = fdim(f)
        width = round(98400 / len(filters))
        zones.append(f"<zone h='6000' id='{zid}' mode='checkdropdown' name='{attr(host)}' "
                     f"param='[{ds}].[{pre}:{f['column']}:{suf}]' type-v2='filter' w='{width - 400}' "
                     f"x='{800 + i * width}' y='800'>{STYLE}</zone>")  # a drop-down, so the list is not cut off
    dash = d["meta"]["title"]
    dashboards = (f"<dashboards><dashboard enable-sort-zone-taborder='true' name='{attr(dash)}'><style />"
                  f"<size maxheight='1200' maxwidth='1200' minheight='1200' minwidth='1200' sizing-mode='fixed' />"
                  f"<zones><zone h='100000' id='4' type-v2='layout-basic' w='100000' x='0' y='0'>{''.join(zones)}"
                  f"<zone-style><format attr='border-color' value='#000000' /><format attr='border-style' value='none' />"
                  f"<format attr='border-width' value='0' /><format attr='margin' value='8' /></zone-style></zone></zones>"
                  f"<simple-id uuid='{{{str(uuid.uuid4()).upper()}}}' /></dashboard></dashboards>")
    cards = ("<cards><edge name='left'><strip size='160'><card type='pages' /><card type='filters' /><card type='marks' /></strip>"
             "</edge><edge name='top'><strip size='31'><card type='columns' /></strip><strip size='31'><card type='rows' /></strip>"
             "<strip size='31'><card type='title' /></strip></edge></cards>")
    windows = ("<windows show-side-pane='false'>"
               + "".join(f"<window class='worksheet' name='{attr(n)}'>{cards}</window>" for n in sorted(used))
               + f"<window class='dashboard' maximized='true' name='{attr(dash)}'><viewpoints>"
               + "".join(f"<viewpoint name='{attr(n)}' />" for n in sorted(used))
               + "</viewpoints><active id='-1' /></window></windows>")
    head = tpl[: tpl.index("<worksheets>")]
    head = re.sub(r"\n[ \t]*<repository-location derived-from='[^']*workbooks/[^']*'[^>]*/>", "", head)
    head = re.sub(r"\n  <repository-location[^>]*/>", "", head, count=1)  # the old workbook's location
    out = head + "<worksheets>" + "".join(sheets) + "</worksheets>" + dashboards + windows + "</workbook>\n"
    import xml.dom.minidom as md
    md.parseString(out.encode("utf-8"))  # must be well-formed
    open(OUT, "w", encoding="utf-8").write(out)
    print(f"Wrote {os.path.basename(OUT)}: {len(sheets)} sheets and 1 dashboard '{dash}', data source '{caption}'.")
    print(f"{len(filters)} filters on every sheet and on the dashboard. Next: publish it from a Claude session, "
          "then compare every KPI with Snowflake.")


if __name__ == "__main__":
    cmd, args = (sys.argv[1] if len(sys.argv) > 1 else ""), sys.argv[2:]
    {"translate": translate, "build": lambda: build(args[0])}[cmd]()

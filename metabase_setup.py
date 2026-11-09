"""One-time Metabase setup from .env, safe to run again: python metabase_setup.py

1. First run only: create the admin account (METABASE_ADMIN_EMAIL / METABASE_ADMIN_PASSWORD).
2. Create an API key and save it in .env as METABASE_API_KEY (skipped when the key is already set).
3. Add your Snowflake database to Metabase (skipped when one exists), sync it, and wait for the tables.

Nothing secret is printed. Metabase must be running (docker compose up -d) and METABASE_URL set in .env.
"""
import json, os, re, sys, time, urllib.request, urllib.error

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def load_env():
    env = {}
    for line in open(ENV_PATH):
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.rstrip("\n").split("=", 1)
            env[k] = v
    return env


env = load_env()
for k in ("METABASE_URL", "METABASE_ADMIN_EMAIL", "METABASE_ADMIN_PASSWORD", "SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER",
          "SNOWFLAKE_PASSWORD", "SNOWFLAKE_WAREHOUSE", "SNOWFLAKE_DATABASE", "SNOWFLAKE_ROLE"):
    if not env.get(k):
        sys.exit(f"{k} is empty in .env")
BASE = env["METABASE_URL"].rstrip("/")


def call(method, path, body=None, headers=None):
    req = urllib.request.Request(BASE + path, method=method, headers={"Content-Type": "application/json", **(headers or {})},
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode()[:300]}
    except urllib.error.URLError:
        sys.exit(f"Cannot reach Metabase at {BASE}. Is it running? (docker compose up -d)")


def fail(step, out):
    sys.exit(f"{step} failed: {out}")


# 1. admin account (first run only)
token = call("GET", "/api/session/properties")[1].get("setup-token")
if token:
    st, out = call("POST", "/api/setup", {
        "token": token,
        "user": {"first_name": "Admin", "last_name": "User", "email": env["METABASE_ADMIN_EMAIL"],
                 "password": env["METABASE_ADMIN_PASSWORD"]},
        "prefs": {"site_name": "BI Dashboard", "allow_tracking": False}})
    print("admin account:", "created" if st < 300 else fail("setup", out))
else:
    print("admin account: already set up")

# 2. API key
if env.get("METABASE_API_KEY"):
    print("API key: already in .env")
    hdr = {"X-API-KEY": env["METABASE_API_KEY"]}
else:
    st, sess = call("POST", "/api/session", {"username": env["METABASE_ADMIN_EMAIL"], "password": env["METABASE_ADMIN_PASSWORD"]})
    if st >= 300:
        fail("login", sess)
    st, groups = call("GET", "/api/permissions/group", headers={"X-Metabase-Session": sess["id"]})
    admin_group = next(g["id"] for g in groups if g["name"] == "Administrators")
    st, key = call("POST", "/api/api-key", {"name": "dashboard-agent", "group_id": admin_group},
                   {"X-Metabase-Session": sess["id"]})
    if st >= 300:
        fail("api-key", key)
    text = open(ENV_PATH).read()
    text = re.sub(r"^METABASE_API_KEY=.*$", lambda m: "METABASE_API_KEY=" + key["unmasked_key"], text, flags=re.M)
    open(ENV_PATH, "w").write(text)
    print("API key: created and saved in .env")
    hdr = {"X-API-KEY": key["unmasked_key"]}

# 3. Snowflake database, then sync
st, dbs = call("GET", "/api/database", headers=hdr)
existing = [d for d in dbs.get("data", []) if d["engine"] == "snowflake"]
if existing:
    db = existing[0]
    print("Snowflake database: already added, id", db["id"])
else:
    details = {  # no schema filter: views the model step creates must be visible to Metabase too
        "account": env["SNOWFLAKE_ACCOUNT"].strip().removeprefix("https://").removesuffix("/").removesuffix(".snowflakecomputing.com"),
        "user": env["SNOWFLAKE_USER"], "password": env["SNOWFLAKE_PASSWORD"], "warehouse": env["SNOWFLAKE_WAREHOUSE"],
        "db": env["SNOWFLAKE_DATABASE"], "role": env["SNOWFLAKE_ROLE"]}
    st, db = call("POST", "/api/database", {"name": "Snowflake", "engine": "snowflake", "is_full_sync": True,
                                            "details": details}, hdr)
    if st >= 300:
        fail("add database", db)
    print("Snowflake database: added, id", db["id"])
call("POST", f"/api/database/{db['id']}/sync_schema", headers=hdr)
for _ in range(60):
    tables = call("GET", f"/api/database/{db['id']}/metadata?include_hidden=true", headers=hdr)[1].get("tables", [])
    if tables:
        print(f"Synced: {len(tables)} tables or views visible to Metabase")
        break
    time.sleep(5)
else:
    print("No tables after 5 minutes. Check Metabase Admin settings, Databases.")

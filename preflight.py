"""Setup helpers, run through flow.py:

  python flow.py init     # asks for your settings and writes .env (secrets are typed hidden, never echoed)
  python flow.py doctor   # checks the setup and says exactly what to fix; prints no secrets
"""
import getpass, json, os, shutil, subprocess, sys, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH, EXAMPLE_PATH = os.path.join(HERE, ".env"), os.path.join(HERE, ".env.example")

# name, question, secret, default shown to the learner. METABASE_API_KEY is filled by metabase_setup.py.
FIELDS = [
    ("SNOWFLAKE_ACCOUNT", "Snowflake account (for example myorg-myaccount; no .snowflakecomputing.com needed)", False, ""),
    ("SNOWFLAKE_USER", "Snowflake user (a read-only one)", False, ""),
    ("SNOWFLAKE_PASSWORD", "Snowflake password", True, ""),
    ("SNOWFLAKE_WAREHOUSE", "Snowflake warehouse", False, ""),
    ("SNOWFLAKE_DATABASE", "Snowflake database", False, ""),
    ("SNOWFLAKE_SCHEMA", "Snowflake schema", False, ""),
    ("SNOWFLAKE_ROLE", "Snowflake role (read-only)", False, ""),
    ("METABASE_URL", "Metabase URL", False, "http://localhost:3000"),
    ("METABASE_ADMIN_EMAIL", "Metabase admin email (you choose it; used on first setup)", False, ""),
    ("METABASE_ADMIN_PASSWORD", "Metabase admin password (you choose it; a long, unusual one, 14+ characters is safest)", True, ""),
    ("ANTHROPIC_API_KEY", "Anthropic API key (needed for the AI steps)", True, ""),
]
REQUIRED = [f[0] for f in FIELDS]


def read_env():
    env = {}
    if os.path.exists(ENV_PATH):
        for line in open(ENV_PATH):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.rstrip("\n").split("=", 1)
                env[k] = v
    return env


def missing(env):
    return [k for k in REQUIRED if not env.get(k, "").strip()]


def init_env():
    if not sys.stdin.isatty():
        sys.exit("init asks questions, so run it in a terminal. Or copy .env.example to .env and fill it in.")
    env = read_env()
    print("Press Enter to keep a value that is already set. Secrets are not shown as you type.\n")
    for name, question, secret, default in FIELDS:
        have = env.get(name, "").strip()
        if secret:
            shown = "set, Enter to keep" if have else "required" if name != "ANTHROPIC_API_KEY" else "Enter to skip"
            ans = getpass.getpass(f"{question} [{shown}]: ").strip()
        else:
            shown = have or default
            ans = input(f"{question}" + (f" [{shown}]" if shown else "") + ": ").strip() or shown
        if ans:
            env[name] = ans
    # write .env in the order and with the comments of .env.example
    template = open(EXAMPLE_PATH).read().split("\n") if os.path.exists(EXAMPLE_PATH) else [f"{k}=" for k in env]
    seen, out = set(), []
    for line in template:
        k = line.split("=", 1)[0]
        if "=" in line and not line.lstrip().startswith("#") and k in env:
            line = f"{k}={env[k]}"
            seen.add(k)
        out.append(line)
    out += [f"{k}={v}" for k, v in env.items() if k not in seen]
    open(ENV_PATH, "w").write("\n".join(out).rstrip("\n") + "\n")
    os.chmod(ENV_PATH, 0o600)
    left = missing(env)
    print("\nSaved .env." + (f" Still empty: {', '.join(left)}. Run init again to fill them." if left else ""))


def _get(url, key=None):
    req = urllib.request.Request(url, headers={"X-API-KEY": key} if key else {})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status, json.loads(r.read() or b"{}")


def doctor():
    results = []

    def check(name, status, hint=""):
        results.append(status)
        print(f"  {status:<5} {name}" + (f"\n        {hint}" if hint and status != "PASS" else ""))

    print("Checking your setup (no secrets are printed):")
    env = read_env()
    left = missing(env)
    if not os.path.exists(ENV_PATH):
        check(".env file", "FAIL", "Run: python flow.py init")
    else:
        check("settings in .env", "FAIL" if [k for k in left if k != "ANTHROPIC_API_KEY"] else "PASS",
              f"Empty: {', '.join(k for k in left if k != 'ANTHROPIC_API_KEY')}. Run: python flow.py init")
    check("Python 3.9 or newer", "PASS" if sys.version_info >= (3, 9) else "FAIL", "Install a newer Python.")
    gone = []
    for mod in ("yaml", "openpyxl", "snowflake.connector"):
        try:
            __import__(mod)
        except ImportError:
            gone.append(mod)
    check("Python packages", "FAIL" if gone else "PASS", f"Missing: {', '.join(gone)}. Run: pip install -r requirements.txt")
    try:
        ok = shutil.which("docker") and subprocess.run(["docker", "info"], capture_output=True, timeout=20).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        ok = False
    check("Docker is running", "PASS" if ok else "FAIL", "Start Docker Desktop (or install it), then try again.")

    base = env.get("METABASE_URL", "").rstrip("/")
    up = False
    if base:
        try:
            up = _get(base + "/api/health")[1].get("status") == "ok"
        except (urllib.error.URLError, OSError, ValueError):
            pass
    check(f"Metabase is up", "PASS" if up else "FAIL", "Run: docker compose up -d  (wait a minute), or: python setup.py")
    if up:
        key = env.get("METABASE_API_KEY", "").strip()
        good = False
        if key:
            try:
                good = _get(base + "/api/user/current", key)[0] == 200
            except (urllib.error.URLError, OSError, ValueError):
                pass
        check("Metabase API key works", "PASS" if good else "FAIL", "Run: python metabase_setup.py")
        has_db = False
        if good:
            try:
                has_db = any(d["engine"] == "snowflake" for d in _get(base + "/api/database", key)[1].get("data", []))
            except (urllib.error.URLError, OSError, ValueError, KeyError):
                pass
        check("Snowflake is added in Metabase", "PASS" if has_db else "FAIL", "Run: python metabase_setup.py")

    if not gone and not [k for k in left if k.startswith("SNOWFLAKE")]:
        try:
            sys.path.insert(0, HERE)
            import flow
            conn, _ = flow.connect_snowflake()
            role = conn.cursor().execute("SELECT CURRENT_ROLE()").fetchone()[0]
            check("Snowflake login works", "PASS")
            check("Role is read-only (not an admin role)", "WARN" if role.upper() in
                  ("ACCOUNTADMIN", "SECURITYADMIN", "SYSADMIN", "ORGADMIN", "USERADMIN") else "PASS",
                  "This flow only needs read access. Use a read-only role (see snowflake_setup.sql).")
        except Exception as e:  # a bad login shows as a Snowflake error; show its first line, never the settings
            check("Snowflake login works", "FAIL", "Could not log in: " + str(e).split("\n")[0][:160] +
                  ". Check account, user, password, role and warehouse in .env.")
    else:
        check("Snowflake login works", "FAIL", "Fix the items above first.")

    key = env.get("ANTHROPIC_API_KEY", "").strip()
    check("Anthropic API key is set", "PASS" if key.startswith("sk-ant-") else "WARN" if key else "FAIL",
          "Needed for KPI suggestions, the summary and the chatbot. Run: python flow.py init  "
          "(set but not starting with sk-ant-? check it is a real key). The key is not tested live.")
    bad = results.count("FAIL")
    print("\n" + ("All good. Start with: python flow.py connect" if not bad else f"{bad} thing(s) to fix before you start."))
    sys.exit(1 if bad else 0)

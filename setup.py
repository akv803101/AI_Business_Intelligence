"""One-command setup: python setup.py

Installs the Python packages, writes .env (asks you), starts Metabase in Docker, does the one-time Metabase setup,
and runs the doctor. Safe to run again: it skips what is already done. No secrets are printed.
"""
import os, shutil, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def step(n, text):
    print(f"\n[{n}/6] {text}")


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=HERE, **kw)


if sys.version_info < (3, 9):
    sys.exit("Python 3.9 or newer is needed.")

step(1, "Installing Python packages")
if run([PY, "-m", "pip", "install", "-q", "-r", "requirements.txt"]).returncode:
    sys.exit("pip install failed. Fix the error above and run python setup.py again.")

step(2, "Settings (.env)")
sys.path.insert(0, HERE)
import preflight
env = preflight.read_env()
if preflight.missing(env):
    if not os.path.exists(preflight.ENV_PATH) and os.path.exists(preflight.EXAMPLE_PATH):
        shutil.copy(preflight.EXAMPLE_PATH, preflight.ENV_PATH)
    preflight.init_env()
    env = preflight.read_env()
    if [k for k in preflight.missing(env) if k != "ANTHROPIC_API_KEY"]:
        sys.exit("Some settings are still empty. Run python setup.py again to finish them.")
else:
    print("  .env is complete.")

step(3, "Docker")
if not shutil.which("docker") or run(["docker", "info"], capture_output=True).returncode:
    sys.exit("Docker is not running. Install or start Docker Desktop, then run python setup.py again.")
compose = ["docker", "compose"] if run(["docker", "compose", "version"], capture_output=True).returncode == 0 else ["docker-compose"]

step(4, "Starting Metabase (the first start takes a minute or two)")
if run(compose + ["up", "-d"]).returncode:
    sys.exit("docker compose failed. Check that port 3000 is free and Docker is running.")
base = env["METABASE_URL"].rstrip("/")
for _ in range(60):
    try:
        if b'"ok"' in urllib.request.urlopen(base + "/api/health", timeout=5).read():
            break
    except Exception:
        pass
    time.sleep(5)
else:
    sys.exit(f"Metabase did not become healthy at {base} after 5 minutes. Check: docker compose logs metabase")
print("  Metabase is up.")

step(5, "One-time Metabase setup (admin, API key, Snowflake database)")
if run([PY, "metabase_setup.py"]).returncode:
    sys.exit("Metabase setup failed. Read the message above, fix it, and run python setup.py again.")

step(6, "Checking everything")
code = run([PY, "flow.py", "doctor"]).returncode
print("\nNext: open this folder in Claude Code and paste STARTER_PROMPT.md, or run: python flow.py connect"
      if not code else "\nFix the items marked FAIL, then run: python flow.py doctor")
sys.exit(code)

"""Run the site's browser tests: page checks on several screen sizes, then the sign-in and sync tests.

    npm run build                      # makes dist/
    pip install playwright && python -m playwright install chromium
    python tests/run.py                # TEST_BROWSER=firefox, webkit or msedge for the other engines

Firebase is replaced by a local stand-in (tests/fake/), so nothing touches the real accounts."""
import os, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DIST = os.path.join(ROOT, "dist")
DEVICES = os.environ.get("TEST_DEVICES", "iphone-se,iphone-14,pixel-7,ipad-mini,ipad-pro-land,win-laptop,desktop-1280").split(",")
OUT = os.path.join(ROOT, "test-results")

if not os.path.exists(os.path.join(DIST, "index.html")):
    sys.exit("Build the site first: npm run build")
os.makedirs(OUT, exist_ok=True)
srv = subprocess.Popen(["node", os.path.join(HERE, "server.mjs"), DIST, "8000"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
try:
    for _ in range(50):
        try:
            urllib.request.urlopen("http://localhost:8000/", timeout=1); break
        except Exception:
            time.sleep(0.2)
    failed = []
    for d in DEVICES:
        r = subprocess.run([sys.executable, os.path.join(HERE, "sweep.py"), d, OUT])
        if r.returncode: failed.append("pages on " + d)
    r = subprocess.run([sys.executable, os.path.join(HERE, "synctest.py")])
    if r.returncode: failed.append("sign-in and sync")
    print("\nAll checks passed." if not failed else "\nFailed: " + ", ".join(failed))
    sys.exit(1 if failed else 0)
finally:
    srv.terminate()

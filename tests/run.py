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
    def step(label, args):
        """Run one part and show its output; if it crashed, say so in the GitHub summary too."""
        r = subprocess.run([sys.executable] + args, capture_output=True, text=True, encoding="utf-8", errors="replace")
        sys.stdout.write(r.stdout); sys.stdout.write(r.stderr); sys.stdout.flush()
        if r.returncode:
            failed.append(label)
            if os.environ.get("GITHUB_ACTIONS") and "::error" not in r.stdout:
                tail = " | ".join((r.stdout + r.stderr).strip().splitlines()[-6:])[:900]
                print(f"::error title={label} stopped ({os.environ.get('TEST_BROWSER', 'chromium')})::{tail}", flush=True)
    for d in DEVICES:
        step("pages on " + d, [os.path.join(HERE, "sweep.py"), d, OUT])
    step("sign-in and sync", [os.path.join(HERE, "synctest.py")])
    print("\nAll checks passed." if not failed else "\nFailed: " + ", ".join(failed))
    sys.exit(1 if failed else 0)
finally:
    srv.terminate()

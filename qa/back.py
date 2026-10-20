"""Temporary QA: on the LIVE site, check that Back returns to the same place on phones and desktop,
and list which network requests stay open after the writing desk pre-loads Firebase.
Usage: python qa/back.py <outdir>"""
import json, os, sys, time
from playwright.sync_api import sync_playwright

LIVE = os.environ.get("LIVE_URL", "https://pmkyaw412-lab.github.io/wandering-eric/")
OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
res = {"live": LIVE, "when": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "back": {}, "after_desk": {}}
with sync_playwright() as p:
    for key, engine, dev in [("iphone14-webkit", "webkit", "iPhone 14"), ("iphoneSE-webkit", "webkit", "iPhone SE"),
                             ("pixel7-chromium", "chromium", "Pixel 7"), ("desktop-chromium", "chromium", None)]:
        b = getattr(p, engine).launch()
        opts = dict(p.devices[dev]) if dev else {"viewport": {"width": 1280, "height": 800}}
        opts.pop("default_browser_type", None)
        ctx = b.new_context(**opts)
        page = ctx.new_page()
        bk = {}
        for rr in ("#/faq", "#/schools", "#/study/terms"):
            try:
                page.goto(LIVE + rr, wait_until="load", timeout=45000)
                page.wait_for_timeout(1800)
                mx = page.evaluate("() => document.documentElement.scrollHeight - innerHeight")
                tgt = int(min(1200, mx / 2))
                page.evaluate("(t) => window.scrollTo(0, t)", tgt)
                page.wait_for_timeout(900)
                y0 = page.evaluate("() => scrollY")
                page.evaluate("() => { location.hash = '#/privacy' }")
                page.wait_for_timeout(900)
                y1 = page.evaluate("() => scrollY")
                page.go_back(wait_until="commit")
                page.wait_for_timeout(1500)
                bk[rr] = {"scrolled_to": y0, "after_move": y1, "after_back": page.evaluate("() => scrollY"),
                          "hash": page.evaluate("() => location.hash"), "h1": page.evaluate("() => (document.querySelector('main h1') || {}).textContent || ''")[:60]}
            except Exception as e:  # noqa
                bk[rr] = {"error": str(e)[:300]}
        res["back"][key] = bk
        page.screenshot(path=f"{OUT}/{key}__after-back.jpg", type="jpeg", quality=50)
        # which requests stay open once the desk has pre-loaded Firebase (signed out)
        pending, started = {}, []
        def on_req(r):
            pending[id(r)] = r.url[:160]; started.append([round(time.time() - t0, 1), r.resource_type, r.url[:160]])
        def on_done(r):
            pending.pop(id(r), None)
        page.on("request", on_req); page.on("requestfinished", on_done); page.on("requestfailed", on_done)
        t0 = time.time()
        try:
            page.goto(LIVE + "#/write", wait_until="load", timeout=45000)
        except Exception as e:  # noqa
            started.append(["goto-error", str(e)[:200]])
        page.wait_for_timeout(15000)
        res["after_desk"][key] = {"still_open_after_15s": sorted(set(pending.values())), "requests_in_15s": len(started),
                                  "started": started[:60], "frames": [f.url[:160] for f in page.frames]}
        b.close()
json.dump(res, open(f"{OUT}/back.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(json.dumps(res["back"], ensure_ascii=False, indent=1))
for k, v in res["after_desk"].items():
    print(k, "requests in 15 s:", v["requests_in_15s"], "still open:", v["still_open_after_15s"], "frames:", v["frames"])

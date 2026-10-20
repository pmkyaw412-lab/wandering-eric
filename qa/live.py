"""Temporary QA script: open the LIVE site with real network on phone and desktop profiles.
Usage: python qa/live.py <outdir>   (records console errors, failed requests, sideways overflow,
loaded fonts, and a JPEG of each page; then opens the Google sign-in window without signing in)."""
import json, os, sys, time
from playwright.sync_api import sync_playwright

LIVE = os.environ.get("LIVE_URL", "https://pmkyaw412-lab.github.io/wandering-eric/")
OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
ROUTES = ["", "#/home/steps", "#/study", "#/study/eju", "#/study/eju/dates", "#/study/eju/answers", "#/study/eju/papers",
          "#/study/terms", "#/study/apply", "#/study/apply/statement", "#/study/apply/interview", "#/study/apply/essay",
          "#/schools", "#/schools/pre", "#/schools/list", "#/schools/match", "#/schools/guide",
          "#/scholarships", "#/scholarships/saved", "#/scholarships/check", "#/scholarships/guide",
          "#/blog", "#/blog/no-such-post", "#/faq", "#/class", "#/privacy", "#/write"]
OVERFLOW_JS = """() => { const w = document.documentElement.clientWidth;
  const bad = [...document.querySelectorAll('body *')].filter(e => { const r = e.getBoundingClientRect(); if (r.width === 0) return false;
    let p = e.parentElement; while (p && p !== document.body) { const cs = getComputedStyle(p); if (/(auto|scroll|hidden|clip)/.test(cs.overflowX)) return false; p = p.parentElement; }
    return r.right > w + 1 || r.left < -1; })
    .map(e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (e.className && typeof e.className === 'string' ? '.' + e.className.trim().split(/\\s+/).join('.') : ''));
  return { sw: document.documentElement.scrollWidth, cw: w, bad: [...new Set(bad)].slice(0, 12) }; }"""

res = {"live": LIVE, "when": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "pages": {}, "signin": {}}
with sync_playwright() as p:
    for key, engine, dev in [("iphone14-webkit", "webkit", "iPhone 14"), ("pixel7-chromium", "chromium", "Pixel 7"), ("desktop-chromium", "chromium", None)]:
        b = getattr(p, engine).launch()
        opts = dict(p.devices[dev]) if dev else {"viewport": {"width": 1280, "height": 800}}
        opts.pop("default_browser_type", None)
        ctx = b.new_context(**opts)
        page = ctx.new_page()
        ev = []
        page.on("console", lambda m: ev.append(["console." + m.type, m.text[:300]]) if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: ev.append(["pageerror", str(e)[:300]]))
        page.on("requestfailed", lambda r: ev.append(["requestfailed", r.url[:200] + " " + str(r.failure)[:120]]))
        page.on("response", lambda r: ev.append(["http" + str(r.status), r.url[:200]]) if r.status >= 400 else None)
        for r in ROUTES:
            ev.clear()
            t0 = time.time()
            try:
                page.goto(LIVE + r, wait_until="networkidle", timeout=45000)
            except Exception as e:  # noqa
                ev.append(["goto", str(e)[:200]])
            page.wait_for_timeout(900 if r.startswith("#/blog") else 500)
            try:
                ov = page.evaluate(OVERFLOW_JS)
                fonts = page.evaluate("() => [...document.fonts].filter(f => f.status === 'loaded').map(f => f.family + ' ' + f.weight)")
                h1 = page.evaluate("() => (document.querySelector('main h1') || {}).textContent || ''")
            except Exception as e:  # noqa
                ov, fonts, h1 = {"err": str(e)[:200]}, [], ""
            name = r.replace("#/", "").replace("/", "_") or "home"
            try:
                page.screenshot(path=f"{OUT}/{key}__{name}.jpg", type="jpeg", quality=50, full_page=False)
            except Exception as e:  # noqa
                ev.append(["screenshot", str(e)[:200]])
            res["pages"][key + " " + (r or "/")] = {"ms": int((time.time() - t0) * 1000), "h1": h1[:120], "overflow": ov, "events": list(ev), "fonts": sorted(set(fonts))[:40]}
        if key == "desktop-chromium":
            # open the Google sign-in window, never sign in
            ev.clear()
            s = {}
            try:
                page.goto(LIVE, wait_until="networkidle", timeout=45000)
                page.click('[data-act="acct"]')
                page.wait_for_selector("#dlgbtn", timeout=15000)
                page.wait_for_timeout(4000)
                with page.expect_popup(timeout=20000) as pi:
                    page.click("#dlgbtn")
                pop = pi.value
                try:
                    pop.wait_for_load_state("domcontentloaded", timeout=30000)
                except Exception as e:  # noqa
                    s["popup_load"] = str(e)[:200]
                pop.wait_for_timeout(5000)
                s["popup_url_host"] = pop.url.split("?")[0][:200]
                s["popup_title"] = pop.title()[:200]
                pop.screenshot(path=f"{OUT}/signin-popup.jpg", type="jpeg", quality=50)
                pop.close()
                page.wait_for_timeout(3000)
                s["dialog_error"] = page.evaluate("() => (document.querySelector('#dlgerr') || {}).textContent || ''")
                page.screenshot(path=f"{OUT}/signin-after-close.jpg", type="jpeg", quality=50)
            except Exception as e:  # noqa
                s["error"] = str(e)[:300]
            s["events"] = list(ev)
            res["signin"] = s
        b.close()
json.dump(res, open(f"{OUT}/live.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
bad = {k: v for k, v in res["pages"].items() if v["events"] or (v["overflow"].get("sw", 0) > v["overflow"].get("cw", 0)) or v["overflow"].get("bad")}
print("pages:", len(res["pages"]), "with issues:", len(bad))
for k, v in bad.items():
    print(" ", k, v["overflow"], v["events"][:4])
print("signin:", json.dumps(res["signin"], ensure_ascii=False)[:1500])

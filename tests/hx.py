"""Shared Playwright helpers: a browser context that behaves like the live site, offline.
CDN files come from the local test server, Firebase is the fake in fake/, Firestore REST goes to the fake backend."""
import json, os, re, urllib.request

BASE = "http://localhost:8000/"
LOCAL = "http://localhost:8000"
LOCAL_CDN = os.environ.get("LOCAL_CDN") == "1"  # offline sandbox: serve KaTeX, marked and fonts from node_modules
BROWSER = os.environ.get("TEST_BROWSER", "chromium")  # chromium, firefox, webkit or msedge


def launch(p):
    if BROWSER == "msedge":
        return p.chromium.launch(channel="msedge")
    return getattr(p, BROWSER).launch()


def D(p, name):
    """A device profile that the current engine accepts (Firefox has no mobile emulation)."""
    d = dict(p.devices[name]) if name else {}
    d.pop("default_browser_type", None)
    if BROWSER == "firefox":
        d.pop("is_mobile", None)
    return d


CDN_MAP = [
    (re.compile(r"^https://cdnjs\.cloudflare\.com/ajax/libs/KaTeX/0\.16\.9/(.*)$"), LOCAL + "/__cdn/katex/{0}"),
    (re.compile(r"^https://cdn\.jsdelivr\.net/npm/marked@18\.0\.13/lib/marked\.umd\.js$"), LOCAL + "/__cdn/marked.umd.js"),
    (re.compile(r"^https://fonts\.googleapis\.com/css2.*$"), LOCAL + "/__cdn/fonts.css"),
    ]
MAP = (CDN_MAP if LOCAL_CDN else []) + [
    (re.compile(r"^https://www\.gstatic\.com/firebasejs/[^/]+/(firebase-[a-z]+\.js)$"), LOCAL + "/__cdn/firebase/{0}"),
    (re.compile(r"^https://firestore\.googleapis\.com/(v1/.*)$"), LOCAL + "/__rest/{0}"),
]
PIXEL = bytes.fromhex("47494638396101000100800000ffffff00000021f90401000000002c00000000010001000002024401003b")


def install_routes(ctx, blocked=None):
    def handler(route, request):
        url = request.url
        if url.startswith(LOCAL):
            return route.continue_()
        for rx, tpl in MAP:
            m = rx.match(url)
            if m:
                target = tpl.format(*[g.split("?")[0] if "firebase" in tpl or "katex" in tpl else g for g in m.groups()])
                try:
                    resp = ctx.request.fetch(target, method=request.method, headers={k: v for k, v in request.headers.items() if k.lower().startswith("x-") or k.lower() == "content-type"}, data=request.post_data_buffer)
                    return route.fulfill(response=resp, headers={**resp.headers, "access-control-allow-origin": "*"})
                except Exception as e:  # noqa
                    if blocked is not None:
                        blocked.append("fetchfail " + url + " " + str(e)[:80])
                    return route.abort()
        if "googleusercontent" in url:
            return route.fulfill(status=200, body=PIXEL, content_type="image/gif")
        if not LOCAL_CDN:
            return route.continue_()  # the real CDNs (fonts, KaTeX, marked)
        if blocked is not None:
            blocked.append(url)
        return route.abort()
    ctx.route("**/*", handler)


def new_ctx(p_or_browser, browser, device=None, init=None, blocked=None, **kw):
    opts = dict(device or {})
    opts.pop("default_browser_type", None)
    if BROWSER == "firefox":
        opts.pop("is_mobile", None)
    opts.update(kw)
    if BROWSER == "firefox":
        opts.pop("is_mobile", None)
    ctx = browser.new_context(**opts)
    install_routes(ctx, blocked)
    if init:
        ctx.add_init_script(init)
    return ctx


def watch(page, sink):
    page.on("console", lambda m: sink.append(("console." + m.type, m.text)) if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: sink.append(("pageerror", str(e))))
    page.on("requestfailed", lambda r: sink.append(("requestfailed", r.url + " " + str(r.failure))) if "localhost" in r.url or "googleapis" in r.url or "gstatic" in r.url else None)
    page.on("response", lambda r: sink.append(("http" + str(r.status), r.url)) if r.status >= 400 else None)


def server(path, data=None):
    req = urllib.request.Request(LOCAL + path, data=json.dumps(data).encode() if data is not None else None, method="POST" if data is not None else "GET", headers={"content-type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read() or b"null")


OVERFLOW_JS = """() => { const w = document.documentElement.clientWidth;
  const bad = [...document.querySelectorAll('body *')].filter(e => { const r = e.getBoundingClientRect(); if (r.width === 0) return false;
    let p = e.parentElement; while (p && p !== document.body) { const cs = getComputedStyle(p); if (/(auto|scroll|hidden|clip)/.test(cs.overflowX)) return false; p = p.parentElement; }
    return r.right > w + 1 || r.left < -1; })
    .map(e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (e.className && typeof e.className === 'string' ? '.' + e.className.trim().split(/\\s+/).join('.') : '') + ' [' + Math.round(e.getBoundingClientRect().left) + ',' + Math.round(e.getBoundingClientRect().right) + ']');
  return { sw: document.documentElement.scrollWidth, cw: w, bad: [...new Set(bad)].slice(0, 12) }; }"""

SMALL_INPUT_JS = """() => [...document.querySelectorAll('input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=hidden]),select,textarea,[contenteditable=true]')]
  .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && parseFloat(getComputedStyle(e).fontSize) < 16; })
  .map(e => (e.id || e.name || e.getAttribute('aria-label') || e.placeholder || e.tagName) + ':' + getComputedStyle(e).fontSize)"""

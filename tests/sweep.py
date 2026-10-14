"""Route sweep: every route on one device profile. Usage: python3 sweep.py <device-key> <outdir>
Reports page errors, console errors, failed requests, sideways overflow, inputs that make iOS zoom,
and saves a screenshot of each route."""
import sys, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright
from hx import *

ROUTES = ["", "#/home/steps", "#/study", "#/study/terms", "#/study/eju", "#/study/eju/dates", "#/study/eju/answers", "#/study/eju/papers",
          "#/study/apply", "#/study/apply/statement", "#/study/apply/interview", "#/study/apply/essay",
          "#/schools", "#/schools/pre", "#/schools/list", "#/schools/match", "#/schools/guide",
          "#/scholarships", "#/scholarships/saved", "#/scholarships/check", "#/scholarships/guide",
          "#/blog", "#/blog/sample-english", "#/blog/sample-burmese", "#/blog/no-such-post",
          "#/faq", "#/class", "#/privacy", "#/write", "#/exam", "#/apply/money", "#/nonsense"]

DEVICES = {
    "iphone-se": ("iPhone SE", {}),
    "iphone-14": ("iPhone 14", {}),
    "iphone-14-land": ("iPhone 14 landscape", {}),
    "pixel-7": ("Pixel 7", {}),
    "galaxy-360": ("Galaxy S8", {}),
    "ipad-mini": ("iPad Mini", {}),
    "ipad-pro-land": ("iPad Pro 11 landscape", {}),
    "win-laptop": (None, {"viewport": {"width": 1536, "height": 730}, "device_scale_factor": 1.25, "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0"}),
    "desktop-1280": (None, {"viewport": {"width": 1280, "height": 800}}),
    "desktop-1024": (None, {"viewport": {"width": 1024, "height": 700}}),
    "narrow-320": (None, {"viewport": {"width": 320, "height": 640}, "is_mobile": True, "has_touch": True, "device_scale_factor": 2}),
}


# two sample posts, only in the test stand-in, so the blog list and post pages have something to show
SAMPLE_EN = """This sample post checks how the blog reads: plain paragraphs, **bold words**, *a little italic*, and [a link to the scholarships](#/scholarships).

## A heading inside a post

A second paragraph that runs long enough to wrap onto several lines on a phone, so the line length and the line spacing can be judged at a glance, the way a student would read it on the train home.

- First point in a list
- Second point, which is a little longer than the first one
- Third point

> A quoted line, set apart from the text.

### A smaller heading

| Subject | Time | Score |
|---|---|---|
| Maths Course 2 | 80 minutes | 200 |
| Physics and chemistry | 80 minutes | 200 |

The area under $y = x^2$ from 0 to 1 is $\\frac{1}{3}$.

$$\\int_0^1 x^2\\,dx = \\frac{1}{3}$$
"""
SAMPLE_MY = """ဂျပန်နိုင်ငံရှိ တက္ကသိုလ်များသို့ ဝင်ခွင့်ရရန် EJU စာမေးပွဲကို နှစ်စဉ် ဖြေဆိုကြပါသည်။ ဤစာသည် စမ်းသပ်ရန်အတွက်သာ ဖြစ်ပါသည်။

## ခေါင်းစဉ်ငယ်

သင်္ချာ၊ ရူပဗေဒနှင့် ဓာတုဗေဒ ဘာသာရပ်များကို ပြင်ဆင်ရာတွင် အချိန်ဇယားကို စနစ်တကျ စီစဉ်ထားရန် အရေးကြီးပါသည်။

- ပထမအချက်
- ဒုတိယအချက်
"""
def seed_posts():
    for slug, title, lang, body, summary in [
        ("sample-english", "A sample post to check how the blog reads", "en", SAMPLE_EN, "Headings, a list, a table and some maths, to judge the type."),
        ("sample-burmese", "ဘလော့ဂ် စာမျက်နှာ စမ်းသပ်ချက်", "my", SAMPLE_MY, "မြန်မာစာ စာကြောင်းအကွာအဝေး စစ်ဆေးရန်"),
    ]:
        server("/__fake/put", {"p": "posts/" + slug, "data": {"status": "published", "title": title, "lang": lang, "date": "2026-10-14T09:00", "summary": summary, "body": body, "tags": ["test"]}})

key, outdir = sys.argv[1], sys.argv[2]
seed_posts()
os.makedirs(outdir, exist_ok=True)
name, extra = DEVICES[key]
report = {"device": key, "routes": {}}
with sync_playwright() as p:
    b = launch(p)
    dev = D(p, name) if name else {}
    blocked = []
    ctx = new_ctx(p, b, dev, blocked=blocked, **extra)
    # a saved school and scholarship so the lists are not empty
    ctx.add_init_script("""(()=>{ if(!localStorage.getItem('wandering-eric:v6')) localStorage.setItem('wandering-eric:v6', JSON.stringify({saved:{}, sschol:{}})); })()""")
    pg = ctx.new_page()
    ev = []
    watch(pg, ev)
    for r in ROUTES:
        ev.clear(); blocked.clear()
        pg.goto(BASE + r)
        pg.wait_for_timeout(900 if r.startswith("#/blog") else 450)
        ov = pg.evaluate(OVERFLOW_JS)
        small = pg.evaluate(SMALL_INPUT_JS) if dev.get("has_touch") or extra.get("has_touch") else []
        nm = (r.replace("#/", "").replace("/", "_") or "home")
        pg.screenshot(path=f"{outdir}/{key}__{nm}.png", full_page=False)
        report["routes"][r or "/"] = {"hash": pg.evaluate("location.hash"), "title": pg.title(), "overflow": ov, "smallInputs": small, "events": list(ev), "blocked": list(blocked)}
    b.close()
json.dump(report, open(f"{outdir}/{key}.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
bad = {r: v for r, v in report["routes"].items() if v["events"] or v["blocked"] or v["overflow"]["sw"] > v["overflow"]["cw"] or v["overflow"]["bad"] or v["smallInputs"]}
print(key, "routes:", len(report["routes"]), "with issues:", len(bad))
for r, v in bad.items():
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::error title=Page check ({BROWSER}, {key})::{r}: overflow {v['overflow']['bad'][:3]} small inputs {v['smallInputs'][:3]} errors {[e[1][:120] for e in v['events'][:2]]}", flush=True)
    print(" ", r, "| sw/cw", v["overflow"]["sw"], v["overflow"]["cw"], "| bad", v["overflow"]["bad"][:4], "| small", v["smallInputs"][:4], "| ev", v["events"][:3], "| blocked", v["blocked"][:3])

sys.exit(1 if bad else 0)

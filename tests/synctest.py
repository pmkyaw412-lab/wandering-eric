"""Sign-in, saving and sync tests with two simulated devices (separate browser contexts) on one fake account.
Usage: python3 synctest.py [only-test-name ...]"""
import sys, json, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright
from hx import *

KEY = "wandering-eric:v6"
RESULTS = []
ONLY = set(sys.argv[1:])


def real_errors(errs):
    """Page errors from the site. WebKit on macOS reports the test stand-in's own cancelled polling requests
    (to /__fake/) as page errors; those are not the site's and are left out."""
    return [e for e in errs if not ("__fake/" in e and "access control checks" in e)]


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> " + str(detail)[:400]), flush=True)
    if not ok and os.environ.get("GITHUB_ACTIONS"):
        print(f"::error title=Sync test ({BROWSER})::{name}: {str(detail)[:300]}", flush=True)


def local(pg):
    return json.loads(pg.evaluate(f"localStorage.getItem('{KEY}')") or "{}")


def cloud(uid="student-1"):
    return server("/__fake/dump")["db"].get("users/" + uid)


def device(p, b, dev="iPhone 14", user=None, errs=None, latency=None, extra_init=""):
    init = ""
    if user:
        init += "window.__FAKE_SIGNIN_USER=" + json.dumps(user) + ";"
    if latency is not None:
        init += f"window.__FAKE_LATENCY={latency};"
    init += extra_init
    ctx = new_ctx(p, b, D(p, dev) if dev else {}, init=init or None)
    pg = ctx.new_page()
    if errs is not None:
        pg.on("pageerror", lambda e: errs.append(str(e)))
    return ctx, pg


def sign_in(pg):
    pg.click("#acct button")
    pg.wait_for_selector("#dlgbtn")
    pg.wait_for_timeout(300)
    pg.click("#dlgbtn")
    pg.wait_for_function("document.querySelector('#acct button.in')", timeout=5000)
    pg.wait_for_timeout(900)


def school_keys(pg, n):
    pg.goto(BASE + "#/schools")
    pg.wait_for_timeout(400)
    return pg.eval_on_selector_all('[data-act="save"]', "els=>els.map(e=>e.getAttribute('data-k'))")[:n]


def toggle_school(pg, k):
    pg.click(f'[data-act="save"][data-k="{k}"]')


def saved_ui(pg):
    pg.goto(BASE + "#/schools/list")
    pg.wait_for_timeout(300)
    return sorted(set(pg.eval_on_selector_all('[data-k]', "els=>els.map(e=>e.getAttribute('data-k'))")))


def want(name):
    return not ONLY or name in ONLY


with sync_playwright() as p:
    b = launch(p)

    # ---------- signed out ----------
    if want("signedout"):
        server("/__fake/reset", {})
        errs = []
        ctx, pg = device(p, b, errs=errs)
        pg.goto(BASE); pg.wait_for_timeout(300)
        ks = school_keys(pg, 3)
        for k in ks[:2]:
            toggle_school(pg, k); pg.wait_for_timeout(100)
        pg.wait_for_timeout(400)
        pg.reload(); pg.wait_for_timeout(400)
        check("signed out: saved schools survive a reload", set(ks[:2]) <= set(local(pg).get("saved", {}).keys()), local(pg).get("saved"))
        # tap Save and leave the page straight away (phones: switching apps right after a tap)
        pg.goto(BASE + "#/schools"); pg.wait_for_timeout(400)
        toggle_school(pg, ks[2])
        pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))")  # nothing hidden yet; the next line is the real exit
        pg.goto("about:blank")
        pg2 = ctx.new_page(); pg2.goto(BASE); pg2.wait_for_timeout(300)
        check("signed out: a save made just before leaving the page is kept", ks[2] in local(pg2).get("saved", {}), list(local(pg2).get("saved", {}).keys()))
        check("signed out: no script errors", not real_errors(errs), real_errors(errs))
        ctx.close()

    # ---------- sign in, second device, removal while the other device is open ----------
    if want("twodevices"):
        server("/__fake/reset", {})
        errs = []
        A, pa = device(p, b, "iPhone 14", errs=errs)
        pa.goto(BASE); pa.wait_for_timeout(300)
        ks = school_keys(pa, 4)
        toggle_school(pa, ks[0]); toggle_school(pa, ks[1]); pa.wait_for_timeout(500)
        sign_in(pa)
        c = cloud() or {}
        check("sign in: items saved before signing in reach the account", set(ks[:2]) <= set((c.get("saved") or {}).keys()), c)
        dump = server("/__fake/dump")
        check("sign in: no write refused by the security rules", not [x for x in dump["log"] if x["op"] == "denied"], [x for x in dump["log"] if x["op"] == "denied"])
        Bc, pb = device(p, b, None, errs=errs)
        pb.set_viewport_size({"width": 1280, "height": 800})
        pb.goto(BASE); pb.wait_for_timeout(300)
        sign_in(pb); pb.wait_for_timeout(600)
        check("second device: sees the list after signing in", set(ks[:2]) <= set(local(pb).get("saved", {}).keys()), local(pb).get("saved"))
        # laptop removes one, phone is open on another page
        pa.goto(BASE + "#/study"); pa.wait_for_timeout(200)
        pb.goto(BASE + "#/schools"); pb.wait_for_timeout(300)
        toggle_school(pb, ks[0]); pb.wait_for_timeout(2600)
        check("live sync: a removal on the laptop reaches the open phone", ks[0] not in local(pa).get("saved", {}), list(local(pa).get("saved", {}).keys()))
        check("two devices: no script errors", not real_errors(errs), real_errors(errs))
        A.close(); Bc.close()

    # ---------- removal made while the other device was closed comes back? ----------
    if want("resurrect"):
        server("/__fake/reset", {})
        errs = []
        A, pa = device(p, b, "iPhone 14", errs=errs)
        pa.goto(BASE); pa.wait_for_timeout(300)
        ks = school_keys(pa, 3)
        for k in ks: toggle_school(pa, k); pa.wait_for_timeout(80)
        pa.wait_for_timeout(400)
        sign_in(pa); pa.wait_for_timeout(1500)
        state_a = A.storage_state()
        A.close()  # phone closed
        Bc, pb = device(p, b, None, errs=errs)
        pb.goto(BASE); pb.wait_for_timeout(300); sign_in(pb); pb.wait_for_timeout(600)
        pb.goto(BASE + "#/schools"); pb.wait_for_timeout(300)
        toggle_school(pb, ks[1]); pb.wait_for_timeout(2600)  # laptop removes it
        check("setup: the removal reached the cloud", ks[1] not in (cloud() or {}).get("saved", {}), (cloud() or {}).get("saved"))
        Bc.close()
        # phone opens the site again later
        A2 = b.new_context(**D(p, "iPhone 14"), storage_state=state_a); install_routes(A2)
        pa2 = A2.new_page(); pa2.on("pageerror", lambda e: errs.append(str(e)))
        pa2.goto(BASE); pa2.wait_for_timeout(3000)
        check("reopened phone: a school removed on the laptop stays removed", ks[1] not in local(pa2).get("saved", {}), list(local(pa2).get("saved", {}).keys()))
        check("reopened phone: the cloud still has it removed", ks[1] not in (cloud() or {}).get("saved", {}), list((cloud() or {}).get("saved", {}).keys()))
        check("resurrect: no script errors", not real_errors(errs), real_errors(errs))
        A2.close()

    # ---------- quick taps while a write is on its way ----------
    if want("race"):
        server("/__fake/reset", {})
        errs = []
        A, pa = device(p, b, "iPhone 14", errs=errs, latency=600)
        pa.goto(BASE); pa.wait_for_timeout(300); sign_in(pa); pa.wait_for_timeout(1500)
        ks = school_keys(pa, 6)
        lost = []
        for k in ks:
            toggle_school(pa, k)
            pa.wait_for_timeout(1550)  # a student tapping Save on a school every second and a half
        pa.wait_for_timeout(3500)
        l = set(local(pa).get("saved", {}).keys()); c = set(((cloud() or {}).get("saved") or {}).keys())
        check("quick taps: every school stays saved on the phone", set(ks) <= l, sorted(set(ks) - l))
        check("quick taps: every school reaches the account", set(ks) <= c, sorted(set(ks) - c))
        check("race: no script errors", not real_errors(errs), real_errors(errs))
        A.close()

    # ---------- typing a statement while signed in ----------
    if want("typing"):
        server("/__fake/reset", {})
        errs = []
        A, pa = device(p, b, "iPhone 14", errs=errs)
        pa.goto(BASE); pa.wait_for_timeout(300); sign_in(pa); pa.wait_for_timeout(1500)
        pa.goto(BASE + "#/study/apply/statement"); pa.wait_for_timeout(400)
        ta = pa.locator("textarea[data-stmt]").first
        ta.click()
        sid = ta.get_attribute("data-stmt")
        typed = ""
        focus_lost = 0
        for chunk in ["When I was fifteen ", "my village had no bridge, ", "so I wanted to build one. "]:
            pa.keyboard.type(chunk, delay=25); typed += chunk
            pa.wait_for_timeout(2600)  # pause to think; the save goes to the cloud
            still = pa.evaluate("(id)=>{const a=document.activeElement;return !!a&&a.getAttribute('data-stmt')===id}", sid)
            if not still:
                focus_lost += 1
                pa.locator(f'textarea[data-stmt="{sid}"]').click()
                pa.keyboard.press("End")
        val = pa.locator(f'textarea[data-stmt="{sid}"]').input_value()
        check("typing while signed in: the text box keeps focus while the draft syncs", focus_lost == 0, f"focus lost {focus_lost} times")
        check("typing while signed in: the text is intact", val == typed, repr(val))
        check("typing while signed in: the draft reaches the account", ((cloud() or {}).get("stmt") or {}).get(sid) == typed, (cloud() or {}).get("stmt"))
        writes = [x for x in server("/__fake/dump")["log"] if x["op"] == "set"]
        check("typing: no script errors", not real_errors(errs), real_errors(errs))
        A.close()

    # ---------- typing before Firebase has arrived (slow connection, returning user) ----------
    if want("slowboot"):
        server("/__fake/reset", {})
        errs = []
        A, pa = device(p, b, "iPhone 14", errs=errs)
        pa.goto(BASE); pa.wait_for_timeout(300); sign_in(pa); pa.wait_for_timeout(1500)
        pa.goto(BASE + "#/study/apply/statement"); pa.wait_for_timeout(300)
        sid = pa.locator("textarea[data-stmt]").first.get_attribute("data-stmt")
        pa.locator(f'textarea[data-stmt="{sid}"]').fill("Old text from yesterday."); pa.wait_for_timeout(2600)
        state = A.storage_state(); A.close()
        A3 = b.new_context(**D(p, "iPhone 14"), storage_state=state)
        install_routes(A3)
        A3.add_init_script("window.__FAKE_SLOWLOAD=4000;")
        pa3 = A3.new_page(); pa3.on("pageerror", lambda e: errs.append(str(e)))
        pa3.goto(BASE + "#/study/apply/statement"); pa3.wait_for_timeout(300)
        t = pa3.locator(f'textarea[data-stmt="{sid}"]')
        t.click(); pa3.keyboard.press("End"); pa3.keyboard.type(" New line typed today.", delay=20)
        pa3.wait_for_timeout(1200); pa3.keyboard.type(" More.", delay=60)
        pa3.wait_for_timeout(6000)
        val = t.input_value()
        foc = pa3.evaluate("(id)=>document.activeElement&&document.activeElement.getAttribute('data-stmt')===id", sid)
        check("slow connection: text typed before sign-in finished is kept", val.endswith("New line typed today. More."), repr(val))
        check("slow connection: the text box still has focus after sign-in finished", foc, foc)
        check("slow connection: today's text reaches the account", (((cloud() or {}).get("stmt") or {}).get(sid) or "").endswith("New line typed today. More."), (cloud() or {}).get("stmt"))
        check("slowboot: no script errors", not real_errors(errs), real_errors(errs))
        A3.close()

    # ---------- sign out right after a change ----------
    if want("signout"):
        server("/__fake/reset", {})
        errs = []
        A, pa = device(p, b, "iPhone 14", errs=errs)
        pa.goto(BASE); pa.wait_for_timeout(300); sign_in(pa); pa.wait_for_timeout(1500)
        ks = school_keys(pa, 1)
        toggle_school(pa, ks[0]); pa.wait_for_timeout(300)
        pa.click("#acct button"); pa.wait_for_selector('[data-act="signout"]'); pa.click('[data-act="signout"]')
        pa.wait_for_timeout(2500)
        check("sign out straight after saving: the save reaches the account", ks[0] in ((cloud() or {}).get("saved") or {}), (cloud() or {}).get("saved"))
        check("sign out: what you saved stays on this device", ks[0] in local(pa).get("saved", {}))
        check("signout: no script errors", not real_errors(errs), real_errors(errs))
        A.close()

    # ---------- delete account data ----------
    if want("delete"):
        server("/__fake/reset", {})
        errs = []
        A, pa = device(p, b, "iPhone 14", errs=errs)
        pa.goto(BASE); pa.wait_for_timeout(300)
        ks = school_keys(pa, 1); toggle_school(pa, ks[0]); pa.wait_for_timeout(400)
        sign_in(pa); pa.wait_for_timeout(1500)
        pa.click("#acct button"); pa.wait_for_selector('[data-act="delcloud"]'); pa.click('[data-act="delcloud"]')
        pa.wait_for_timeout(300)
        btns = pa.eval_on_selector_all("#dlg button", "b=>b.map(x=>x.textContent)")
        pa.click("#dlg .btn:not(.ghost)") if pa.locator("#dlg .btn:not(.ghost)").count() else None
        pa.wait_for_timeout(1500)
        check("delete account data: the cloud record is gone", cloud() is None, cloud())
        check("delete account data: signed out", pa.locator("#acct button.in").count() == 0)
        check("delete account data: the device keeps its list", ks[0] in local(pa).get("saved", {}))
        check("delete: no script errors", not real_errors(errs), real_errors(errs))
        A.close()

    # ---------- storage blocked (some private modes, some in-app browsers) ----------
    if want("nostorage"):
        errs = []
        A, pa = device(p, b, "iPhone 14", errs=errs, extra_init="Object.defineProperty(window,'localStorage',{get(){throw new DOMException('denied','SecurityError')}});")
        pa.goto(BASE + "#/schools/list"); pa.wait_for_timeout(500)
        warn = pa.locator(".warn").count()
        check("blocked storage: the page warns that nothing is kept", warn > 0)
        ks = school_keys(pa, 1); toggle_school(pa, ks[0]); pa.wait_for_timeout(300)
        check("blocked storage: saving still works for this visit", pa.locator(f'[data-act="save"][data-k="{ks[0]}"][aria-pressed="true"]').count() == 1)
        check("nostorage: no script errors", not real_errors(errs), real_errors(errs))
        A.close()

    # ---------- in-app browsers ----------
    if want("inapp"):
        for label, ua in [("Facebook iOS", "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 [FBAN/FBIOS;FBAV/520.0.0.40.104;FBBV/700000000;FBDV/iPhone15,2;FBMD/iPhone;FBSN/iOS;FBSV/18.5;FBSS/3;FBID/phone;FBLC/en_US;FBOP/5]"),
                          ("Messenger Android", "Mozilla/5.0 (Linux; Android 14; SM-A546E Build/UP1A.231005.007; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/140.0.0.0 Mobile Safari/537.36 [FB_IAB/Orca-Android;FBAV/480.0.0.40.110;]"),
                          ("Viber iOS", "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Viber/25.6.0"),
                          ("TikTok iOS", "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 musical_ly_40.1.0 JsSdk/2.0 NetType/WIFI Channel/App Store ByteLocale/en Region/MM BytedanceWebview/d8a21c6"),
                          ("Telegram iOS", "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1"),
                          ]:
            ctx = b.new_context(**{**D(p, "iPhone 14"), "user_agent": ua}); install_routes(ctx)
            pg = ctx.new_page(); pg.goto(BASE); pg.wait_for_timeout(300)
            pg.click("#acct button"); pg.wait_for_timeout(400)
            inapp = pg.locator(".dlg.inapp").count() > 0
            expect = label != "Telegram iOS"
            check(f"in-app browser ({label}): {'shows Open in your browser' if expect else 'normal sign-in'}", inapp == expect, f"inapp dialog shown={inapp}")
            ctx.close()

    # ---------- a new device with its own items meets an account that has items ----------
    if want("union"):
        server("/__fake/reset", {})
        errs = []
        A, pa = device(p, b, "iPhone 14", errs=errs)
        pa.goto(BASE); pa.wait_for_timeout(300)
        ks = school_keys(pa, 4)
        toggle_school(pa, ks[0]); pa.wait_for_timeout(400); sign_in(pa); pa.wait_for_timeout(1500); A.close()
        Bc, pb = device(p, b, None, errs=errs); pb.set_viewport_size({"width": 1366, "height": 768})
        pb.goto(BASE); pb.wait_for_timeout(300)
        toggle_school(pb, ks[1]) if pb.url.endswith("#/schools") else None
        pb.goto(BASE + "#/schools"); pb.wait_for_timeout(300); toggle_school(pb, ks[1]); pb.wait_for_timeout(400)
        sign_in(pb); pb.wait_for_timeout(1800)
        l = set(local(pb).get("saved", {}).keys()); c = set(((cloud() or {}).get("saved") or {}).keys())
        check("new device: its own items and the account's items are combined", {ks[0], ks[1]} <= l and {ks[0], ks[1]} <= c, (sorted(l), sorted(c)))
        check("union: no script errors", not real_errors(errs), real_errors(errs))
        Bc.close()

    # ---------- both devices open, both save at about the same time ----------
    if want("concurrent"):
        server("/__fake/reset", {})
        errs = []
        A, pa = device(p, b, "iPhone 14", errs=errs, latency=300)
        Bc, pb = device(p, b, None, errs=errs, latency=300); pb.set_viewport_size({"width": 1280, "height": 800})
        pa.goto(BASE); pa.wait_for_timeout(300); sign_in(pa); pa.wait_for_timeout(1200)
        pb.goto(BASE); pb.wait_for_timeout(300); sign_in(pb); pb.wait_for_timeout(1200)
        ks = school_keys(pa, 4); school_keys(pb, 1)
        toggle_school(pa, ks[0]); toggle_school(pb, ks[1]); pa.wait_for_timeout(5000)
        la = set(local(pa).get("saved", {}).keys()); lb = set(local(pb).get("saved", {}).keys()); c = set(((cloud() or {}).get("saved") or {}).keys())
        ok = {ks[0], ks[1]} <= la and {ks[0], ks[1]} <= lb and {ks[0], ks[1]} <= c
        check("both devices save at once: both schools end up everywhere", ok, (sorted(la), sorted(lb), sorted(c)))
        # statements: phone writes part 1 while the laptop writes part 2
        pa.goto(BASE + "#/study/apply/statement"); pb.goto(BASE + "#/study/apply/statement"); pa.wait_for_timeout(400)
        ids = pa.eval_on_selector_all("textarea[data-stmt]", "t=>t.map(x=>x.getAttribute('data-stmt'))")
        pa.locator(f'textarea[data-stmt="{ids[0]}"]').click(); pa.keyboard.type("Phone part one.", delay=15)
        pb.locator(f'textarea[data-stmt="{ids[1]}"]').click(); pb.keyboard.type("Laptop part two.", delay=15)
        pa.wait_for_timeout(1000)
        foc = pa.evaluate("(id)=>document.activeElement&&document.activeElement.getAttribute('data-stmt')===id", ids[0])
        pa.wait_for_timeout(4000)
        st = (cloud() or {}).get("stmt") or {}
        check("statement parts written on two devices are both kept", st.get(ids[0]) == "Phone part one." and st.get(ids[1]) == "Laptop part two.", st)
        check("the phone kept its text box while the laptop's part arrived", foc)
        pa.locator("h1").first.click(); pa.wait_for_timeout(500)
        check("after leaving the box, the phone shows the laptop's part", pa.locator(f'textarea[data-stmt="{ids[1]}"]').input_value() == "Laptop part two.", pa.locator(f'textarea[data-stmt="{ids[1]}"]').input_value())
        n0 = len([x for x in server("/__fake/dump")["log"] if x["op"] == "set"]); pa.wait_for_timeout(5000)
        n1 = len([x for x in server("/__fake/dump")["log"] if x["op"] == "set"])
        check("no endless writing back and forth when nothing changes", n1 == n0, f"{n1 - n0} writes in 5 idle seconds")
        check("concurrent: no script errors", not real_errors(errs), real_errors(errs))
        A.close(); Bc.close()

    # ---------- formula practice: quick taps on flashcards ----------
    if want("flashcards"):
        server("/__fake/reset", {})
        errs = []
        A, pa = device(p, b, "iPhone 14", errs=errs, latency=500)
        pa.goto(BASE); pa.wait_for_timeout(300); sign_in(pa); pa.wait_for_timeout(1200)
        pa.goto(BASE + "#/study"); pa.wait_for_timeout(400)
        pa.click('[data-act="fmode"][data-v="cards"]'); pa.wait_for_timeout(300)
        n = 0
        for i in range(12):
            if pa.locator('[data-act="fshow"]').count(): pa.click('[data-act="fshow"]')
            pa.wait_for_timeout(150)
            if pa.locator('[data-act="fknow"]').count(): pa.click('[data-act="fknow"]'); n += 1
            pa.wait_for_timeout(500)
        pa.wait_for_timeout(4000)
        lf = local(pa).get("frec", {}); cf = (cloud() or {}).get("frec") or {}
        tl = sum(v.get("k", 0) for v in lf.values()); tc = sum(v.get("k", 0) for v in cf.values())
        check("flashcards: every 'I know it' is counted on the phone", tl == n, f"{tl} of {n}")
        check("flashcards: every 'I know it' reaches the account", tc == n, f"{tc} of {n}")
        check("flashcards: no script errors", not real_errors(errs), real_errors(errs))
        A.close()

    # ---------- offline when the site opens, then back online ----------
    if want("offline"):
        server("/__fake/reset", {})
        errs = []
        A, pa = device(p, b, "iPhone 14", errs=errs)
        pa.goto(BASE); pa.wait_for_timeout(300); sign_in(pa); pa.wait_for_timeout(1200)
        state = A.storage_state(); A.close()
        A2 = b.new_context(**D(p, "iPhone 14"), storage_state=state); install_routes(A2)
        A2.add_init_script("window.__FAKE_OFFLINE=true;")
        pa2 = A2.new_page(); pa2.on("pageerror", lambda e: errs.append(str(e)))
        pa2.goto(BASE); pa2.wait_for_timeout(1500)
        ks = school_keys(pa2, 1); toggle_school(pa2, ks[0]); pa2.wait_for_timeout(2000)
        pa2.evaluate("window.__FAKE_OFFLINE=false; window.dispatchEvent(new Event('online'))"); pa2.wait_for_timeout(3000)
        check("offline start: a save made offline reaches the account once back online", ks[0] in ((cloud() or {}).get("saved") or {}), (cloud() or {}).get("saved"))
        check("offline: no script errors", not real_errors(errs), real_errors(errs))
        A2.close()

    # ---------- a second person signs in on the same phone ----------
    if want("otheruser"):
        server("/__fake/reset", {})
        errs = []
        A, pa = device(p, b, "iPhone 14", errs=errs)
        pa.goto(BASE); pa.wait_for_timeout(300); sign_in(pa); pa.wait_for_timeout(1000)
        ks = school_keys(pa, 2); toggle_school(pa, ks[0]); pa.wait_for_timeout(2500)
        pa.click("#acct button"); pa.click('[data-act="signout"]'); pa.wait_for_timeout(1000)
        pa.evaluate("""window.__FAKE_SIGNIN_USER={uid:'student-2',email:'s2@example.com',displayName:'Su Su',photoURL:''}""")
        sign_in(pa); pa.wait_for_timeout(1500)
        c2 = cloud("student-2") or {}; c1 = cloud("student-1") or {}
        check("second account on the same phone: it gets the list that was on the phone", ks[0] in (c2.get("saved") or {}), c2.get("saved"))
        check("second account: the first account is untouched", list((c1.get("saved") or {}).keys()) == [ks[0]], c1.get("saved"))
        check("otheruser: no script errors", not real_errors(errs), real_errors(errs))
        A.close()

    # ---------- review 1: an idle text box must not overwrite newer text from another device ----------
    if want("stalebox"):
        server("/__fake/reset", {})
        errs = []
        A, pa = device(p, b, "iPhone 14", errs=errs)
        Bc, pb = device(p, b, None, errs=errs); pb.set_viewport_size({"width": 1280, "height": 800})
        pa.goto(BASE); pa.wait_for_timeout(300); sign_in(pa); pa.wait_for_timeout(1200)
        pb.goto(BASE); pb.wait_for_timeout(300); sign_in(pb); pb.wait_for_timeout(1200)
        pa.goto(BASE + "#/study/apply/statement"); pb.goto(BASE + "#/study/apply/statement"); pa.wait_for_timeout(500)
        sid = pa.locator("textarea[data-stmt]").first.get_attribute("data-stmt")
        pb.locator(f'textarea[data-stmt="{sid}"]').click(); pb.wait_for_timeout(300)   # laptop: caret in part 1, idle
        pa.locator(f'textarea[data-stmt="{sid}"]').click(); pa.keyboard.type("Written on the phone.", delay=10); pa.wait_for_timeout(3500)
        shown = pb.locator(f'textarea[data-stmt="{sid}"]').input_value()
        check("idle box on the laptop shows the phone's newer text", shown == "Written on the phone.", repr(shown))
        pb.keyboard.press("End"); pb.keyboard.type(" Laptop adds this.", delay=10); pb.wait_for_timeout(3500)
        st = ((cloud() or {}).get("stmt") or {}).get(sid)
        check("typing on the laptop builds on the phone's text instead of replacing it", st == "Written on the phone. Laptop adds this.", repr(st))
        check("stalebox: no script errors", not real_errors(errs), real_errors(errs))
        A.close(); Bc.close()

    # ---------- review 2: deleted account data must not come back from another open device ----------
    if want("delete2"):
        server("/__fake/reset", {})
        errs = []
        A, pa = device(p, b, "iPhone 14", errs=errs)
        Bc, pb = device(p, b, None, errs=errs); pb.set_viewport_size({"width": 1280, "height": 800})
        pa.goto(BASE); pa.wait_for_timeout(300); sign_in(pa); pa.wait_for_timeout(1000)
        ks = school_keys(pa, 2); toggle_school(pa, ks[0]); pa.wait_for_timeout(2500)
        pb.goto(BASE); pb.wait_for_timeout(300); sign_in(pb); pb.wait_for_timeout(1500)
        pa.click("#acct button"); pa.click('[data-act="delcloud"]'); pa.wait_for_timeout(300); pa.click("#dlg .btn:not(.ghost)"); pa.wait_for_timeout(1500)
        pb.goto(BASE + "#/schools"); pb.wait_for_timeout(300); toggle_school(pb, ks[1]); pb.wait_for_timeout(3000)
        check("after deleting on the phone, the laptop doesn't bring the record back", cloud() is None, cloud())
        check("the laptop is signed out after the deletion", pb.locator("#acct button.in").count() == 0)
        # the laptop was closed and opens later
        check("delete2: no script errors", not real_errors(errs), real_errors(errs))
        A.close(); Bc.close()

    # ---------- review 3: a refused write is not retried in a loop ----------
    if want("denyloop"):
        server("/__fake/reset", {})
        errs = []
        A, pa = device(p, b, "iPhone 14", errs=errs)
        pa.goto(BASE); pa.wait_for_timeout(300); sign_in(pa); pa.wait_for_timeout(1500)
        ks = school_keys(pa, 1)
        pa.evaluate("window.__FAKE_DENY=true"); toggle_school(pa, ks[0]); pa.wait_for_timeout(9000)
        n = pa.evaluate("globalThis.__FFB.denied||0")
        check("a refused write is tried once, not again and again", n <= 2, f"{n} attempts in 9 s")
        pa.evaluate("window.__FAKE_DENY=false")
        check("denyloop: no script errors", not real_errors(errs), real_errors(errs))
        A.close()

    # ---------- review 5: sync starts again after a failed start without an 'online' event ----------
    if want("retry"):
        server("/__fake/reset", {})
        errs = []
        A, pa = device(p, b, "iPhone 14", errs=errs)
        pa.goto(BASE); pa.wait_for_timeout(300); sign_in(pa); pa.wait_for_timeout(1200)
        state = A.storage_state(); A.close()
        A2 = b.new_context(**D(p, "iPhone 14"), storage_state=state); install_routes(A2)
        A2.add_init_script("window.__FAKE_OFFLINE=true;")
        pa2 = A2.new_page(); pa2.on("pageerror", lambda e: errs.append(str(e)))
        pa2.goto(BASE); pa2.wait_for_timeout(1500)
        ks = school_keys(pa2, 1); toggle_school(pa2, ks[0]); pa2.wait_for_timeout(500)
        pa2.evaluate("window.__FAKE_OFFLINE=false"); pa2.wait_for_timeout(9000)
        check("weak signal: sync recovers by itself and the save reaches the account", ks[0] in ((cloud() or {}).get("saved") or {}), (cloud() or {}).get("saved"))
        check("retry: no script errors", not real_errors(errs), real_errors(errs))
        A2.close()

    # ---------- review 2.1: two tabs on one laptop, typing in one while the other merges a change ----------
    if want("twotabs"):
        server("/__fake/reset", {})
        errs = []
        X, ta = device(p, b, None, errs=errs); ta.set_viewport_size({"width": 1280, "height": 800})
        ta.goto(BASE); ta.wait_for_timeout(300); sign_in(ta); ta.wait_for_timeout(1200)
        tb = X.new_page(); tb.set_viewport_size({"width": 1280, "height": 800}); tb.on("pageerror", lambda e: errs.append(str(e)))
        tb.goto(BASE + "#/study/apply/statement"); tb.wait_for_timeout(2000)
        Y, py = device(p, b, "iPhone 14", errs=errs); py.goto(BASE); py.wait_for_timeout(300); sign_in(py); py.wait_for_timeout(1200)
        ks = school_keys(py, 2)
        ta.goto(BASE + "#/schools"); ta.wait_for_timeout(300)
        tb.bring_to_front(); tb.locator('[data-stmt="trigger"]').click()
        text = "日本の大学で学びたい理由は三つある。" * 3
        toggle_school(py, ks[0])
        ta.goto(BASE + "#/schools"); ta.wait_for_timeout(300)
        aks = ta.eval_on_selector_all('[data-act="save"]', "els=>els.map(e=>e.getAttribute('data-k'))")[2:11]
        # the student types in tab B while tab A keeps saving schools (each save rewrites the stored copy)
        for i in range(9):
            tb.keyboard.type(text[i * 6:(i + 1) * 6], delay=45)
            ta.click(f'[data-act="save"][data-k="{aks[i]}"]')
        tb.wait_for_timeout(3500)
        v = tb.locator('[data-stmt="trigger"]').input_value()
        check("two tabs: nothing typed in one tab is lost when the other tab syncs", v == text, f"{len(v)} of {len(text)} characters: {v!r}")
        check("two tabs: the statement reaches the account", (((cloud() or {}).get("stmt") or {}).get("trigger") or "") == text, len(((cloud() or {}).get("stmt") or {}).get("trigger") or ""))
        check("two tabs: the phone's save shows in both tabs", ks[0] in local(tb).get("saved", {}), list(local(tb).get("saved", {}).keys()))
        lb = set(local(tb).get("saved", {}).keys()); cs = set(((cloud() or {}).get("saved") or {}).keys())
        check("two tabs: every school saved in tab A is kept, on the device and in the account", set(aks) <= lb and set(aks) <= cs, (sorted(set(aks) - lb), sorted(set(aks) - cs)))
        check("twotabs: no script errors", not real_errors(errs), real_errors(errs))
        X.close(); Y.close()

    # ---------- review 2.4: the first click after typing works while a sync is waiting ----------
    if want("clickafter"):
        server("/__fake/reset", {})
        errs = []
        X, ta = device(p, b, None, errs=errs); ta.set_viewport_size({"width": 1280, "height": 800})
        ta.goto(BASE); ta.wait_for_timeout(300); sign_in(ta); ta.wait_for_timeout(1200)
        Y, py = device(p, b, "iPhone 14", errs=errs); py.goto(BASE); py.wait_for_timeout(300); sign_in(py); py.wait_for_timeout(1200)
        ks = school_keys(py, 1)
        ta.goto(BASE + "#/study/apply/statement"); ta.wait_for_timeout(400)
        ta.locator('[data-stmt="trigger"]').click(); ta.keyboard.type("A first line.", delay=20)
        toggle_school(py, ks[0]); ta.wait_for_timeout(2800)  # the phone's save arrives while the laptop is in the box
        link = ta.locator('#main a[href="#/study/apply/interview"]').first
        link.evaluate("e=>e.scrollIntoView({block:'center'})"); ta.wait_for_timeout(100)
        box = link.bounding_box()
        ta.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2); ta.mouse.down(); ta.wait_for_timeout(120); ta.mouse.up()
        ta.wait_for_timeout(500)
        check("first click after typing still works when a sync was waiting", ta.evaluate("location.hash") == "#/study/apply/interview", ta.evaluate("location.hash"))
        check("clickafter: no script errors", not real_errors(errs), real_errors(errs))
        X.close(); Y.close()

    # ---------- two fresh tabs, nothing stored yet: the first saves of one must not blank the other ----------
    if want("freshtabs"):
        errs = []
        X, ta = device(p, b, None, errs=errs); ta.set_viewport_size({"width": 1280, "height": 800})
        tb = X.new_page(); tb.on("pageerror", lambda e: errs.append(str(e)))
        ta.goto(BASE + "#/schools"); tb.goto(BASE + "#/study/apply/statement"); ta.wait_for_timeout(500); tb.wait_for_timeout(500)
        tb.locator('[data-stmt="trigger"]').click(); tb.keyboard.type("最初の一文。", delay=30); tb.wait_for_timeout(600)
        k = ta.eval_on_selector_all('[data-act="save"]', "els=>els.map(e=>e.getAttribute('data-k'))")[0]
        ta.click(f'[data-act="save"][data-k="{k}"]'); ta.wait_for_timeout(800)
        tb.keyboard.type("次の文。", delay=30); tb.wait_for_timeout(800)
        v = tb.locator('[data-stmt="trigger"]').input_value(); st = local(tb)
        check("fresh tabs: the statement typed in one tab survives the other tab's first save", v == "最初の一文。次の文。" and (st.get("stmt") or {}).get("trigger") == v, (v, st.get("stmt")))
        check("fresh tabs: the other tab's saved school is kept", k in st.get("saved", {}), list(st.get("saved", {}).keys()))
        check("freshtabs: no script errors", not real_errors(errs), real_errors(errs))
        X.close()
    b.close()

fails = [r for r in RESULTS if not r[1]]
print(f"\n{len(RESULTS) - len(fails)} of {len(RESULTS)} passed")
sys.exit(1 if fails else 0)

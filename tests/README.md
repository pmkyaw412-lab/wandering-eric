# Tests

Browser tests for the site, run by `.github/workflows/test.yml` on every change to `index.html` or `tests/`
(and by hand from the Actions tab). They don't block publishing; they report.

- **Page checks** (`sweep.py`): every page on phone, iPad and desktop sizes. Fails on script errors, failed
  requests, pages that scroll sideways, and text boxes under 16 px (iPhones zoom into those).
- **Sign-in and sync** (`synctest.py`): two simulated devices on one account. Saving signed out, signing in,
  a second device, removals staying removed, quick taps, typing during sync, slow connections, signing out,
  deleting account data, two tabs, in-app browsers (Facebook, Messenger, Viber, TikTok).
- **Engines**: Chromium (Chrome, Edge), Firefox, WebKit (Safari's engine), on Linux, Windows and macOS.

Firebase is replaced by a stand-in (`fake/`, served by `server.mjs`) that behaves like Firestore where it matters:
writes show locally at once and are confirmed later, server timestamps resolve on confirmation, maps come back
sorted, and the `users/{uid}` rules from `firestore.rules` are enforced. Real accounts are never touched.

Run locally:

```
npm install && npm run build
pip install playwright && python -m playwright install chromium firefox webkit
python tests/run.py                       # Chromium
TEST_BROWSER=webkit python tests/run.py   # Safari's engine
python tests/synctest.py race twotabs     # with the server running: just some sync tests
```

Without internet (a sandbox), set `LOCAL_CDN=1` and install `katex@0.16.9 marked@18.0.13 @fontsource/lexend
@fontsource/biz-udpgothic @fontsource/noto-sans-myanmar` into `tests/node_modules`.

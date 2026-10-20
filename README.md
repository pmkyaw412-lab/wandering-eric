# Wandering Eric

The EJU and admission guide for students from Myanmar, with Eric's blog. One HTML file, no framework, published on GitHub Pages.

- `index.html` is the whole site (v16). Routes are hash routes: `#/study` (with tabs `eju` and `apply`), `#/schools`, `#/scholarships`, `#/blog`, `#/faq`, `#/class`, `#/privacy`, and `#/write` (Eric's writing desk). The old `#/exam` and `#/apply` addresses redirect to their new homes (see `oldRoute` in `index.html`).
- The school list is sorted by default by QS 2027 place, then by each university's highest-faculty 偏差値 (河合塾, from 日本の学校 and Kei-Net, collected October 2026; the `HEN` table in `index.html`), then north to south. The 偏差値 is used only for ordering and is never shown.
- `posts/` holds blog posts written as Markdown files (empty since v15; posts are written in the site's writing desk). `media/` holds their images.
- The blog and the writing desk use their own type (v15): Noto Sans, regular weight for reading, semi-bold for titles, in a column of about 70 characters, after Wait But Why. The rest of the site keeps Lexend.
- `scripts/build.mjs` copies everything into `dist/` and writes `dist/posts/index.json`, the list the Blog page reads. It also checks Burmese text for Zawgyi and converts it to Unicode.
- `.github/workflows/pages.yml` runs that build on every push to `main` and publishes `dist/` to GitHub Pages.
- `.pages.yml` describes the posts for Pages CMS, the writing dashboard.
- `firestore.rules` is a copy of the Firestore security rules used in the Firebase console. Publish it there whenever it changes (Firestore Database, Rules, paste, Publish).

## Writing a post

The site has its own writing desk (v13). Nothing to install, no GitHub.

1. Open the site, tap the account button at the top right and sign in with Google as **pmkyaw412@gmail.com** or **pmkyawclass@gmail.com**.
2. Open the account menu and choose **Write a Post** (or go to `#/write`). The Blog page also shows Write a post and Your posts for these two accounts.
3. Write. The toolbar has headings, bold, italic, links, lists, quotes, photos, formulas (∑), tables and dividers. Typing `## `, `- ` or `1. ` at the start of a line works too.
4. Drafts save themselves as you type, on the device and in your account. Press **Preview** to see the post as readers will, then **Publish**.
5. Later edits stay private until you press **Update**. Post settings (under the post) hold the summary, cover photo, tags, date and web address, plus Unpublish and Delete.

How it is stored: published posts in Firestore `posts/<web-address>` (anyone can read; the Blog reads them over Firestore's REST API, so readers never download Firebase), drafts in `drafts/<id>` (only the two accounts), photos in `media/<id>` (shrunk in the browser to under about 700 KB). The Markdown files in `posts/` still show on the Blog; publishing one of them from the desk puts a copy in Firestore that replaces the file, and deleting one leaves a "removed" marker that hides it.

**One-time setup:** the rules in `firestore.rules` must be published in the Firebase console (Firestore Database, Rules, paste, Publish). Until then the desk can't save.

Pages CMS (`.pages.yml`, https://app.pagescms.org) still works for editing the Markdown files in `posts/` if ever needed.

## Building locally

```
npm ci
npm run build
npx serve dist
```

Then open the address it prints. The blog needs the site served over http (not opened as a file), because the posts are fetched.

## Accounts and cloud sync

Signing in with Google is optional. It is done with Firebase Authentication, and the student's saved items live in one Firestore document, `users/<uid>`, that only that student can read or write (see `firestore.rules`). The Firebase settings are in `FBC` near the end of `index.html`; they are safe to publish, because the rules protect the data. The Firestore database is in Tokyo (`asia-northeast1`).

Firebase is only downloaded by the browser when someone opens the sign-in sheet (so the Google window can open straight from the tap, which phones require), or on later visits for someone who has signed in before. Inside the Facebook, Messenger, Instagram, Viber, TikTok, LINE and similar in-app browsers, where Google refuses to sign anyone in, the sheet instead explains how to open the page in Safari or Chrome.

How syncing works (v14): each device keeps a copy of the account's record as it last saw it (`wandering-eric:sync` in local storage). When something arrives from the account, the site compares three versions (that copy, this device, the account), so a change made on one device and a change made on another are both kept, and something removed stays removed. Saves write only the items that changed (one saved school, one formula's record, one part of the statement) with `updateDoc`, so two devices saving at the same moment don't overwrite each other. Anything waiting is written straight away when the page is hidden or closed and before signing out. While a student is typing, the page doesn't redraw; text boxes are updated in place instead.

## Security (v16)

- The Firebase settings in `FBC` (including the `apiKey`) are meant to be public: every visitor's browser needs them. What protects the data is `firestore.rules` and the Firebase and Google Cloud console settings: Google as the only sign-in method, and the browser key limited to this site's addresses and to the Identity Toolkit, Token Service and Cloud Firestore APIs.
- The rules allow each student only their own record, only the fields the site writes and only of the right type; only Eric's two Google accounts can write posts, drafts and photos. They were tested in the Firestore emulator (30 checks) on 20 October 2026.
- `package-lock.json` is committed and the workflows run `npm ci --ignore-scripts`, so a build always uses the same, checked versions of its two packages. Only the deploy job can publish to Pages.
- KaTeX and marked load from their CDNs with Subresource Integrity, so the browser refuses any file that isn't the exact published version. When upgrading either, update the `integrity` values too.
- Blog posts are cleaned before they are shown: no scripts, event handlers, styles, classes or ids from a post reach the page.

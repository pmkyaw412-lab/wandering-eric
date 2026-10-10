# Wandering Eric

The EJU and admission guide for students from Myanmar, with Eric's blog. One HTML file, no framework, published on GitHub Pages.

- `index.html` is the whole site (v11). Routes are hash routes: `#/exam`, `#/study`, `#/schools`, `#/apply`, `#/faq`, `#/scholarships`, `#/blog`, `#/class`, `#/privacy`.
- `posts/` holds the blog posts, one Markdown file each. `media/` holds their images.
- `scripts/build.mjs` copies everything into `dist/` and writes `dist/posts/index.json`, the list the Blog page reads. It also checks Burmese text for Zawgyi and converts it to Unicode.
- `.github/workflows/pages.yml` runs that build on every push to `main` and publishes `dist/` to GitHub Pages.
- `.pages.yml` describes the posts for Pages CMS, the writing dashboard.
- `firestore.rules` is a copy of the Firestore security rules used in the Firebase console.

## Writing a post

1. Open https://app.pagescms.org, sign in with GitHub and open this repository.
2. Choose Blog posts, then Add an entry.
3. Fill in the title, the web address (lowercase letters, numbers and hyphens, in English), the date and the language. Write the post. Maths goes between dollar signs: `$x^2$` inside a sentence, or `$$ ... $$` on its own lines for a big formula.
4. Save. Pages CMS commits the file to `posts/`, the workflow rebuilds the site, and the post is live at `#/blog/<web-address>` about a minute later.

Tick Draft to keep a post off the site while you work on it. Burmese must be typed in Unicode (the standard keyboard on any modern phone or computer); if a Zawgyi text is pasted in, the build converts it and prints a warning in the Actions log, but the file itself stays as it was, so please fix it there.

## Building locally

```
npm install
npm run build
npx serve dist
```

Then open the address it prints. The blog needs the site served over http (not opened as a file), because the posts are fetched.

## Accounts and cloud sync

Signing in with Google is optional. It is done with Firebase Authentication, and the student's saved items live in one Firestore document, `users/<uid>`, that only that student can read or write (see `firestore.rules`). The Firebase settings are in `FBC` near the end of `index.html`; they are safe to publish, because the rules protect the data. The Firestore database is in Tokyo (`asia-northeast1`).

Firebase is only downloaded by the browser when someone opens the sign-in sheet (so the Google window can open straight from the tap, which phones require), or on later visits for someone who has signed in before. Inside the Facebook, Messenger, Instagram or LINE browsers, where Google refuses to sign anyone in, the sheet instead explains how to open the page in Safari or Chrome.

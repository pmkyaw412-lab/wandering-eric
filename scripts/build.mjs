// Builds the site into dist/: copies index.html and media/, copies each post, and writes posts/index.json,
// the list the Blog page reads. Burmese text is checked for Zawgyi and converted to Unicode when found.
// Runs in GitHub Actions (see .github/workflows/pages.yml) and locally with: node scripts/build.mjs
import { cp, mkdir, readdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import YAML from "yaml";

const root = process.cwd();
const out = path.join(root, "dist");
const postsDir = path.join(root, "posts");

await rm(out, { recursive: true, force: true });
await mkdir(path.join(out, "posts"), { recursive: true });
await cp(path.join(root, "index.html"), path.join(out, "index.html"));
for (const dir of ["media"]) {
  try { await stat(path.join(root, dir)); await cp(path.join(root, dir), path.join(out, dir), { recursive: true }); } catch {}
}
// GitHub Pages serves dist/ as is; .nojekyll keeps it from touching files that start with an underscore
await writeFile(path.join(out, ".nojekyll"), "");

let zawgyi = null;
try {
  const mod = await import("myanmar-tools");
  const mt = mod.default && mod.default.ZawgyiDetector ? mod.default : mod;
  zawgyi = { detector: new mt.ZawgyiDetector(), converter: new mt.ZawgyiConverter() };
} catch {
  console.warn("myanmar-tools is not installed, so posts are not checked for Zawgyi.");
}
const MYANMAR = /[က-႟ꩠ-ꩿ]/;
function toUnicode(text, label) {
  if (!zawgyi || !text || !MYANMAR.test(text)) return text;
  const p = zawgyi.detector.getZawgyiProbability(text);
  if (p > 0.9) {
    console.warn(`${label}: looks like Zawgyi (probability ${p.toFixed(2)}), converted to Unicode for the site. Please fix the source so it is Unicode.`);
    return zawgyi.converter.zawgyiToUnicode(text);
  }
  return text;
}

function isoDate(v) {
  if (v instanceof Date) return v.toISOString().slice(0, 10);
  if (v == null) return "";
  const s = String(v).trim();
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  return m ? `${m[1]}-${m[2]}-${m[3]}` : s;
}
function readingMinutes(body, lang) {
  const text = body.replace(/```[\s\S]*?```/g, " ").replace(/\$\$[\s\S]*?\$\$/g, " ").replace(/[#*_>`\[\]()!-]/g, " ");
  if (lang === "my" || lang === "ja") {
    const chars = text.replace(/\s/g, "").length;
    return Math.max(1, Math.round(chars / 500));
  }
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  return Math.max(1, Math.round(words / 200));
}

const files = (await readdir(postsDir)).filter((f) => f.endsWith(".md")).sort();
const posts = [];
const slugs = new Set();
for (const file of files) {
  let src = (await readFile(path.join(postsDir, file), "utf8")).replace(/^﻿/, "");
  const m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/.exec(src);
  if (!m) { console.warn(`${file}: no front matter, skipped.`); continue; }
  let fm;
  try { fm = YAML.parse(m[1]) || {}; } catch (e) { console.warn(`${file}: front matter could not be read (${e.message}), skipped.`); continue; }
  if (fm.draft === true) { console.log(`${file}: draft, left out.`); continue; }

  const title = toUnicode(String(fm.title || "").trim(), `${file} title`);
  const summary = toUnicode(String(fm.summary || "").trim(), `${file} summary`);
  const body = toUnicode(m[2], file);
  if (!title) { console.warn(`${file}: no title, skipped.`); continue; }
  const slug = String(fm.slug || file.replace(/\.md$/, "")).trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  if (!slug) { console.warn(`${file}: no usable slug (add a slug field in Latin letters), skipped.`); continue; }
  if (slugs.has(slug)) { console.warn(`${file}: the slug "${slug}" is already used by another post, skipped.`); continue; }
  slugs.add(slug);
  const lang = ["my", "en", "ja"].includes(fm.lang) ? fm.lang : (MYANMAR.test(title + body) ? "my" : "en");
  const tags = Array.isArray(fm.tags) ? fm.tags.map(String).filter(Boolean) : (fm.tags ? String(fm.tags).split(",").map((t) => t.trim()).filter(Boolean) : []);
  const cover = fm.cover ? String(fm.cover).replace(/^\//, "") : "";
  const when = fm.date instanceof Date ? fm.date.toISOString() : String(fm.date || "");
  posts.push({ slug, file, title, date: isoDate(fm.date), when, lang, summary, cover, tags, mins: readingMinutes(body, lang) });
  // the site strips the front matter itself; keep the file whole so the copy in dist matches the source
  await writeFile(path.join(out, "posts", file), `---\n${m[1]}\n---\n${body}`);
}
posts.sort((a, b) => (b.when || "").localeCompare(a.when || "") || a.slug.localeCompare(b.slug));
// "when" keeps the time, so the site can sort these together with posts written in its writing desk
posts.forEach((p) => { p.when = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(p.when) ? p.when.slice(0, 16) : p.date ? p.date + "T09:00" : ""; });
await writeFile(path.join(out, "posts", "index.json"), JSON.stringify({ generated: new Date().toISOString(), posts }, null, 1));
console.log(`${posts.length} post${posts.length === 1 ? "" : "s"} listed in dist/posts/index.json`);

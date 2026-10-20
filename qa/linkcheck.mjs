// Temporary QA script: check every external link in index.html.
// Usage: node qa/linkcheck.mjs index.html out.json
import fs from "node:fs";

const html = fs.readFileSync(process.argv[2], "utf8");
const out = process.argv[3] || "links.json";
const SKIP = /^https?:\/\/(www\.gstatic\.com|fonts\.(googleapis|gstatic)\.com|cdnjs\.cloudflare\.com|cdn\.jsdelivr\.net|firestore\.googleapis\.com|identitytoolkit\.googleapis\.com|securetoken\.googleapis\.com|www\.googleapis\.com|www\.w3\.org|accounts\.google\.com|apis\.google\.com|lh3\.googleusercontent\.com|localhost)/;
const urls = [...new Set((html.match(/https?:\/\/[^"'\s<>)\\\]]+/g) || [])
  .map((u) => u.replace(/&amp;/g, "&").replace(/[.,;:]+$/, "")))]
  .filter((u) => !SKIP.test(u) && u.length > 12);

const LIMIT = +process.env.LIMIT || 0;
if (LIMIT) urls.splice(LIMIT);
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const SOFT404 = /404|not\s*found|見つかりません|ページがありません|存在しません|お探しのページ|削除された|移動しました|エラー|error/i;

async function readHead(res) {
  const reader = res.body.getReader();
  let got = 0;
  const chunks = [];
  while (got < 250000) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(Buffer.from(value));
    got += value.length;
  }
  try { await reader.cancel(); } catch {}
  return Buffer.concat(chunks);
}

async function check(url) {
  const t0 = Date.now();
  for (let attempt = 0; attempt < 2; attempt++) {
    const ac = new AbortController();
    const timer = setTimeout(() => ac.abort(), 30000);
    try {
      const res = await fetch(url, {
        redirect: "follow",
        signal: ac.signal,
        headers: { "user-agent": UA, accept: "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8", "accept-language": "ja,en;q=0.8" },
      });
      const ct = res.headers.get("content-type") || "";
      let title = "";
      if (/html/i.test(ct) && res.body) {
        const buf = await readHead(res);
        let text = buf.toString("utf8");
        const cs = (/charset=([\w-]+)/i.exec(ct) || /<meta[^>]+charset=["']?([\w-]+)/i.exec(text) || [])[1];
        if (cs && !/utf-?8/i.test(cs)) { try { text = new TextDecoder(cs.toLowerCase()).decode(buf); } catch {} }
        title = ((/<title[^>]*>([\s\S]*?)<\/title>/i.exec(text) || [])[1] || "").replace(/\s+/g, " ").trim().slice(0, 160);
      } else if (res.body) {
        try { await res.body.cancel(); } catch {}
      }
      clearTimeout(timer);
      if ((res.status >= 500 || res.status === 429) && attempt === 0) { await sleep(5000); continue; }
      return { url, status: res.status, final: res.url !== url ? res.url : "", ct: ct.split(";")[0], title, soft404: !!(title && SOFT404.test(title)), ms: Date.now() - t0 };
    } catch (e) {
      clearTimeout(timer);
      if (attempt === 0) { await sleep(4000); continue; }
      return { url, status: 0, err: String((e && e.cause && (e.cause.code || e.cause.message)) || (e && e.name) || e).slice(0, 160), ms: Date.now() - t0 };
    }
  }
}

// a pool: 24 at once overall, 2 at once per host
const host = (u) => { try { return new URL(u).host; } catch { return u; } };
const busy = new Map();
const queue = urls.slice();
const results = [];
let running = 0;
await new Promise((done) => {
  const pump = () => {
    if (!queue.length && !running) return done();
    for (let i = 0; i < queue.length && running < 24; i++) {
      const h = host(queue[i]);
      if ((busy.get(h) || 0) >= 2) continue;
      const u = queue.splice(i, 1)[0];
      i--;
      running++;
      busy.set(h, (busy.get(h) || 0) + 1);
      check(u).then((r) => {
        results.push(r);
        running--;
        busy.set(h, busy.get(h) - 1);
        if (results.length % 100 === 0) console.log(results.length + " of " + urls.length + " checked");
        pump();
      });
    }
  };
  pump();
});
results.sort((a, b) => a.url.localeCompare(b.url));
fs.writeFileSync(out, JSON.stringify({ checked: new Date().toISOString(), total: results.length, results }, null, 1));
const bad = results.filter((r) => r.status === 0 || r.status >= 400 || r.soft404);
console.log("checked " + results.length + ", problems " + bad.length);
for (const r of bad) console.log(r.status, r.err || "", r.soft404 ? "soft404: " + r.title : "", r.url);

// Local test server: serves the built site, local copies of the CDN files, and a fake Firestore backend.
// Usage: node server.mjs <distDir> [port]
import http from "node:http";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const dist = path.resolve(process.argv[2] || "dist");
const port = +(process.argv[3] || 8000);
const NM = path.join(here, "node_modules");
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".md": "text/markdown; charset=utf-8", ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".svg": "image/svg+xml", ".gif": "image/gif", ".ico": "image/x-icon" };
const ADMINS = ["pmkyaw412@gmail.com", "pmkyawclass@gmail.com"];
const USER_KEYS = ["saved", "sschol", "frec", "stars", "steps", "docs", "stmt", "essay", "target", "elig", "mq", "flang", "fess", "fdiag", "updatedAt", "v"];

let DB = {}; // path -> data
let LOG = []; // writes, for assertions
function resolveTs(v) {
  if (Array.isArray(v)) return v.map(resolveTs);
  // Firestore hands map fields back sorted by key, not in the order they were written
  if (v && typeof v === "object") { if (v.__st) return { __ts: Date.now() }; const o = {}; for (const k of Object.keys(v).sort()) o[k] = resolveTs(v[k]); return o; }
  return v;
}
function allowed(op, p, uid, email, data) {
  const [coll, id] = p.split("/");
  const admin = !!uid && ADMINS.includes(email);
  if (coll === "users") {
    if (!uid || uid !== id) return false;
    if (op === "set") { const keys = Object.keys(data || {}); return keys.every((k) => USER_KEYS.includes(k)) && keys.length <= 20; }
    return true;
  }
  if (coll === "posts") return op === "get" || op === "list" ? true : admin && /^[a-z0-9]+(-[a-z0-9]+)*$/.test(id) && id.length <= 80;
  if (coll === "drafts") return admin;
  if (coll === "media") return op === "get" ? true : admin;
  return false;
}
function toFs(v) {
  if (v === null || v === undefined) return { nullValue: null };
  if (typeof v === "string") return { stringValue: v };
  if (typeof v === "boolean") return { booleanValue: v };
  if (typeof v === "number") return Number.isInteger(v) ? { integerValue: String(v) } : { doubleValue: v };
  if (Array.isArray(v)) return { arrayValue: { values: v.map(toFs) } };
  if (v.__ts) return { timestampValue: new Date(v.__ts).toISOString() };
  const f = {}; for (const k of Object.keys(v)) f[k] = toFs(v[k]); return { mapValue: { fields: f } };
}
function fsDocJSON(p, data) { const f = {}; for (const k of Object.keys(data)) f[k] = toFs(data[k]); return { name: "projects/wandering-eric/databases/(default)/documents/" + p, fields: f }; }

async function body(req) { const chunks = []; for await (const c of req) chunks.push(c); return Buffer.concat(chunks).toString("utf8"); }
function send(res, code, obj, type) { res.writeHead(code, { "content-type": type || "application/json", "cache-control": "no-store", "access-control-allow-origin": "*" }); res.end(typeof obj === "string" || Buffer.isBuffer(obj) ? obj : JSON.stringify(obj)); }

async function fontCSS() {
  const parts = [];
  const pick = [["lexend", ["400", "500", "600"]], ["biz-udpgothic", ["400", "700"]], ["noto-sans-myanmar", ["400", "500", "600", "700"]], ["noto-sans", ["400", "600", "400-italic"]]];
  for (const [pkg, ws] of pick) for (const w of ws) {
    try { let css = await readFile(path.join(NM, "@fontsource", pkg, w + ".css"), "utf8"); css = css.replace(/url\(\.\/files\//g, `url(http://localhost:8000/__cdn/fonts/${pkg}/files/`); parts.push(css); } catch (e) {}
  }
  return parts.join("\n").replace(/font-family:\s*'Lexend'/g, "font-family:'Lexend'").replace(/font-family:\s*'BIZ UDPGothic'/g, "font-family:'BIZ UDPGothic'");
}

const server = http.createServer(async (req, res) => {
  const u = new URL(req.url, "http://localhost");
  const uid = req.headers["x-uid"] || "", email = req.headers["x-email"] || "";
  try {
    if (u.pathname === "/__fake/doc") {
      const p = u.searchParams.get("p");
      if (req.method === "GET") { if (!allowed("get", p, uid, email)) return send(res, 403, { error: "denied" }); return send(res, 200, { exists: p in DB, data: DB[p] ?? null }); }
      const b = JSON.parse(await body(req) || "{}");
      if (b.op === "delete") { if (!allowed("delete", p, uid, email)) return send(res, 403, { error: "denied" }); delete DB[p]; LOG.push({ op: "delete", p, at: Date.now() }); return send(res, 200, { ok: true }); }
      if (b.op === "update") {
        if (!(p in DB)) return send(res, 404, { error: "not-found" });
        const d = JSON.parse(JSON.stringify(DB[p]));
        for (const [segs, v] of b.ops) { let o = d; for (let i = 0; i < segs.length - 1; i++) { if (!o[segs[i]] || typeof o[segs[i]] !== "object") o[segs[i]] = {}; o = o[segs[i]]; } const last = segs[segs.length - 1]; if (v && v.__del) delete o[last]; else o[last] = v; }
        if (!allowed("set", p, uid, email, d)) { LOG.push({ op: "denied", p, at: Date.now(), keys: Object.keys(d) }); return send(res, 403, { error: "denied" }); }
        DB[p] = resolveTs(d); LOG.push({ op: "set", kind: "update", p, at: Date.now(), n: b.ops.length });
        return send(res, 200, { ok: true });
      }
      if (!allowed("set", p, uid, email, b.data)) { LOG.push({ op: "denied", p, at: Date.now(), keys: Object.keys(b.data || {}) }); return send(res, 403, { error: "denied" }); }
      DB[p] = resolveTs(b.data); LOG.push({ op: "set", p, at: Date.now(), data: DB[p] });
      return send(res, 200, { ok: true });
    }
    if (u.pathname === "/__fake/list") {
      const c = u.searchParams.get("c");
      if (!allowed("list", c + "/x", uid, email)) return send(res, 403, { error: "denied" });
      return send(res, 200, Object.keys(DB).filter((k) => k.startsWith(c + "/")).map((k) => ({ id: k.split("/")[1], data: DB[k] })));
    }
    if (u.pathname === "/__fake/dump") return send(res, 200, { db: DB, log: LOG });
    if (u.pathname === "/__fake/reset") { DB = {}; LOG = []; return send(res, 200, { ok: true }); }
    if (u.pathname === "/__fake/put") { const b = JSON.parse(await body(req)); DB[b.p] = b.data; return send(res, 200, { ok: true }); }
    // Firestore REST, as the blog reads it
    const rest = /^\/__rest\/v1\/projects\/wandering-eric\/databases\/\(default\)\/documents\/(.+)$/.exec(decodeURIComponent(u.pathname));
    if (rest) {
      const p = rest[1];
      if (!p.includes("/")) { const rows = Object.keys(DB).filter((k) => k.startsWith(p + "/")); if (!allowed("list", p + "/x", "", "")) return send(res, 403, { error: { code: 403 } }); return send(res, 200, rows.length ? { documents: rows.map((k) => fsDocJSON(k, DB[k])) } : {}); }
      if (!(p in DB)) return send(res, 404, { error: { code: 404 } });
      if (!allowed("get", p, "", "")) return send(res, 403, { error: { code: 403 } });
      return send(res, 200, fsDocJSON(p, DB[p]));
    }
    // CDN mirrors
    if (u.pathname === "/__cdn/fonts.css") return send(res, 200, await fontCSS(), "text/css; charset=utf-8");
    let file = null;
    if (u.pathname.startsWith("/__cdn/fonts/")) file = path.join(NM, "@fontsource", u.pathname.slice("/__cdn/fonts/".length));
    else if (u.pathname.startsWith("/__cdn/katex/")) file = path.join(NM, "katex", "dist", u.pathname.slice("/__cdn/katex/".length));
    else if (u.pathname === "/__cdn/marked.umd.js") file = path.join(NM, "marked", "lib", "marked.umd.js");
    else if (u.pathname.startsWith("/__cdn/firebase/")) file = path.join(here, "fake", path.basename(u.pathname));
    else { let p = decodeURIComponent(u.pathname); if (p.endsWith("/")) p += "index.html"; file = path.join(dist, p); if (!file.startsWith(dist)) return send(res, 403, "no"); }
    const st = await stat(file).catch(() => null);
    if (!st || !st.isFile()) return send(res, 404, "not found", "text/plain");
    const buf = await readFile(file);
    res.writeHead(200, { "content-type": TYPES[path.extname(file).toLowerCase()] || "application/octet-stream", "cache-control": "no-cache", "access-control-allow-origin": "*" });
    res.end(buf);
  } catch (e) { send(res, 500, { error: String(e && e.stack || e) }); }
});
server.listen(port, () => console.log("test server on http://localhost:" + port + " serving " + dist));

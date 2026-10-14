// Fake firebase-firestore backed by the local test server (/__fake/*), shared by every browser context,
// so two contexts behave like a phone and a laptop on the same account.
// It mimics the parts of real Firestore behaviour that matter for sync bugs:
//  - setDoc fires a local snapshot at once with hasPendingWrites=true and serverTimestamp() as null,
//  - the server acks after a delay (window.__FAKE_LATENCY, default 150 ms) and resolves the timestamp,
//    which changes the data and so fires a second snapshot with hasPendingWrites=false,
//  - writes from other devices arrive through the listener (polled here every 200 ms),
//  - security rules for users/{uid} are checked by the server.
const F = (globalThis.__FFB = globalThis.__FFB || { authCbs: [], user: null, inited: false });
const SERVER = "/__fake";
const ST = { __st: 1 };
export function serverTimestamp() { return ST; }
const DEL = { __del: 1 };
export function deleteField() { return DEL; }
export class FieldPath { constructor(...segs) { if (!segs.length || segs.some((x) => typeof x !== "string" || !x)) throw new Error("Invalid FieldPath"); this.segs = segs; } }
function segsOf(f) { if (f instanceof FieldPath) return f.segs; if (typeof f === "string") return f.split("."); throw new Error("bad field"); }
function applyOps(base, ops) { const d = base ? JSON.parse(JSON.stringify(base)) : {}; for (const [segs, v] of ops) { let o = d; for (let i = 0; i < segs.length - 1; i++) { if (!o[segs[i]] || typeof o[segs[i]] !== "object") o[segs[i]] = {}; o = o[segs[i]]; } const last = segs[segs.length - 1]; if (v && v.__del) delete o[last]; else o[last] = v && v.__st ? null : JSON.parse(JSON.stringify(v)); } return d; }
export function getFirestore() { return { type: "firestore" }; }
export function doc(db, coll, id) { return { type: "doc", path: coll + "/" + id, id }; }
export function collection(db, name) { return { type: "coll", path: name }; }
function hdrs() { const u = F.user; return { "content-type": "application/json", "x-uid": u ? u.uid : "", "x-email": u ? u.email || "" : "" }; }
function lat() { return window.__FAKE_LATENCY == null ? 150 : window.__FAKE_LATENCY; }
function offline() { return !!window.__FAKE_OFFLINE; }
function denied() { if (window.__FAKE_DENY) { F.denied = (F.denied || 0) + 1; return true; } return false; }
function fsErr(code) { return Object.assign(new Error("Fake Firestore: " + code), { code }); }
function snapOf(id, data, pending) {
  return { id, exists: () => data != null, data: () => (data == null ? undefined : JSON.parse(JSON.stringify(data))), metadata: { hasPendingWrites: !!pending, fromCache: !!pending } };
}
function localEstimate(data) { // pending serverTimestamp() reads as null, like Firestore's default
  return JSON.parse(JSON.stringify(data, (k, v) => (v && v.__st ? null : v)));
}
async function serverGet(path) {
  let r;
  try { r = await fetch(SERVER + "/doc?p=" + encodeURIComponent(path), { headers: hdrs(), cache: "no-store" }); }
  catch (e) { throw fsErr("unavailable"); } // a cancelled request (WebKit closes them when a tab goes away)
  if (r.status === 403) throw fsErr("permission-denied");
  if (!r.ok) throw fsErr("unavailable");
  return r.json();
}
F.listeners = F.listeners || [];
F.writes = F.writes || [];
F.pending = F.pending || {};
function pend(path, d) { F.pending[path] = (F.pending[path] || 0) + d; }
export function getDoc(ref) {
  if (offline()) return Promise.reject(fsErr("unavailable"));
  return serverGet(ref.path).then((j) => snapOf(ref.id, j.exists ? j.data : null, false));
}
function emitLocal(path, data) {
  F.listeners.filter((l) => l.path === path).forEach((l) => { l.last = JSON.stringify(data); l.next(snapOf(l.id, data, true)); });
}
export function setDoc(ref, data) {
  const est = localEstimate(data);
  emitLocal(ref.path, est);
  F.writes.push({ path: ref.path, at: Date.now(), data: est });
  pend(ref.path, 1);
  return new Promise((res, rej) => setTimeout(async () => {
    if (offline()) { pend(ref.path, -1); return rej(fsErr("unavailable")); }
    try {
      const r = await fetch(SERVER + "/doc?p=" + encodeURIComponent(ref.path), { method: "POST", headers: hdrs(), body: JSON.stringify({ op: "set", data }) });
      pend(ref.path, -1);
      if (r.status === 403) return rej(fsErr("permission-denied"));
      if (!r.ok) return rej(fsErr("unavailable"));
      res();
    } catch (e) { pend(ref.path, -1); rej(fsErr("unavailable")); }
  }, lat()));
}
export function updateDoc(ref, ...pairs) {
  if (pairs.length % 2) throw new Error("updateDoc needs field/value pairs");
  const ops = []; for (let i = 0; i < pairs.length; i += 2) ops.push([segsOf(pairs[i]), pairs[i + 1]]);
  F.listeners.filter((l) => l.path === ref.path && l.last !== undefined).forEach((l) => { const cur = JSON.parse(l.last); if (cur) { const est = applyOps(cur, ops); l.last = JSON.stringify(est); l.next(snapOf(l.id, est, true)); } });
  F.writes.push({ path: ref.path, at: Date.now(), ops: ops.length });
  pend(ref.path, 1);
  return new Promise((res, rej) => setTimeout(async () => {
    if (offline()) { pend(ref.path, -1); return rej(fsErr("unavailable")); }
    if (denied()) { pend(ref.path, -1); F.listeners.filter((l) => l.path === ref.path).forEach((l) => { l.last = "revert"; }); return rej(fsErr("permission-denied")); }
    try {
      const r = await fetch(SERVER + "/doc?p=" + encodeURIComponent(ref.path), { method: "POST", headers: hdrs(), body: JSON.stringify({ op: "update", ops }) });
      pend(ref.path, -1);
      if (r.status === 404) return rej(fsErr("not-found"));
      if (r.status === 403) return rej(fsErr("permission-denied"));
      if (!r.ok) return rej(fsErr("unavailable"));
      res();
    } catch (e) { pend(ref.path, -1); rej(fsErr("unavailable")); }
  }, lat()));
}
export function deleteDoc(ref) {
  emitLocal(ref.path, null);
  pend(ref.path, 1);
  return new Promise((res, rej) => setTimeout(async () => {
    if (offline()) { pend(ref.path, -1); return rej(fsErr("unavailable")); }
    let r;
    try { r = await fetch(SERVER + "/doc?p=" + encodeURIComponent(ref.path), { method: "POST", headers: hdrs(), body: JSON.stringify({ op: "delete" }) }); }
    catch (e) { pend(ref.path, -1); return rej(fsErr("unavailable")); }
    pend(ref.path, -1);
    if (r.status === 403) return rej(fsErr("permission-denied"));
    res();
  }, lat()));
}
export function getDocs(coll) {
  if (offline()) return Promise.reject(fsErr("unavailable"));
  return fetch(SERVER + "/list?c=" + encodeURIComponent(coll.path), { headers: hdrs(), cache: "no-store" }).then((r) => {
    if (r.status === 403) throw fsErr("permission-denied");
    return r.json();
  }, () => { throw fsErr("unavailable"); }).then((rows) => {
    const docs = rows.map((d) => ({ id: d.id, exists: () => true, data: () => d.data }));
    return { docs, size: docs.length, empty: !docs.length, forEach: (fn) => docs.forEach(fn) };
  });
}
export function onSnapshot(ref, next, error) {
  const l = { path: ref.path, id: ref.id, next, last: undefined, on: true };
  F.listeners.push(l);
  const tick = async () => {
    if (!l.on) return;
    if (!offline() && !(F.pending[ref.path] > 0)) {
      try {
        const j = await serverGet(ref.path);
        const data = j.exists ? j.data : null;
        const s = JSON.stringify(data);
        if (l.on && !(F.pending[ref.path] > 0) && s !== l.last) { l.last = s; next(snapOf(ref.id, data, false)); }
      } catch (e) { if (e.code === "permission-denied") { l.on = false; if (error) error(e); return; } }
    }
    setTimeout(tick, 200);
  };
  tick();
  return () => { l.on = false; F.listeners = F.listeners.filter((x) => x !== l); };
}

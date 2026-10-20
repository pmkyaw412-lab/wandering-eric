// Temporary QA: run the Firestore security rules against the emulator.
// Usage (inside `firebase emulators:exec --only firestore`): node qa/rules/test.mjs <rules file> <label>
import fs from "node:fs";
import { initializeTestEnvironment, assertSucceeds, assertFails } from "@firebase/rules-unit-testing";
import { doc, setDoc, getDoc, getDocs, updateDoc, deleteDoc, collection, serverTimestamp } from "firebase/firestore";

const [rulesFile, label] = process.argv.slice(2);
const env = await initializeTestEnvironment({ projectId: "demo-wandering-eric", firestore: { rules: fs.readFileSync(rulesFile, "utf8") } });
const results = [];
async function check(name, expect, fn) {
  let ok = false, err = "";
  try { if (expect === "allow") await assertSucceeds(fn()); else await assertFails(fn()); ok = true; } catch (e) { err = String(e && e.message || e).slice(0, 200); }
  results.push({ name, expect, ok, err });
}
const G = (uid, extra = {}) => env.authenticatedContext(uid, Object.assign({ firebase: { sign_in_provider: "google.com" }, email: uid + "@example.com", email_verified: true }, extra)).firestore();
const student = G("s1"), other = G("s2");
const admin = G("admin1", { email: "pmkyaw412@gmail.com" });
const admin2 = G("admin2", { email: "pmkyawclass@gmail.com" });
const anon = env.authenticatedContext("anon1", { firebase: { sign_in_provider: "anonymous" } }).firestore();
const pwSpoof = env.authenticatedContext("pw1", { firebase: { sign_in_provider: "password" }, email: "pmkyaw412@gmail.com", email_verified: true }).firestore();
const unverified = G("admin3", { email: "pmkyaw412@gmail.com", email_verified: false });
const nobody = env.unauthenticatedContext().firestore();

// a record shaped exactly like the site's (cloudPush: every CLOUD key, plus updatedAt and v)
const record = {
  saved: { "u:東京大学": { s: 1, t: 1760000000000, c: 1 }, "o:HAL東京": { s: 0, t: 1760000000001, c: 0 } },
  sschol: { "mext-ug": { t: 1760000000000 } }, frec: { "t1-1": { k: 2, w: 1, s: 2 } }, stars: { "出願": true },
  steps: { "0": true }, docs: { "3": true }, stmt: { trigger: "I want to study civil engineering.", prep: "" },
  essay: "", target: 800, elig: { visa: "y" }, mq: { f: ["e"], r: [], k: ["u"], o: [], pre: "", en: "y", intl: "" },
  flang: "en", fess: false, fdiag: true, updatedAt: serverTimestamp(), v: 11,
};

await check("student creates own record (site shape)", "allow", () => setDoc(doc(student, "users/s1"), record));
await check("student updates one saved school (updateDoc path)", "allow", () => updateDoc(doc(student, "users/s1"), "saved.u:京都大学", { s: 0, t: 1, c: 0 }, "updatedAt", serverTimestamp(), "v", 11));
await check("student removes a saved school (field delete via whole save)", "allow", () => setDoc(doc(student, "users/s1"), Object.assign({}, record, { saved: {} })));
await check("student reads own record", "allow", () => getDoc(doc(student, "users/s1")));
await check("student cannot read another student", "deny", () => getDoc(doc(other, "users/s1")));
await check("student cannot write another student's record", "deny", () => setDoc(doc(other, "users/s1"), record));
await check("unknown field refused", "deny", () => setDoc(doc(student, "users/s1"), Object.assign({}, record, { evil: 1 })));
await check("target must be a number", "deny", () => setDoc(doc(student, "users/s1"), Object.assign({}, record, { target: "<img src=x onerror=alert(1)>" })));
await check("essay must be text", "deny", () => setDoc(doc(student, "users/s1"), Object.assign({}, record, { essay: { a: 1 } })));
await check("saved must be a map", "deny", () => setDoc(doc(student, "users/s1"), Object.assign({}, record, { saved: "x" })));
await check("anonymous account cannot create a record", "deny", () => setDoc(doc(anon, "users/anon1"), record));
await check("signed-out visitor cannot read a record", "deny", () => getDoc(doc(nobody, "users/s1")));
await check("student deletes own record", "allow", () => deleteDoc(doc(student, "users/s1")));

await check("anyone reads posts", "allow", () => getDocs(collection(nobody, "posts")));
await check("Eric (account 1) publishes a post", "allow", () => setDoc(doc(admin, "posts/hello-world"), { status: "published", title: "Hello", body: "x" }));
await check("Eric (account 2) updates a post", "allow", () => setDoc(doc(admin2, "posts/hello-world"), { status: "published", title: "Hello 2", body: "y" }));
await check("bad post address refused", "deny", () => setDoc(doc(admin, "posts/Hello World"), { status: "published" }));
await check("a student cannot write posts", "deny", () => setDoc(doc(student, "posts/hack"), { status: "published" }));
await check("email/password account with Eric's address cannot write posts", "deny", () => setDoc(doc(pwSpoof, "posts/hack"), { status: "published" }));
await check("unverified Google email cannot write posts", "deny", () => setDoc(doc(unverified, "posts/hack"), { status: "published" }));
await check("Eric writes a draft", "allow", () => setDoc(doc(admin, "drafts/k1"), { title: "Draft", body: "z", rev: "abc" }));
await check("Eric reads drafts", "allow", () => getDocs(collection(admin, "drafts")));
await check("a student cannot read drafts", "deny", () => getDocs(collection(student, "drafts")));
await check("a visitor cannot read a draft", "deny", () => getDoc(doc(nobody, "drafts/k1")));
await check("Eric uploads a photo", "allow", () => setDoc(doc(admin, "media/m1"), { data: "data:image/jpeg;base64,AAAA" }));
await check("photo data must be text", "deny", () => setDoc(doc(admin, "media/m2"), { data: 5 }));
await check("anyone opens a photo by id", "allow", () => getDoc(doc(nobody, "media/m1")));
await check("nobody else can list photos", "deny", () => getDocs(collection(nobody, "media")));
await check("Eric lists photos", "allow", () => getDocs(collection(admin, "media")));
await check("other collections closed, even to Eric", "deny", () => setDoc(doc(admin, "config/x"), { a: 1 }));

await env.cleanup();
const pass = results.filter((r) => r.ok).length;
const out = { label, rules: rulesFile, pass, total: results.length, results };
fs.mkdirSync("qa-results", { recursive: true });
fs.writeFileSync(`qa-results/rules-${label}.json`, JSON.stringify(out, null, 1));
console.log(label, pass, "of", results.length, "as expected");
for (const r of results) if (!r.ok) console.log("  UNEXPECTED:", r.name, "(expected " + r.expect + ")", r.err);
process.exit(0);

// Fake firebase-auth. The signed-in user persists in localStorage (like Firebase's IndexedDB persistence),
// so each browser context behaves like a separate device.
const F = (globalThis.__FFB = globalThis.__FFB || { authCbs: [], user: null, inited: false });
const UKEY = "__fakefb_user";
function readUser() { try { return JSON.parse(localStorage.getItem(UKEY) || "null"); } catch (e) { return null; } }
function writeUser(u) { try { u ? localStorage.setItem(UKEY, JSON.stringify(u)) : localStorage.removeItem(UKEY); } catch (e) {} }
function wrap(u) { if (!u) return null; return Object.assign({ emailVerified: true, getIdToken: () => Promise.resolve("fake") }, u); }
function emit() { F.authCbs.forEach((cb) => { try { cb(F.user); } catch (e) { console.error(e); } }); }
export function getAuth() {
  if (!F.inited) { F.inited = true; F.user = wrap(readUser()); }
  return { currentUser: F.user };
}
export function onAuthStateChanged(auth, cb) {
  F.authCbs.push(cb);
  setTimeout(() => cb(F.user), 30);
  return () => { F.authCbs = F.authCbs.filter((x) => x !== cb); };
}
export class GoogleAuthProvider { setCustomParameters(p) { this.p = p; } addScope() {} }
export function signInWithPopup(auth, provider) {
  F.popups = (F.popups || 0) + 1;
  const mode = window.__FAKE_POPUP || "ok";
  return new Promise((res, rej) => setTimeout(() => {
    if (mode === "blocked") return rej(Object.assign(new Error("Firebase: Error (auth/popup-blocked)."), { code: "auth/popup-blocked" }));
    if (mode === "closed") return rej(Object.assign(new Error("Firebase: Error (auth/popup-closed-by-user)."), { code: "auth/popup-closed-by-user" }));
    if (mode === "network") return rej(Object.assign(new Error("Firebase: Error (auth/network-request-failed)."), { code: "auth/network-request-failed" }));
    const u = window.__FAKE_SIGNIN_USER || { uid: "student-1", email: "student1@example.com", displayName: "Aung Aung", photoURL: "" };
    writeUser(u); F.user = wrap(u); emit();
    res({ user: F.user });
  }, 120));
}
export function reauthenticateWithPopup(user, provider) {
  const mode = window.__FAKE_POPUP || "ok";
  return new Promise((res, rej) => setTimeout(() => {
    if (mode === "closed") return rej(Object.assign(new Error("Firebase: Error (auth/popup-closed-by-user)."), { code: "auth/popup-closed-by-user" }));
    if (mode === "blocked") return rej(Object.assign(new Error("Firebase: Error (auth/popup-blocked)."), { code: "auth/popup-blocked" }));
    window.__FAKE_RECENT_LOGIN = false; // a fresh sign-in lets deleteUser go through
    res({ user });
  }, 60));
}
export function signOut() { return new Promise((res) => setTimeout(() => { writeUser(null); F.user = null; emit(); res(); }, 40)); }
export function deleteUser(u) {
  if (window.__FAKE_RECENT_LOGIN) return Promise.reject(Object.assign(new Error("Firebase: Error (auth/requires-recent-login)."), { code: "auth/requires-recent-login" }));
  return new Promise((res) => setTimeout(() => { writeUser(null); F.user = null; emit(); res(); }, 40));
}

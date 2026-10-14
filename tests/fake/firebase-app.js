// Fake firebase-app for local testing. Shared state lives on globalThis.__FFB.
const F = (globalThis.__FFB = globalThis.__FFB || { authCbs: [], user: null, inited: false });
export function initializeApp(cfg) { F.cfg = cfg; return { name: "[DEFAULT]", options: cfg }; }
export const SDK_VERSION = "fake";
// slow connection: window.__FAKE_SLOWLOAD (ms) holds back the module, like a slow download
if (window.__FAKE_SLOWLOAD) await new Promise((r) => setTimeout(r, window.__FAKE_SLOWLOAD));

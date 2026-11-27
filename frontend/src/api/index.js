// One API object for the whole app: the real backend (live.js) or the in-browser demo (demo.js).
// The sign-in screen picks; the choice is kept for the tab so a reload stays where you were.
import { demo } from './demo.js';
import { live, ApiError } from './live.js';

const KEY = 'wbh-mode';
let current = (() => { try { return sessionStorage.getItem(KEY) === 'demo' ? demo : live; } catch { return live; } })();

export const api = new Proxy({}, { get: (_, prop) => {
  const v = current[prop];
  return typeof v === 'function' ? v.bind(current) : v;
} });

export function setMode(mode) {
  current = mode === 'demo' ? demo : live;
  try { sessionStorage.setItem(KEY, mode); } catch { /* ignore */ }
}

export { ApiError, demo, live };

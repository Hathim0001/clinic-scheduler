// The staff token lives in sessionStorage: it survives a reload but not closing the tab, so a shared
// reception computer is signed out when the browser is. Storage can be unavailable (private windows,
// blocked site data), so every access is wrapped and the token is also kept in memory.

const KEY = "clinic.staffToken";

export interface Session {
  token: string;
  name: string;
  role?: "ADMIN" | "RECEPTIONIST"; // missing in a session saved before roles existed
}

let memory: Session | null = null;
let loaded = false;
const listeners = new Set<() => void>();

function load(): Session | null {
  if (!loaded) {
    loaded = true;
    try {
      const raw = window.sessionStorage.getItem(KEY);
      memory = raw ? (JSON.parse(raw) as Session) : null;
    } catch {
      memory = null;
    }
  }
  return memory;
}

export function getSession(): Session | null {
  return load();
}

export function setSession(session: Session | null): void {
  loaded = true;
  memory = session;
  try {
    if (session) window.sessionStorage.setItem(KEY, JSON.stringify(session));
    else window.sessionStorage.removeItem(KEY);
  } catch {
    // keep working from memory
  }
  listeners.forEach((notify) => notify());
}

export function subscribeSession(notify: () => void): () => void {
  listeners.add(notify);
  return () => listeners.delete(notify);
}

/** Test helper: forget what was loaded so the next read goes back to storage. */
export function resetSessionCache(): void {
  loaded = false;
  memory = null;
}

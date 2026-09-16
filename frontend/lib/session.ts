// The frontend generates its own session_id and sends it with every chat request (per the
// migration brief -- the FastAPI backend keeps an in-memory dict keyed by whatever it receives,
// it never generates IDs itself). Persisted to localStorage so a page refresh keeps the same
// conversation instead of silently starting a new one.

const STORAGE_KEY = "schemelogic_session_id";

function randomId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  // Fallback for any environment without crypto.randomUUID -- good enough for a session key,
  // not used for anything security-sensitive.
  return `sess-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function getOrCreateSessionId(): string {
  if (typeof window === "undefined") return randomId(); // SSR guard -- never actually used server-side
  const existing = window.localStorage.getItem(STORAGE_KEY);
  if (existing) return existing;
  const fresh = randomId();
  window.localStorage.setItem(STORAGE_KEY, fresh);
  return fresh;
}

export function resetSessionId(): string {
  const fresh = randomId();
  if (typeof window !== "undefined") {
    window.localStorage.setItem(STORAGE_KEY, fresh);
  }
  return fresh;
}

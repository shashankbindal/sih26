// JWT held in memory, mirrored to sessionStorage so a refresh keeps the session.
// sessionStorage access is wrapped: it can throw in private/blocked contexts.
const KEY = 'loksutra.token';
let memory: string | null = null;

export function getToken(): string | null {
  if (memory) return memory;
  try {
    memory = window.sessionStorage.getItem(KEY);
  } catch {
    memory = null;
  }
  return memory;
}

export function setToken(token: string | null): void {
  memory = token;
  try {
    if (token) window.sessionStorage.setItem(KEY, token);
    else window.sessionStorage.removeItem(KEY);
  } catch {
    /* in-memory only */
  }
}

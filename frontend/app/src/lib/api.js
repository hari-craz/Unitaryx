let csrfTokenPromise = null;

async function getCsrfToken() {
  if (!csrfTokenPromise) {
    csrfTokenPromise = fetch('/api/csrf-token', { credentials: 'same-origin' })
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error('no csrf token'))))
      .then((data) => data.token)
      .catch(() => {
        csrfTokenPromise = null;
        return null;
      });
  }
  return csrfTokenPromise;
}

const WRITE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

export async function apiFetch(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const headers = { ...(options.headers || {}) };

  if (WRITE_METHODS.has(method)) {
    const token = await getCsrfToken();
    if (token) headers['X-CSRFToken'] = token;
    if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }
  }

  let response = await fetch(path, {
    ...options,
    method,
    headers,
    credentials: 'same-origin',
  });

  // Stale CSRF token (new session, rotated cookie): fetch a fresh one and retry once.
  if (response.status === 403 && WRITE_METHODS.has(method) && !options._retried) {
    csrfTokenPromise = null;
    const fresh = await getCsrfToken();
    if (fresh) {
      return apiFetch(path, { ...options, headers: { ...headers, 'X-CSRFToken': fresh }, _retried: true });
    }
  }

  // An ended session makes the server redirect to the HTML login page.
  const sessionEnded =
    response.status === 401 || (response.redirected && new URL(response.url).pathname.startsWith('/login'));
  if (sessionEnded) {
    csrfTokenPromise = null;
    const error = new Error('Your session has ended. Please sign in again.');
    error.status = 401;
    error.errors = {};
    throw error;
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const error = new Error(body.message || `Request failed (${response.status})`);
    error.status = response.status;
    error.errors = body.errors || {};
    throw error;
  }

  if (response.status === 204) return null;
  return response.json();
}

export const getJSON = (path) => apiFetch(path);
export const postJSON = (path, data) => apiFetch(path, { method: 'POST', body: JSON.stringify(data) });
export const putJSON = (path, data) => apiFetch(path, { method: 'PUT', body: JSON.stringify(data) });
export const deleteReq = (path) => apiFetch(path, { method: 'DELETE' });

// Multipart image upload. `kind` is 'founders' or 'projects'. Returns { url }.
export async function uploadImage(file, kind) {
  const form = new FormData();
  form.append('kind', kind);
  form.append('file', file);
  return apiFetch('/api/admin/upload', { method: 'POST', body: form });
}

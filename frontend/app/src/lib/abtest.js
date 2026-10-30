import { apiFetch, getJSON } from './api';

// One shared request per page load; the server also sets the ux_vid cookie
// here, which later event calls use to identify the visitor.
let assignmentsPromise = null;

export function loadAssignments() {
  if (!assignmentsPromise) {
    assignmentsPromise = getJSON('/api/ab-tests/resolve')
      .then((data) => data.assignments || {})
      .catch(() => ({}));
  }
  return assignmentsPromise;
}

const sent = new Set();

// Fire-and-forget. The server de-duplicates per visitor, so this only avoids
// repeat requests within one page view. Failures never affect the page.
export function trackAbEvent(testKey, event) {
  const id = `${testKey}:${event}`;
  if (sent.has(id)) return;
  sent.add(id);
  apiFetch('/api/ab-tests/event', {
    method: 'POST',
    body: JSON.stringify({ test_key: testKey, event }),
    keepalive: true,
  }).catch(() => {});
}

import { useCallback, useEffect, useState } from 'react';
import { getJSON, postJSON } from '../lib/api';

export function useDashboard() {
  const [data, setData] = useState({ user: null, requests: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getJSON('/api/dashboard/requests')
      .then((res) => {
        if (!cancelled) setData({ user: res.user, requests: res.requests });
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Opening a request is what clears its "updated" flag, so a refresh never
  // hides an update the customer has not looked at yet.
  const markSeen = useCallback((id) => {
    setData((d) => ({
      ...d,
      requests: d.requests.map((r) => (r.id === id ? { ...r, is_updated: false } : r)),
    }));
    postJSON(`/api/dashboard/requests/${id}/seen`, {}).catch(() => {});
  }, []);

  return { ...data, loading, error, markSeen };
}

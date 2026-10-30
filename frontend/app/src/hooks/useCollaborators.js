import { useEffect, useState } from 'react';
import { getJSON } from '../lib/api';

export function useCollaborators() {
  const [collaborators, setCollaborators] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getJSON('/api/collaborators')
      .then((data) => {
        if (!cancelled) setCollaborators(data);
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

  return { collaborators, loading, error };
}

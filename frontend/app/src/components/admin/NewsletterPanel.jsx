import { useEffect, useState } from 'react';
import { getJSON } from '../../lib/api';

export default function NewsletterPanel() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    getJSON('/api/admin/newsletter/summary')
      .then(setData)
      .catch((err) => setError(err.message || 'Could not load subscribers'));
  }, []);

  if (error) return <p className="admin-error">{error}</p>;
  if (!data) return <p className="admin-muted">Loading subscribers…</p>;

  return (
    <section className="admin-card glass">
      <h2>Newsletter</h2>
      <p>
        <strong>{data.confirmed}</strong> confirmed subscriber{data.confirmed === 1 ? '' : 's'}
        {' · '}
        <strong>{data.pending}</strong> awaiting confirmation
      </p>
      <p className="admin-muted">
        Only confirmed addresses are exported. Subscribers who unsubscribe are removed immediately.
      </p>
      <a className="studio-btn studio-btn--primary" href="/api/admin/newsletter/export.csv" download>
        Download confirmed subscribers (CSV)
      </a>
    </section>
  );
}

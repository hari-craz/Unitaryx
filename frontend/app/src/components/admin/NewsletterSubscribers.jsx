import { useEffect, useState } from 'react';
import { getJSON, postJSON, deleteReq } from '../../lib/api';

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'confirmed', label: 'Confirmed' },
  { key: 'pending', label: 'Awaiting confirmation' },
];

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

export default function NewsletterSubscribers() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('all');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [email, setEmail] = useState('');
  const [notice, setNotice] = useState({ tone: '', text: '' });
  const [busy, setBusy] = useState(false);

  // Wait for a pause in typing before searching.
  useEffect(() => {
    const t = setTimeout(() => {
      setQuery(search.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const load = () => {
    const params = new URLSearchParams({ status, page: String(page) });
    if (query) params.set('q', query);
    return getJSON(`/api/admin/newsletter/subscribers?${params}`)
      .then((d) => {
        setData(d);
        setError('');
      })
      .catch((err) => setError(err.message || 'Could not load subscribers'));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, query, page]);

  const add = async (e) => {
    e.preventDefault();
    if (!email.trim()) return;
    setBusy(true);
    setNotice({ tone: '', text: '' });
    try {
      const res = await postJSON('/api/admin/newsletter/subscribers', { email });
      setEmail('');
      setNotice(
        res.email_sent
          ? { tone: 'ok', text: `Confirmation email sent to ${res.subscriber.email}. They join the list once they confirm.` }
          : { tone: 'warn', text: 'Added, but the confirmation email could not be sent. Use Resend to try again.' }
      );
      await load();
    } catch (err) {
      setNotice({ tone: 'error', text: err.message || 'Could not add this address.' });
    } finally {
      setBusy(false);
    }
  };

  const resend = async (sub) => {
    setNotice({ tone: '', text: '' });
    try {
      await postJSON(`/api/admin/newsletter/subscribers/${sub.id}/resend`, {});
      setNotice({ tone: 'ok', text: `Confirmation email sent again to ${sub.email}.` });
    } catch (err) {
      setNotice({ tone: 'error', text: err.message || 'Could not resend.' });
    }
  };

  const remove = async (sub) => {
    if (!window.confirm(`Remove ${sub.email} from the newsletter list?`)) return;
    try {
      await deleteReq(`/api/admin/newsletter/subscribers/${sub.id}`);
      await load();
    } catch (err) {
      setNotice({ tone: 'error', text: err.message || 'Could not remove this subscriber.' });
    }
  };

  if (error && !data) return <p className="admin-error">{error}</p>;
  if (!data) return <p className="admin-muted">Loading subscribers…</p>;

  const pages = Math.max(1, Math.ceil(data.total / data.per_page));

  return (
    <div className="nl-stack">
      <div className="admin-card glass nl-summary">
        <p>
          <strong>{data.confirmed}</strong> confirmed subscriber{data.confirmed === 1 ? '' : 's'}
          {' · '}
          <strong>{data.pending}</strong> awaiting confirmation
        </p>
        <a className="studio-btn" href="/api/admin/newsletter/export.csv" download>
          Download confirmed (CSV)
        </a>
      </div>

      <form className="admin-card glass nl-add" onSubmit={add}>
        <label className="studio-field">
          Invite an address
          <input
            type="email"
            value={email}
            maxLength={150}
            placeholder="name@example.com"
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <button type="submit" className="studio-btn studio-btn--primary" disabled={busy || !email.trim()}>
          Send confirmation
        </button>
        <p className="admin-muted nl-add-note">
          The address is only added to the list after its owner clicks the link in the confirmation email.
        </p>
      </form>

      {notice.text && <p className={`nl-notice nl-notice--${notice.tone}`}>{notice.text}</p>}

      <div className="nl-toolbar">
        <div className="studio-tabs" role="group" aria-label="Filter subscribers">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              aria-pressed={status === f.key}
              className={`studio-tab ${status === f.key ? 'active' : ''}`}
              onClick={() => {
                setStatus(f.key);
                setPage(1);
              }}
            >
              {f.label}
            </button>
          ))}
        </div>
        <input
          className="nl-search"
          type="search"
          value={search}
          placeholder="Search by email"
          aria-label="Search subscribers by email"
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {data.subscribers.length === 0 ? (
        <div className="admin-empty glass">
          <p className="admin-empty-title">{query || status !== 'all' ? 'No matching subscribers' : 'No subscribers yet'}</p>
          <p className="admin-muted">
            {query || status !== 'all'
              ? 'Try a different filter or search.'
              : 'People who sign up on the site, or that you invite above, appear here.'}
          </p>
        </div>
      ) : (
        <div className="admin-card glass">
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Status</th>
                  <th>Joined</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.subscribers.map((s) => (
                  <tr key={s.id}>
                    <td className="admin-mono">{s.email}</td>
                    <td>
                      <span className={`admin-badge admin-badge--${s.confirmed ? 'ok' : 'muted'}`}>
                        {s.confirmed ? 'confirmed' : 'awaiting'}
                      </span>
                    </td>
                    <td>{formatDate(s.confirmed_at || s.created_at)}</td>
                    <td>
                      <div className="admin-row-actions">
                        {!s.confirmed && (
                          <button type="button" className="studio-btn studio-btn--ghost" onClick={() => resend(s)}>
                            Resend
                          </button>
                        )}
                        <button type="button" className="studio-btn studio-btn--danger" onClick={() => remove(s)}>
                          Remove
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {pages > 1 && (
            <div className="nl-pager">
              <button
                type="button"
                className="studio-btn studio-btn--ghost"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                Previous
              </button>
              <span className="admin-muted">
                Page {page} of {pages}
              </span>
              <button
                type="button"
                className="studio-btn studio-btn--ghost"
                disabled={page >= pages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

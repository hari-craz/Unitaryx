import { useCallback, useEffect, useState } from 'react';
import { getJSON, postJSON, deleteReq } from '../../lib/api';
import NewsletterEditor from './NewsletterEditor';

const STATUS_TONE = { draft: 'muted', sending: 'progress', sent: 'ok' };
const STATUS_LABEL = { draft: 'Draft', sending: 'Sending', sent: 'Sent' };

function formatWhen(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

function Progress({ nl }) {
  const done = nl.sent_count + nl.failed_count + nl.skipped_count;
  const pct = nl.recipients_total ? Math.round((done / nl.recipients_total) * 100) : 0;
  return (
    <div className="nl-progress" aria-label={`${pct}% processed`}>
      <div className="nl-progress-bar">
        <span style={{ width: `${pct}%` }} />
      </div>
      <span className="admin-muted">
        {nl.sent_count} of {nl.recipients_total} sent
        {nl.failed_count > 0 && ` · ${nl.failed_count} failed`}
        {nl.skipped_count > 0 && ` · ${nl.skipped_count} skipped`}
      </span>
    </div>
  );
}

export default function NewsletterCampaigns() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(null); // 'new', a campaign id, or null
  const [notice, setNotice] = useState('');

  const load = useCallback(
    () =>
      getJSON('/api/admin/newsletter/campaigns')
        .then((d) => {
          setData(d);
          setError('');
        })
        .catch((err) => setError(err.message || 'Could not load newsletters')),
    []
  );

  useEffect(() => {
    load();
  }, [load]);

  // Follow a send in progress.
  const sending = data?.campaigns.some((c) => c.status === 'sending' && !c.stalled);
  useEffect(() => {
    if (!sending) return undefined;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [sending, load]);

  const remove = async (nl) => {
    if (!window.confirm(`Delete "${nl.subject}"? This cannot be undone.`)) return;
    try {
      await deleteReq(`/api/admin/newsletter/campaigns/${nl.id}`);
      await load();
    } catch (err) {
      window.alert(err.message || 'Could not delete this newsletter.');
    }
  };

  const resume = async (nl) => {
    try {
      await postJSON(`/api/admin/newsletter/campaigns/${nl.id}/resume`, {});
      await load();
    } catch (err) {
      window.alert(err.message || 'Could not resume this send.');
    }
  };

  if (error && !data) return <p className="admin-error">{error}</p>;
  if (!data) return <p className="admin-muted">Loading newsletters…</p>;

  if (editing) {
    return (
      <NewsletterEditor
        campaignId={editing === 'new' ? null : editing}
        confirmed={data.confirmed}
        recipientLimit={data.recipient_limit}
        emailConfigured={data.email_configured}
        onClose={() => {
          setEditing(null);
          load();
        }}
        onSent={() => {
          setEditing(null);
          setNotice('Sending started. You can leave this page; progress updates here.');
          load();
        }}
      />
    );
  }

  return (
    <div className="nl-stack">
      {!data.email_configured && (
        <p className="nl-notice nl-notice--warn">
          Email is not configured on the server (SMTP settings), so newsletters cannot be sent yet.
        </p>
      )}
      {notice && <p className="nl-notice nl-notice--ok">{notice}</p>}

      <div className="admin-card glass nl-summary">
        <p>
          A newsletter goes to the <strong>{data.confirmed}</strong> confirmed subscriber
          {data.confirmed === 1 ? '' : 's'}. Each send is limited to {data.recipient_limit} recipients to protect the
          mail account.
        </p>
        <button type="button" className="studio-btn studio-btn--primary" onClick={() => setEditing('new')}>
          New newsletter
        </button>
      </div>

      {data.campaigns.length === 0 ? (
        <div className="admin-empty glass">
          <p className="admin-empty-title">No newsletters yet</p>
          <p className="admin-muted">Write your first update, preview it, send yourself a test, then send it.</p>
          <button type="button" className="studio-btn studio-btn--primary" onClick={() => setEditing('new')}>
            Write your first newsletter
          </button>
        </div>
      ) : (
        <div className="admin-card glass">
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Newsletter</th>
                  <th>Status</th>
                  <th>Delivery</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.campaigns.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <span className="admin-row-title">{c.subject}</span>
                      <span className="admin-muted-inline">
                        {c.status === 'sent' ? `Sent ${formatWhen(c.sent_at)}` : `Edited ${formatWhen(c.updated_at)}`}
                      </span>
                    </td>
                    <td>
                      <span className={`admin-badge admin-badge--${STATUS_TONE[c.status] || 'muted'}`}>
                        {c.stalled ? 'Interrupted' : STATUS_LABEL[c.status] || c.status}
                      </span>
                    </td>
                    <td>{c.status === 'draft' ? <span className="admin-muted">Not sent</span> : <Progress nl={c} />}</td>
                    <td>
                      <div className="admin-row-actions">
                        {c.stalled && (
                          <button type="button" className="studio-btn studio-btn--primary" onClick={() => resume(c)}>
                            Resume
                          </button>
                        )}
                        {c.status !== 'sending' || c.stalled ? (
                          <button type="button" className="studio-btn studio-btn--ghost" onClick={() => setEditing(c.id)}>
                            {c.status === 'draft' ? 'Edit' : 'View'}
                          </button>
                        ) : null}
                        {(c.status !== 'sending' || c.stalled) && (
                          <button type="button" className="studio-btn studio-btn--danger" onClick={() => remove(c)}>
                            Delete
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

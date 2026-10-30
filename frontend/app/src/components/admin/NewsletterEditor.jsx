import { useEffect, useState } from 'react';
import { getJSON, postJSON, putJSON } from '../../lib/api';

const EMPTY = { subject: '', body: '', cta_label: '', cta_url: '' };

export default function NewsletterEditor({
  campaignId,
  confirmed,
  recipientLimit,
  emailConfigured,
  onClose,
  onSent,
}) {
  const [id, setId] = useState(campaignId);
  const [form, setForm] = useState(EMPTY);
  const [status, setStatus] = useState('draft');
  const [loading, setLoading] = useState(Boolean(campaignId));
  const [dirty, setDirty] = useState(false);
  const [message, setMessage] = useState({ tone: '', text: '' });
  const [busy, setBusy] = useState('');
  const [previewHtml, setPreviewHtml] = useState('');
  const [previewError, setPreviewError] = useState('');

  const readOnly = status !== 'draft';

  useEffect(() => {
    if (!campaignId) return;
    getJSON(`/api/admin/newsletter/campaigns/${campaignId}`)
      .then((res) => {
        const c = res.campaign;
        setForm({ subject: c.subject, body: c.body, cta_label: c.cta_label, cta_url: c.cta_url });
        setStatus(c.status);
      })
      .catch((err) => setMessage({ tone: 'error', text: err.message || 'Could not load this newsletter.' }))
      .finally(() => setLoading(false));
  }, [campaignId]);

  // Refresh the preview shortly after the author stops typing.
  useEffect(() => {
    if (loading) return undefined;
    const t = setTimeout(() => {
      if (form.subject.trim().length < 3 || form.body.trim().length < 20) {
        setPreviewHtml('');
        setPreviewError('The preview appears once there is a subject and a message of at least 20 characters.');
        return;
      }
      postJSON('/api/admin/newsletter/campaigns/preview', form)
        .then((res) => {
          setPreviewHtml(res.html);
          setPreviewError('');
        })
        .catch((err) => {
          setPreviewHtml('');
          setPreviewError(err.message || 'Could not build the preview.');
        });
    }, 500);
    return () => clearTimeout(t);
  }, [form, loading]);

  const set = (patch) => {
    setForm((f) => ({ ...f, ...patch }));
    setDirty(true);
    setMessage({ tone: '', text: '' });
  };

  const save = async () => {
    const res = id
      ? await putJSON(`/api/admin/newsletter/campaigns/${id}`, form)
      : await postJSON('/api/admin/newsletter/campaigns', form);
    setId(res.campaign.id);
    setDirty(false);
    return res.campaign.id;
  };

  const run = async (name, fn) => {
    setBusy(name);
    setMessage({ tone: '', text: '' });
    try {
      await fn();
    } catch (err) {
      setMessage({ tone: 'error', text: err.message || 'Something went wrong.' });
    } finally {
      setBusy('');
    }
  };

  const saveDraft = () =>
    run('save', async () => {
      await save();
      setMessage({ tone: 'ok', text: 'Draft saved.' });
    });

  const sendTest = () =>
    run('test', async () => {
      const savedId = dirty || !id ? await save() : id;
      const res = await postJSON(`/api/admin/newsletter/campaigns/${savedId}/test`, {});
      setMessage({ tone: 'ok', text: `Test email sent to ${res.sent_to}. Check your inbox.` });
    });

  const sendToAll = () => {
    const ok = window.confirm(
      `Send "${form.subject}" to ${confirmed} confirmed subscriber${confirmed === 1 ? '' : 's'}?\n\nThis cannot be undone.`
    );
    if (!ok) return;
    run('send', async () => {
      const savedId = dirty || !id ? await save() : id;
      await postJSON(`/api/admin/newsletter/campaigns/${savedId}/send`, { confirm: true });
      onSent();
    });
  };

  if (loading) return <p className="admin-muted">Loading…</p>;

  const tooMany = confirmed > recipientLimit;
  const canSend = emailConfigured && confirmed > 0 && !tooMany && !readOnly;

  return (
    <div className="nl-editor">
      <div className="admin-section-head">
        <div>
          <h3 className="dash-card-title">{readOnly ? 'Newsletter' : id ? 'Edit newsletter' : 'New newsletter'}</h3>
          <p className="admin-section-note">
            {readOnly
              ? 'This newsletter has been sent and can no longer be changed.'
              : 'Plain text. Leave a blank line between paragraphs; web addresses become links.'}
          </p>
        </div>
        <button type="button" className="studio-btn studio-btn--ghost" onClick={onClose}>
          Back to newsletters
        </button>
      </div>

      <div className="nl-editor-grid">
        <div className="admin-card glass nl-editor-form">
          <label className="studio-field">
            Subject
            <input
              value={form.subject}
              maxLength={150}
              disabled={readOnly}
              onChange={(e) => set({ subject: e.target.value })}
            />
          </label>
          <label className="studio-field">
            Message
            <textarea
              rows={12}
              value={form.body}
              maxLength={20000}
              disabled={readOnly}
              onChange={(e) => set({ body: e.target.value })}
            />
            <span className="admin-muted">{form.body.length} / 20000</span>
          </label>
          <div className="studio-field-row">
            <label className="studio-field">
              Button label (optional)
              <input
                value={form.cta_label}
                maxLength={40}
                disabled={readOnly}
                onChange={(e) => set({ cta_label: e.target.value })}
                placeholder="Read the full post"
              />
            </label>
            <label className="studio-field">
              Button link
              <input
                value={form.cta_url}
                maxLength={300}
                disabled={readOnly}
                onChange={(e) => set({ cta_url: e.target.value })}
                placeholder="https://…"
              />
            </label>
          </div>

          {message.text && <p className={`nl-notice nl-notice--${message.tone}`}>{message.text}</p>}

          {!readOnly && (
            <>
              {!emailConfigured && (
                <p className="nl-notice nl-notice--warn">Email is not configured on the server, so sending is disabled.</p>
              )}
              {tooMany && (
                <p className="nl-notice nl-notice--warn">
                  {confirmed} confirmed subscribers is above the per-send limit of {recipientLimit}.
                </p>
              )}
              <div className="nl-editor-actions">
                <button type="button" className="studio-btn" onClick={saveDraft} disabled={Boolean(busy)}>
                  {busy === 'save' ? 'Saving…' : 'Save draft'}
                </button>
                <button
                  type="button"
                  className="studio-btn"
                  onClick={sendTest}
                  disabled={Boolean(busy) || !emailConfigured}
                >
                  {busy === 'test' ? 'Sending…' : 'Send test to me'}
                </button>
                <button
                  type="button"
                  className="studio-btn studio-btn--primary"
                  onClick={sendToAll}
                  disabled={Boolean(busy) || !canSend}
                >
                  {busy === 'send' ? 'Starting…' : `Send to ${confirmed} subscriber${confirmed === 1 ? '' : 's'}`}
                </button>
              </div>
            </>
          )}
        </div>

        <div className="admin-card glass nl-preview">
          <h4 className="dash-card-title">Preview</h4>
          {previewHtml ? (
            <iframe title="Newsletter preview" className="nl-preview-frame" sandbox="" srcDoc={previewHtml} />
          ) : (
            <p className="admin-muted">{previewError}</p>
          )}
        </div>
      </div>
    </div>
  );
}

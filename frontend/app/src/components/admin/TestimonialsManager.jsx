import { useEffect, useState } from 'react';
import { getJSON, postJSON, putJSON, deleteReq } from '../../lib/api';
import { useSaveStatus } from './useSaveStatus';
import SaveBadge from './SaveBadge';

const EMPTY = { name: '', role: '', review: '', rating: 5, active: true };

function TestimonialForm({ item, onSave, onClose }) {
  const [form, setForm] = useState(
    item
      ? { name: item.name, role: item.role || '', review: item.review, rating: item.rating, active: item.active }
      : EMPTY
  );
  const [fieldErrors, setFieldErrors] = useState({});
  const { status, error, run } = useSaveStatus();

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const set = (patch) => setForm((f) => ({ ...f, ...patch }));

  const submit = async (e) => {
    e.preventDefault();
    const errs = {};
    if (!form.name.trim()) errs.name = 'Name is required';
    if (form.review.trim().length < 10) errs.review = 'Write at least 10 characters';
    setFieldErrors(errs);
    if (Object.keys(errs).length) return;
    try {
      await run(() => onSave({ ...form, rating: Number(form.rating) }, item?.id));
    } catch {
      /* SaveBadge shows the error */
    }
  };

  return (
    <div className="studio-overlay" onClick={onClose} role="presentation">
      <form className="studio-modal glass-strong" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <div className="studio-modal-head">
          <h3>{item ? 'Edit testimonial' : 'Add testimonial'}</h3>
          <button type="button" className="studio-modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className="studio-field-row">
          <label className="studio-field">
            Name
            <input value={form.name} maxLength={100} onChange={(e) => set({ name: e.target.value })} />
            {fieldErrors.name && <span className="studio-field-error">{fieldErrors.name}</span>}
          </label>
          <label className="studio-field">
            Role or institution
            <input
              value={form.role}
              maxLength={150}
              onChange={(e) => set({ role: e.target.value })}
              placeholder="e.g. B.Tech CSE, Anna University"
            />
          </label>
        </div>
        <label className="studio-field">
          Review
          <textarea rows={4} value={form.review} maxLength={800} onChange={(e) => set({ review: e.target.value })} />
          {fieldErrors.review && <span className="studio-field-error">{fieldErrors.review}</span>}
        </label>
        <div className="studio-field-row">
          <label className="studio-field">
            Rating
            <select value={form.rating} onChange={(e) => set({ rating: e.target.value })}>
              {[5, 4, 3, 2, 1].map((n) => (
                <option key={n} value={n}>
                  {n} out of 5
                </option>
              ))}
            </select>
          </label>
          <label className="studio-toggle">
            <input type="checkbox" checked={form.active} onChange={(e) => set({ active: e.target.checked })} />
            Visible on site
          </label>
        </div>
        <div className="studio-modal-foot">
          <SaveBadge status={status} error={error} />
          <div className="studio-modal-foot-actions">
            <button type="button" className="studio-btn studio-btn--ghost" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="studio-btn studio-btn--primary" disabled={status === 'saving'}>
              {item ? 'Save changes' : 'Add testimonial'}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}

export default function TestimonialsManager() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const [editing, setEditing] = useState(null); // item, 'new' or null

  useEffect(() => {
    getJSON('/api/admin/testimonials')
      .then(setItems)
      .catch((err) => {
        if (err.status === 403) setDenied(true);
      })
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async (data, id) => {
    if (id) {
      const res = await putJSON(`/api/admin/testimonials/${id}`, data);
      setItems((list) => list.map((t) => (t.id === id ? res.testimonial : t)));
    } else {
      const res = await postJSON('/api/admin/testimonials', data);
      setItems((list) => [...list, res.testimonial]);
    }
    setEditing(null);
  };

  const handleDelete = async (item) => {
    if (!window.confirm(`Delete the testimonial from ${item.name}? This cannot be undone.`)) return;
    try {
      await deleteReq(`/api/admin/testimonials/${item.id}`);
      setItems((list) => list.filter((t) => t.id !== item.id));
    } catch (err) {
      window.alert(err.message || 'Could not delete testimonial.');
    }
  };

  if (!loading && denied) {
    return (
      <section className="admin-section">
        <div className="admin-empty glass">
          <p className="admin-empty-title">Superadmin only</p>
          <p className="admin-muted">Managing testimonials is restricted to the superadmin account.</p>
        </div>
      </section>
    );
  }

  const visible = items.filter((t) => t.active).length;

  return (
    <section className="admin-section">
      <div className="admin-section-head">
        <div>
          <h2>Testimonials</h2>
          <p className="admin-section-note">
            {items.length} total · {visible} visible on the site. Only publish reviews from real clients.
          </p>
        </div>
        <button type="button" className="studio-btn studio-btn--primary" onClick={() => setEditing('new')}>
          Add testimonial
        </button>
      </div>

      {loading ? (
        <p className="admin-muted">Loading…</p>
      ) : items.length === 0 ? (
        <div className="admin-empty glass">
          <p className="admin-empty-title">No testimonials yet</p>
          <p className="admin-muted">The section stays hidden on the site until you add one.</p>
          <button type="button" className="studio-btn studio-btn--primary" onClick={() => setEditing('new')}>
            Add your first testimonial
          </button>
        </div>
      ) : (
        <div className="admin-list">
          {items.map((t) => (
            <div key={t.id} className="admin-row glass">
              <div className="admin-row-main">
                <p className="admin-row-title">
                  {t.name} <span className="admin-muted-inline">{'★'.repeat(t.rating)}</span>
                </p>
                <p className="admin-row-sub">{t.role ? `${t.role} · ` : ''}{t.review}</p>
              </div>
              {!t.active && <span className="admin-badge admin-badge--muted">Hidden</span>}
              <div className="admin-row-actions">
                <button type="button" className="studio-btn studio-btn--ghost" onClick={() => setEditing(t)}>
                  Edit
                </button>
                <button type="button" className="studio-btn studio-btn--danger" onClick={() => handleDelete(t)}>
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {editing && (
        <TestimonialForm
          item={editing === 'new' ? null : editing}
          onSave={handleSave}
          onClose={() => setEditing(null)}
        />
      )}
    </section>
  );
}

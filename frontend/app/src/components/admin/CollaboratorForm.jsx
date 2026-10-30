import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import ImageUpload from './ImageUpload';
import SaveBadge from './SaveBadge';
import { useSaveStatus } from './useSaveStatus';

const GOALS_MAX = 300;

function emptyForm() {
  return { name: '', kind: 'startup', founder_name: '', goals: '', logo_url: '', website_url: '', active: true };
}

export default function CollaboratorForm({ collaborator, onSave, onClose }) {
  const [form, setForm] = useState(emptyForm());
  const [fieldErrors, setFieldErrors] = useState({});
  const { status, error, run } = useSaveStatus();

  useEffect(() => {
    if (collaborator) {
      setForm({
        name: collaborator.name || '',
        kind: collaborator.kind || 'startup',
        founder_name: collaborator.founder_name || '',
        goals: collaborator.goals || '',
        logo_url: collaborator.logo_url || '',
        website_url: collaborator.website_url || '',
        active: collaborator.active !== false,
      });
    } else {
      setForm(emptyForm());
    }
  }, [collaborator]);

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
    if (!/^https?:\/\/\S+$/i.test(form.website_url.trim())) {
      errs.website_url = 'Enter a full link starting with https://';
    }
    setFieldErrors(errs);
    if (Object.keys(errs).length) return;
    try {
      await run(() => onSave({ ...form, website_url: form.website_url.trim() }, collaborator?.id));
    } catch {
      /* SaveBadge shows the error */
    }
  };

  const noun = form.kind === 'freelancer' ? 'Freelancer' : 'Founder';

  return (
    <div className="studio-overlay" onClick={onClose} role="presentation">
      <motion.form
        className="studio-modal glass-strong"
        initial={{ opacity: 0, scale: 0.96, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ type: 'spring', stiffness: 300, damping: 26 }}
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <div className="studio-modal-head">
          <h3>{collaborator ? 'Edit collaborator' : 'Add collaborator'}</h3>
          <button type="button" className="studio-modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <div className="studio-form-grid">
          <div className="studio-form-col">
            <label className="studio-field">
              Name
              <input value={form.name} maxLength={120} onChange={(e) => set({ name: e.target.value })} />
              {fieldErrors.name && <span className="studio-field-error">{fieldErrors.name}</span>}
            </label>
            <label className="studio-field">
              Type
              <select value={form.kind} onChange={(e) => set({ kind: e.target.value })}>
                <option value="startup">Startup</option>
                <option value="freelancer">Freelancer</option>
              </select>
            </label>
            <label className="studio-field">
              {noun} name
              <input
                value={form.founder_name}
                maxLength={120}
                onChange={(e) => set({ founder_name: e.target.value })}
              />
            </label>
            <label className="studio-field">
              Website (where the card links to)
              <input
                value={form.website_url}
                maxLength={300}
                onChange={(e) => set({ website_url: e.target.value })}
                placeholder="https://…"
              />
              {fieldErrors.website_url && <span className="studio-field-error">{fieldErrors.website_url}</span>}
            </label>
            <label className="studio-field">
              Goals
              <textarea
                rows={3}
                value={form.goals}
                maxLength={GOALS_MAX}
                onChange={(e) => set({ goals: e.target.value })}
                placeholder="One or two sentences about what they are building."
              />
              <span className="admin-muted">
                {form.goals.length}/{GOALS_MAX}
              </span>
            </label>
            <label className="studio-toggle">
              <input type="checkbox" checked={form.active} onChange={(e) => set({ active: e.target.checked })} />
              Visible on site
            </label>
          </div>

          <div className="studio-form-col">
            <span className="studio-field-label">Logo</span>
            <ImageUpload
              value={form.logo_url}
              kind="collaborators"
              shape="square"
              onChange={(url) => set({ logo_url: url })}
            />
            <p className="admin-muted">A square logo works best. A transparent background is shown on white.</p>
          </div>
        </div>

        <div className="studio-modal-foot">
          <SaveBadge status={status} error={error} savedLabel="Saved" />
          <div className="studio-modal-foot-actions">
            <button type="button" className="studio-btn studio-btn--ghost" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="studio-btn studio-btn--primary" disabled={status === 'saving'}>
              {collaborator ? 'Save changes' : 'Add collaborator'}
            </button>
          </div>
        </div>
      </motion.form>
    </div>
  );
}

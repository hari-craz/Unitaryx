import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import ImageUpload from './ImageUpload';
import SaveBadge from './SaveBadge';
import { useSaveStatus } from './useSaveStatus';

const CATEGORIES = ['web', 'software', 'hardware', 'ai'];

function emptyForm() {
  return {
    title: '',
    description: '',
    category: 'web',
    tags: '',
    price: '',
    duration: '',
    featured: false,
    photo_url: '',
    problem: '',
    approach: '',
    outcome: '',
    stack: '',
  };
}

export default function ProjectForm({ project, onSave, onClose }) {
  const [form, setForm] = useState(emptyForm());
  const [fieldErrors, setFieldErrors] = useState({});
  const { status, error, run } = useSaveStatus();

  useEffect(() => {
    if (project) {
      setForm({
        title: project.title || '',
        description: project.description || '',
        category: project.category || 'web',
        tags: Array.isArray(project.tags) ? project.tags.join(', ') : project.tags || '',
        price: project.price || '',
        duration: project.duration || '',
        featured: !!project.featured,
        photo_url: project.photo_url || '',
        problem: project.problem || '',
        approach: project.approach || '',
        outcome: project.outcome || '',
        stack: Array.isArray(project.stack) ? project.stack.join(', ') : project.stack || '',
      });
    } else {
      setForm(emptyForm());
    }
  }, [project]);

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const set = (patch) => setForm((f) => ({ ...f, ...patch }));

  const submit = async (e) => {
    e.preventDefault();
    const errs = {};
    if (!form.title.trim()) errs.title = 'Title is required';
    if (!form.description.trim()) errs.description = 'Description is required';
    if (!form.category.trim()) errs.category = 'Category is required';
    setFieldErrors(errs);
    if (Object.keys(errs).length) return;

    const payload = {
      ...form,
      tags: form.tags
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean),
      stack: form.stack
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean),
    };
    try {
      await run(() => onSave(payload, project?.id));
    } catch {
      /* SaveBadge shows the error */
    }
  };

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
          <h3>{project ? 'Edit project' : 'Add project'}</h3>
          <button type="button" className="studio-modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <div className="studio-form-grid">
          <div className="studio-form-col">
            <label className="studio-field">
              Title
              <input value={form.title} onChange={(e) => set({ title: e.target.value })} />
              {fieldErrors.title && <span className="studio-field-error">{fieldErrors.title}</span>}
            </label>
            <label className="studio-field">
              Description
              <textarea
                rows={4}
                value={form.description}
                onChange={(e) => set({ description: e.target.value })}
              />
              {fieldErrors.description && (
                <span className="studio-field-error">{fieldErrors.description}</span>
              )}
            </label>
            <div className="studio-field-row">
              <label className="studio-field">
                Category
                <input
                  list="project-categories"
                  value={form.category}
                  onChange={(e) => set({ category: e.target.value })}
                />
                <datalist id="project-categories">
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c} />
                  ))}
                </datalist>
              </label>
              <label className="studio-field">
                Tags (comma-separated)
                <input value={form.tags} onChange={(e) => set({ tags: e.target.value })} />
              </label>
            </div>
            <div className="studio-field-row">
              <label className="studio-field">
                Price
                <input value={form.price} onChange={(e) => set({ price: e.target.value })} placeholder="Rs.1,500" />
              </label>
              <label className="studio-field">
                Duration
                <input
                  value={form.duration}
                  onChange={(e) => set({ duration: e.target.value })}
                  placeholder="7 days"
                />
              </label>
            </div>
            <label className="studio-toggle">
              <input
                type="checkbox"
                checked={form.featured}
                onChange={(e) => set({ featured: e.target.checked })}
              />
              Featured project
            </label>

            <fieldset className="studio-fieldset">
              <legend>Case study (shown on the project page)</legend>
              <label className="studio-field">
                Problem
                <textarea
                  rows={3}
                  maxLength={4000}
                  value={form.problem}
                  onChange={(e) => set({ problem: e.target.value })}
                  placeholder="What did the client need? 2-3 sentences."
                />
              </label>
              <label className="studio-field">
                Approach
                <textarea
                  rows={3}
                  maxLength={4000}
                  value={form.approach}
                  onChange={(e) => set({ approach: e.target.value })}
                  placeholder="How was it built, and why those choices?"
                />
              </label>
              <label className="studio-field">
                Outcome
                <textarea
                  rows={3}
                  maxLength={4000}
                  value={form.outcome}
                  onChange={(e) => set({ outcome: e.target.value })}
                  placeholder="What was delivered or achieved?"
                />
              </label>
              <label className="studio-field">
                Stack (comma-separated)
                <input
                  value={form.stack}
                  onChange={(e) => set({ stack: e.target.value })}
                  placeholder="Flask, PostgreSQL, React"
                />
              </label>
            </fieldset>
          </div>

          <div className="studio-form-col">
            <span className="studio-field-label">Cover image</span>
            <ImageUpload
              value={form.photo_url}
              kind="projects"
              shape="landscape"
              onChange={(url) => set({ photo_url: url })}
            />
          </div>
        </div>

        <div className="studio-modal-foot">
          <SaveBadge status={status} error={error} savedLabel="Saved" />
          <div className="studio-modal-foot-actions">
            <button type="button" className="studio-btn studio-btn--ghost" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="studio-btn studio-btn--primary" disabled={status === 'saving'}>
              {project ? 'Save changes' : 'Add project'}
            </button>
          </div>
        </div>
      </motion.form>
    </div>
  );
}

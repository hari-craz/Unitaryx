import { useEffect, useState } from 'react';
import { getJSON, postJSON, putJSON, deleteReq } from '../../lib/api';
import { useSaveStatus } from './useSaveStatus';
import SaveBadge from './SaveBadge';

const STATUSES = ['Pending', 'In Progress', 'Done'];

function statusTone(status) {
  if (status === 'Done') return 'done';
  if (status === 'In Progress') return 'progress';
  return 'new';
}

export default function TasksPanel() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [form, setForm] = useState({ title: '', details: '', assigned_to_emails: [] });
  const [formError, setFormError] = useState('');
  const { status: saveState, error: saveError, run } = useSaveStatus();

  const load = () =>
    getJSON('/api/admin/tasks')
      .then(setData)
      .catch((err) => setError(err.message || 'Could not load tasks'));

  useEffect(() => {
    load();
  }, []);

  if (error) return <p className="admin-error">{error}</p>;
  if (!data) return <p className="admin-muted">Loading tasks…</p>;

  const submit = async (e) => {
    e.preventDefault();
    setFormError('');
    if (form.title.trim().length < 3) {
      setFormError('Task title must be at least 3 characters.');
      return;
    }
    if (form.assigned_to_emails.length === 0) {
      setFormError('Choose at least one admin to assign to.');
      return;
    }
    try {
      const res = await run(() => postJSON('/api/admin/tasks', form));
      setData((d) => ({ ...d, tasks: [...res.tasks, ...d.tasks] }));
      setForm({ title: '', details: '', assigned_to_emails: [] });
      if (res.email_sent === false) {
        const n = res.emails_failed?.length || 0;
        setFormError(
          `Assigned, but ${n === 1 ? 'one notification email' : `${n} notification emails`} could not be sent.`
        );
      }
    } catch (err) {
      setFormError(err.message || 'Could not assign task.');
    }
  };

  const toggleAssignee = (email) =>
    setForm((f) => ({
      ...f,
      assigned_to_emails: f.assigned_to_emails.includes(email)
        ? f.assigned_to_emails.filter((e) => e !== email)
        : [...f.assigned_to_emails, email],
    }));

  const allSelected =
    data.assignable_admins.length > 0 && form.assigned_to_emails.length === data.assignable_admins.length;

  const changeStatus = async (task, status) => {
    const res = await putJSON(`/api/admin/tasks/${task.id}/status`, { status });
    setData((d) => ({ ...d, tasks: d.tasks.map((t) => (t.id === task.id ? res.task : t)) }));
  };

  const remove = async (task) => {
    if (!window.confirm(`Delete task "${task.title}"?`)) return;
    await deleteReq(`/api/admin/tasks/${task.id}`);
    setData((d) => ({ ...d, tasks: d.tasks.filter((t) => t.id !== task.id) }));
  };

  return (
    <section className="admin-section">
      <div className="admin-section-head">
        <div>
          <h2>Task assignment</h2>
          <p className="admin-section-note">
            {data.tasks.length} task{data.tasks.length === 1 ? '' : 's'}
            {!data.can_assign && ' · showing tasks assigned to you'}
          </p>
        </div>
      </div>

      {data.can_assign && (
        <form className="admin-card glass workflow-form" onSubmit={submit}>
          <h3 className="dash-card-title">Assign a new task</h3>
          <div className="studio-field-row">
            <label className="studio-field">
              Title
              <input
                value={form.title}
                onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              />
            </label>
            <fieldset className="studio-field task-assignees">
              <legend>
                Assign to
                <span className="task-assignees-count">
                  {form.assigned_to_emails.length} selected
                </span>
              </legend>
              <div className="task-assignees-actions">
                <button
                  type="button"
                  className="studio-btn studio-btn--ghost"
                  onClick={() =>
                    setForm((f) => ({
                      ...f,
                      assigned_to_emails: allSelected ? [] : [...data.assignable_admins],
                    }))
                  }
                >
                  {allSelected ? 'Clear all' : 'Select all'}
                </button>
              </div>
              <div className="task-assignees-list">
                {data.assignable_admins.map((email) => (
                  <label key={email} className="studio-toggle">
                    <input
                      type="checkbox"
                      checked={form.assigned_to_emails.includes(email)}
                      onChange={() => toggleAssignee(email)}
                    />
                    {email}
                  </label>
                ))}
              </div>
            </fieldset>
          </div>
          <label className="studio-field">
            Details
            <textarea
              rows={3}
              value={form.details}
              onChange={(e) => setForm((f) => ({ ...f, details: e.target.value }))}
            />
          </label>
          <div className="workflow-form-foot">
            {formError && <span className="studio-field-error">{formError}</span>}
            <SaveBadge status={saveState} error={saveError} savedLabel="Assigned" />
            <button type="submit" className="studio-btn studio-btn--primary" disabled={saveState === 'saving'}>
              {form.assigned_to_emails.length > 1 ? `Assign to ${form.assigned_to_emails.length} admins` : 'Assign task'}
            </button>
          </div>
        </form>
      )}

      {data.tasks.length === 0 ? (
        <div className="admin-empty glass">
          <p className="admin-empty-title">No tasks yet</p>
          <p className="admin-muted">
            {data.can_assign ? 'Assign a task above to get started.' : 'Nothing is assigned to you right now.'}
          </p>
        </div>
      ) : (
        <div className="admin-card glass">
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Assigned to</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.tasks.map((t) => {
                  const mine = t.assigned_to_email === data.my_email;
                  const canEditStatus = mine || data.can_assign;
                  return (
                    <tr key={t.id}>
                      <td>
                        <span className="admin-row-title">{t.title}</span>
                        {t.details && <span className="admin-muted-inline">{t.details}</span>}
                      </td>
                      <td className="admin-mono">{t.assigned_to_email}</td>
                      <td>
                        {canEditStatus ? (
                          <select
                            className="dash-select"
                            value={t.status}
                            onChange={(e) => changeStatus(t, e.target.value)}
                          >
                            {STATUSES.map((s) => (
                              <option key={s} value={s}>
                                {s}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <span className={`admin-badge admin-badge--${statusTone(t.status)}`}>{t.status}</span>
                        )}
                      </td>
                      <td>
                        {data.can_assign && (
                          <button
                            type="button"
                            className="studio-btn studio-btn--danger"
                            onClick={() => remove(t)}
                          >
                            Delete
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}

import { useEffect, useState } from 'react';
import { getJSON, postJSON, putJSON, deleteReq } from '../../lib/api';

const EMPTY = { name: '', email: '', password: '', admin_scope: 'ops' };

function AdminForm({ admin, scopes, onClose, onSaved }) {
  const [form, setForm] = useState(
    admin
      ? { name: admin.name, email: admin.email, password: '', admin_scope: admin.admin_scope, is_active: admin.is_active }
      : EMPTY
  );
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const set = (patch) => setForm((f) => ({ ...f, ...patch }));

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      if (admin) {
        const payload = { name: form.name, email: form.email, admin_scope: form.admin_scope, is_active: form.is_active };
        if (form.password) payload.password = form.password;
        const res = await putJSON(`/api/admin/admins/${admin.id}`, payload);
        onSaved(res.admin, null);
      } else {
        const res = await postJSON('/api/admin/admins', form);
        onSaved(res.admin, null);
      }
    } catch (err) {
      setError(err.message || 'Could not save admin.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="studio-overlay" onClick={onClose} role="presentation">
      <form className="studio-modal glass-strong" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <div className="studio-modal-head">
          <h3>{admin ? 'Edit admin' : 'Add admin'}</h3>
          <button type="button" className="studio-modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className="studio-field-row">
          <label className="studio-field">
            Name
            <input value={form.name} onChange={(e) => set({ name: e.target.value })} />
          </label>
          <label className="studio-field">
            Email
            <input type="email" value={form.email} onChange={(e) => set({ email: e.target.value })} />
          </label>
        </div>
        <div className="studio-field-row">
          <label className="studio-field">
            Scope
            <select value={form.admin_scope} onChange={(e) => set({ admin_scope: e.target.value })}>
              {scopes.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label className="studio-field">
            {admin ? 'New password (optional)' : 'Password'}
            <input
              type="password"
              autoComplete="new-password"
              value={form.password}
              onChange={(e) => set({ password: e.target.value })}
              placeholder={admin ? 'Leave blank to keep' : 'min 6 chars'}
            />
          </label>
        </div>
        {admin && (
          <label className="studio-toggle">
            <input type="checkbox" checked={form.is_active} onChange={(e) => set({ is_active: e.target.checked })} />
            Active
          </label>
        )}
        <div className="studio-modal-foot">
          {error && <span className="studio-field-error">{error}</span>}
          <div className="studio-modal-foot-actions">
            <button type="button" className="studio-btn studio-btn--ghost" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="studio-btn studio-btn--primary" disabled={busy}>
              {admin ? 'Save changes' : 'Create admin'}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}

export default function AdminsPanel() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(null); // admin | 'new' | null
  const [tempPassword, setTempPassword] = useState(null);

  const load = () =>
    getJSON('/api/admin/admins')
      .then(setData)
      .catch((err) => setError(err.message || 'Could not load admins'));

  useEffect(() => {
    load();
  }, []);

  if (error) return <p className="admin-error">{error}</p>;
  if (!data) return <p className="admin-muted">Loading admins…</p>;

  if (!data.can_manage) {
    return (
      <section className="admin-section">
        <div className="admin-empty glass">
          <p className="admin-empty-title">Superadmin only</p>
          <p className="admin-muted">Admin account management requires the superadmin account.</p>
        </div>
      </section>
    );
  }

  const onSaved = (admin) => {
    setData((d) => {
      const exists = d.admins.some((a) => a.id === admin.id);
      return { ...d, admins: exists ? d.admins.map((a) => (a.id === admin.id ? admin : a)) : [...d.admins, admin] };
    });
    setEditing(null);
  };

  const remove = async (admin) => {
    if (!window.confirm(`Delete admin ${admin.email}? This cannot be undone.`)) return;
    try {
      await deleteReq(`/api/admin/admins/${admin.id}`);
      setData((d) => ({ ...d, admins: d.admins.filter((a) => a.id !== admin.id) }));
    } catch (err) {
      window.alert(err.message || 'Could not delete admin.');
    }
  };

  const resetPassword = async (admin) => {
    if (!window.confirm(`Reset password for ${admin.email}?`)) return;
    try {
      const res = await postJSON(`/api/admin/admins/${admin.id}/reset-password`, {});
      setTempPassword({ email: admin.email, password: res.temporary_password });
    } catch (err) {
      window.alert(err.message || 'Could not reset password.');
    }
  };

  return (
    <section className="admin-section">
      <div className="admin-section-head">
        <div>
          <h2>Admin accounts</h2>
          <p className="admin-section-note">{data.admins.length} admins</p>
        </div>
        <button type="button" className="studio-btn studio-btn--primary" onClick={() => setEditing('new')}>
          Add admin
        </button>
      </div>

      {tempPassword && (
        <div className="admin-card glass temp-pass">
          <p>
            Temporary password for <strong>{tempPassword.email}</strong>:{' '}
            <code>{tempPassword.password}</code> — share it securely; it is shown once.
          </p>
          <button type="button" className="studio-btn" onClick={() => setTempPassword(null)}>
            Dismiss
          </button>
        </div>
      )}

      <div className="admin-card glass">
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Admin</th>
                <th>Scope</th>
                <th>Active</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.admins.map((a) => (
                <tr key={a.id}>
                  <td>
                    <span className="admin-row-title">
                      {a.name}
                      {a.is_super && <span className="admin-badge admin-badge--ok super-tag">Superadmin</span>}
                    </span>
                    <span className="admin-mono admin-muted-inline">{a.email}</span>
                  </td>
                  <td className="admin-mono">{a.admin_scope}</td>
                  <td>
                    <span className={`admin-badge admin-badge--${a.is_active ? 'ok' : 'muted'}`}>
                      {a.is_active ? 'active' : 'disabled'}
                    </span>
                  </td>
                  <td>
                    <div className="admin-row-actions">
                      <button type="button" className="studio-btn studio-btn--ghost" onClick={() => setEditing(a)}>
                        Edit
                      </button>
                      <button type="button" className="studio-btn" onClick={() => resetPassword(a)}>
                        Reset password
                      </button>
                      {!a.is_super && (
                        <button type="button" className="studio-btn studio-btn--danger" onClick={() => remove(a)}>
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

      {editing && (
        <AdminForm
          admin={editing === 'new' ? null : editing}
          scopes={data.scopes}
          onClose={() => setEditing(null)}
          onSaved={onSaved}
        />
      )}
    </section>
  );
}

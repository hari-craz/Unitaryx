import { useEffect, useRef, useState } from 'react';
import { Reorder, useDragControls } from 'framer-motion';
import { getJSON, postJSON, putJSON, deleteReq } from '../../lib/api';
import { useSaveStatus } from './useSaveStatus';
import FounderForm from './FounderForm';
import SaveBadge from './SaveBadge';

function FounderRow({ founder, onEdit, onDelete, onReorderEnd }) {
  const controls = useDragControls();
  return (
    <Reorder.Item
      value={founder}
      dragListener={false}
      dragControls={controls}
      onDragEnd={onReorderEnd}
      className="admin-row glass"
    >
      <button
        type="button"
        className="admin-drag"
        aria-label="Drag to reorder"
        onPointerDown={(e) => controls.start(e)}
      >
        ⠿
      </button>
      <div className="admin-row-thumb admin-row-thumb--portrait">
        {founder.photo_url ? <img src={founder.photo_url} alt="" /> : <span>{founder.name.charAt(0)}</span>}
      </div>
      <div className="admin-row-main">
        <p className="admin-row-title">{founder.name}</p>
        <p className="admin-row-sub">{founder.role}</p>
      </div>
      {!founder.active && <span className="admin-badge admin-badge--muted">Hidden</span>}
      <div className="admin-row-actions">
        <button type="button" className="studio-btn studio-btn--ghost" onClick={() => onEdit(founder)}>
          Edit
        </button>
        <button type="button" className="studio-btn studio-btn--danger" onClick={() => onDelete(founder)}>
          Delete
        </button>
      </div>
    </Reorder.Item>
  );
}

export default function FoundersManager() {
  const [founders, setFounders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const [editing, setEditing] = useState(null); // founder object, 'new', or null
  const foundersRef = useRef(founders);
  const { status: orderStatus, run: runOrder } = useSaveStatus();

  foundersRef.current = founders;

  const load = () => {
    setLoading(true);
    getJSON('/api/admin/founders')
      .then((data) => {
        setDenied(false);
        setFounders(data);
      })
      .catch((err) => {
        if (err.status === 403) setDenied(true);
        setFounders([]);
      })
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const persistOrder = () => {
    const order = foundersRef.current.map((f) => f.id);
    runOrder(() => postJSON('/api/admin/founders/reorder', { order })).catch(() => load());
  };

  const handleSave = async (data, id) => {
    if (id) {
      const res = await putJSON(`/api/admin/founders/${id}`, data);
      setFounders((list) => list.map((f) => (f.id === id ? res.founder : f)));
    } else {
      const res = await postJSON('/api/admin/founders', data);
      setFounders((list) => [...list, res.founder]);
    }
    setEditing(null);
  };

  const handleDelete = async (founder) => {
    if (!window.confirm(`Delete ${founder.name}? This cannot be undone.`)) return;
    try {
      await deleteReq(`/api/admin/founders/${founder.id}`);
      setFounders((list) => list.filter((f) => f.id !== founder.id));
    } catch (err) {
      window.alert(err.message || 'Could not delete team member.');
    }
  };

  if (!loading && denied) {
    return (
      <section className="admin-section">
        <div className="admin-section-head">
          <h2>Team members</h2>
        </div>
        <div className="admin-empty glass">
          <p className="admin-empty-title">Superadmin only</p>
          <p className="admin-muted">
            Managing the team roster is restricted to the superadmin account.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="admin-section">
      <div className="admin-section-head">
        <div>
          <h2>Team members</h2>
          <p className="admin-section-note">
            {founders.length} member{founders.length === 1 ? '' : 's'} · drag to reorder
          </p>
        </div>
        <div className="admin-section-head-actions">
          <SaveBadge status={orderStatus} savedLabel="Order saved" />
          <button type="button" className="studio-btn studio-btn--primary" onClick={() => setEditing('new')}>
            Add member
          </button>
        </div>
      </div>

      {loading ? (
        <p className="admin-muted">Loading…</p>
      ) : founders.length === 0 ? (
        <div className="admin-empty glass">
          <p className="admin-empty-title">No team members yet</p>
          <p className="admin-muted">Add your first team member to populate the site carousel.</p>
          <button type="button" className="studio-btn studio-btn--primary" onClick={() => setEditing('new')}>
            Add your first member
          </button>
        </div>
      ) : (
        <Reorder.Group axis="y" values={founders} onReorder={setFounders} className="admin-list">
          {founders.map((f) => (
            <FounderRow
              key={f.id}
              founder={f}
              onEdit={setEditing}
              onDelete={handleDelete}
              onReorderEnd={persistOrder}
            />
          ))}
        </Reorder.Group>
      )}

      {editing && (
        <FounderForm
          founder={editing === 'new' ? null : editing}
          onSave={handleSave}
          onClose={() => setEditing(null)}
        />
      )}
    </section>
  );
}

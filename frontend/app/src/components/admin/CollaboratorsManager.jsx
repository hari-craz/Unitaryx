import { useEffect, useRef, useState } from 'react';
import { Reorder, useDragControls } from 'framer-motion';
import { getJSON, postJSON, putJSON, deleteReq } from '../../lib/api';
import { useSaveStatus } from './useSaveStatus';
import CollaboratorForm from './CollaboratorForm';
import SaveBadge from './SaveBadge';

const KIND_LABEL = { startup: 'Startup', freelancer: 'Freelancer' };

function CollaboratorRow({ item, onEdit, onDelete, onReorderEnd }) {
  const controls = useDragControls();
  return (
    <Reorder.Item
      value={item}
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
      <div className="admin-row-thumb admin-row-thumb--square">
        {item.logo_url ? <img src={item.logo_url} alt="" /> : <span>{item.name.charAt(0)}</span>}
      </div>
      <div className="admin-row-main">
        <p className="admin-row-title">{item.name}</p>
        <p className="admin-row-sub">
          {KIND_LABEL[item.kind] || item.kind}
          {item.founder_name ? ` · ${item.founder_name}` : ''}
        </p>
      </div>
      {!item.active && <span className="admin-badge admin-badge--muted">Hidden</span>}
      <div className="admin-row-actions">
        <button type="button" className="studio-btn studio-btn--ghost" onClick={() => onEdit(item)}>
          Edit
        </button>
        <button type="button" className="studio-btn studio-btn--danger" onClick={() => onDelete(item)}>
          Remove
        </button>
      </div>
    </Reorder.Item>
  );
}

export default function CollaboratorsManager() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const [editing, setEditing] = useState(null); // item, 'new' or null
  const itemsRef = useRef(items);
  const { status: orderStatus, run: runOrder } = useSaveStatus();

  itemsRef.current = items;

  const load = () => {
    setLoading(true);
    getJSON('/api/admin/collaborators')
      .then((data) => {
        setDenied(false);
        setItems(data);
      })
      .catch((err) => {
        if (err.status === 403) setDenied(true);
        setItems([]);
      })
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const persistOrder = () => {
    const order = itemsRef.current.map((c) => c.id);
    runOrder(() => postJSON('/api/admin/collaborators/reorder', { order })).catch(() => load());
  };

  const handleSave = async (data, id) => {
    if (id) {
      const res = await putJSON(`/api/admin/collaborators/${id}`, data);
      setItems((list) => list.map((c) => (c.id === id ? res.collaborator : c)));
    } else {
      const res = await postJSON('/api/admin/collaborators', data);
      setItems((list) => [...list, res.collaborator]);
    }
    setEditing(null);
  };

  const handleDelete = async (item) => {
    if (!window.confirm(`Remove ${item.name} from the collaborators page? This cannot be undone.`)) return;
    try {
      await deleteReq(`/api/admin/collaborators/${item.id}`);
      setItems((list) => list.filter((c) => c.id !== item.id));
    } catch (err) {
      window.alert(err.message || 'Could not remove collaborator.');
    }
  };

  if (!loading && denied) {
    return (
      <section className="admin-section">
        <div className="admin-section-head">
          <h2>Collaborators</h2>
        </div>
        <div className="admin-empty glass">
          <p className="admin-empty-title">Superadmin only</p>
          <p className="admin-muted">Managing collaborators is restricted to the superadmin account.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="admin-section">
      <div className="admin-section-head">
        <div>
          <h2>Collaborators</h2>
          <p className="admin-section-note">
            {items.length} collaborator{items.length === 1 ? '' : 's'} · drag to reorder
          </p>
        </div>
        <div className="admin-section-head-actions">
          <SaveBadge status={orderStatus} savedLabel="Order saved" />
          <button type="button" className="studio-btn studio-btn--primary" onClick={() => setEditing('new')}>
            Add collaborator
          </button>
        </div>
      </div>

      {loading ? (
        <p className="admin-muted">Loading…</p>
      ) : items.length === 0 ? (
        <div className="admin-empty glass">
          <p className="admin-empty-title">No collaborators yet</p>
          <p className="admin-muted">
            Add a startup or freelancer. The collaborators page and the homepage strip stay hidden until you do.
          </p>
          <button type="button" className="studio-btn studio-btn--primary" onClick={() => setEditing('new')}>
            Add your first collaborator
          </button>
        </div>
      ) : (
        <Reorder.Group axis="y" values={items} onReorder={setItems} className="admin-list">
          {items.map((c) => (
            <CollaboratorRow
              key={c.id}
              item={c}
              onEdit={setEditing}
              onDelete={handleDelete}
              onReorderEnd={persistOrder}
            />
          ))}
        </Reorder.Group>
      )}

      {editing && (
        <CollaboratorForm
          collaborator={editing === 'new' ? null : editing}
          onSave={handleSave}
          onClose={() => setEditing(null)}
        />
      )}
    </section>
  );
}

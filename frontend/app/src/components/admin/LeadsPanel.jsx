import { useEffect, useMemo, useState } from 'react';
import { getJSON, putJSON, postJSON, deleteReq } from '../../lib/api';
import LeadDrawer from './LeadDrawer';

const STATUSES = ['New', 'In Progress', 'Done'];
const TIER_TONE = { A: 'ok', B: 'progress', C: 'muted', D: 'muted' };

function money(n) {
  return `Rs ${Number(n || 0).toLocaleString('en-IN')}`;
}
function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}
function fmtId(id) {
  return String(id).padStart(4, '0');
}

export default function LeadsPanel() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [filters, setFilters] = useState({ search: '', status: 'all', sort: 'newest' });
  const [selected, setSelected] = useState(new Set());
  const [active, setActive] = useState(null);
  const [notice, setNotice] = useState('');

  const load = () =>
    getJSON('/api/admin/leads')
      .then((d) => {
        setData(d);
        setSelected(new Set());
      })
      .catch((err) => setError(err.message || 'Could not load leads'));

  useEffect(() => {
    load();
  }, []);

  const filtered = useMemo(() => {
    if (!data) return [];
    const q = filters.search.trim().toLowerCase();
    let list = data.leads.filter((r) => {
      const blob = `${r.id} ${r.name} ${r.email} ${r.service} ${r.status} ${r.message}`.toLowerCase();
      const okSearch = !q || blob.includes(q);
      const okStatus = filters.status === 'all' || (r.status || '').toLowerCase() === filters.status;
      return okSearch && okStatus;
    });
    list = [...list].sort((a, b) => {
      switch (filters.sort) {
        case 'oldest':
          return Date.parse(a.created_at) - Date.parse(b.created_at);
        case 'value':
          return (b.value || 0) - (a.value || 0);
        case 'score':
          return (b.lead_score_total || 0) - (a.lead_score_total || 0);
        default:
          return Date.parse(b.created_at) - Date.parse(a.created_at);
      }
    });
    return list;
  }, [data, filters]);

  if (error) return <p className="admin-error">{error}</p>;
  if (!data) return <p className="admin-muted">Loading leads…</p>;

  const toggle = (id) =>
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const allVisibleSelected = filtered.length > 0 && filtered.every((r) => selected.has(r.id));
  const toggleAll = () =>
    setSelected(allVisibleSelected ? new Set() : new Set(filtered.map((r) => r.id)));

  const runBulk = async (action) => {
    if (selected.size === 0) return;
    if (action === 'delete' && !window.confirm(`Delete ${selected.size} selected inquiries?`)) return;
    try {
      const res = await postJSON('/api/admin/leads/bulk', { action, ids: [...selected] });
      setNotice(res.queued ? res.message : `Applied "${action}" to ${res.count} inquiries.`);
      await load();
    } catch (err) {
      setNotice(err.message || 'Bulk action failed.');
    }
  };

  const saveLead = async (id, patch) => {
    let res;
    try {
      res = await putJSON(`/api/admin/leads/${id}`, patch);
    } catch (err) {
      setNotice(err.message || 'Could not save the change.');
      await load();
      return;
    }
    if (res.queued) {
      await load();
      setNotice(res.message);
      setActive(null);
      return;
    }
    setData((d) => ({ ...d, leads: d.leads.map((r) => (r.id === id ? res.lead : r)) }));
    setActive((a) => (a && a.id === id ? res.lead : a));
  };

  const deleteLead = async (lead) => {
    if (!window.confirm(`Delete inquiry #${fmtId(lead.id)} from ${lead.name}?`)) return;
    let res;
    try {
      res = await deleteReq(`/api/admin/leads/${lead.id}`);
    } catch (err) {
      setNotice(err.message || 'Could not delete the inquiry.');
      return;
    }
    if (res.queued) setNotice(res.message);
    else setData((d) => ({ ...d, leads: d.leads.filter((r) => r.id !== lead.id) }));
    setActive(null);
  };

  const s = data.summary;

  return (
    <section className="admin-section">
      <div className="admin-section-head">
        <div>
          <h2>Leads</h2>
          <p className="admin-section-note">
            {s.total} inquiries · {s.updates} with updates
            {!data.is_super && ' · sensitive changes queue for approval'}
          </p>
        </div>
        <div className="admin-section-head-actions">
          <a className="studio-btn" href="/admin/export/csv">
            CSV
          </a>
          <a className="studio-btn" href="/admin/export/pdf">
            PDF
          </a>
        </div>
      </div>

      <div className="analytics-kpis">
        <article className="kpi-card glass">
          <p className="kpi-label">Total value</p>
          <p className="kpi-value">{money(s.total_value)}</p>
        </article>
        <article className="kpi-card glass">
          <p className="kpi-label">New</p>
          <p className="kpi-value">{s.new}</p>
        </article>
        <article className="kpi-card glass">
          <p className="kpi-label">In progress</p>
          <p className="kpi-value">{s.in_progress}</p>
        </article>
        <article className="kpi-card glass">
          <p className="kpi-label">Done</p>
          <p className="kpi-value">{s.done}</p>
        </article>
      </div>

      <div className="dash-toolbar">
        <input
          className="dash-input"
          type="search"
          placeholder="Search id, name, email, service, message…"
          value={filters.search}
          onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
        />
        <select
          className="dash-select"
          value={filters.status}
          onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
        >
          <option value="all">All status</option>
          <option value="new">New</option>
          <option value="in progress">In Progress</option>
          <option value="done">Done</option>
        </select>
        <select
          className="dash-select"
          value={filters.sort}
          onChange={(e) => setFilters((f) => ({ ...f, sort: e.target.value }))}
        >
          <option value="newest">Newest</option>
          <option value="oldest">Oldest</option>
          <option value="value">Highest value</option>
          <option value="score">Lead score</option>
        </select>
        <span className="dash-result-count">{filtered.length} shown</span>
      </div>

      {selected.size > 0 && (
        <div className="leads-bulkbar glass">
          <span>{selected.size} selected</span>
          <button type="button" className="studio-btn" onClick={() => runBulk('mark_progress')}>
            Mark In Progress
          </button>
          <button type="button" className="studio-btn" onClick={() => runBulk('mark_done')}>
            Mark Done
          </button>
          <button type="button" className="studio-btn" onClick={() => runBulk('priority_high')}>
            Priority High
          </button>
          <button type="button" className="studio-btn studio-btn--danger" onClick={() => runBulk('delete')}>
            Delete
          </button>
        </div>
      )}

      {notice && <p className="leads-notice">{notice}</p>}

      <div className="admin-card glass">
        <div className="admin-table-wrap">
          <table className="admin-table leads-table">
            <thead>
              <tr>
                <th>
                  <input type="checkbox" checked={allVisibleSelected} onChange={toggleAll} aria-label="Select all" />
                </th>
                <th>Inquiry</th>
                <th>Service</th>
                <th>Status</th>
                <th>Priority</th>
                <th>Value</th>
                <th>Score</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.id} className={r.is_new_update ? 'lead-row--updated' : ''}>
                  <td>
                    <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggle(r.id)} aria-label={`Select ${r.id}`} />
                  </td>
                  <td>
                    <span className="admin-row-title">
                      #{fmtId(r.id)} {r.name}
                    </span>
                    <span className="admin-muted-inline">
                      {r.email} · {fmtDate(r.created_at)}
                    </span>
                  </td>
                  <td className="admin-mono">{r.service}</td>
                  <td>
                    <select
                      className="dash-select"
                      value={r.status}
                      onChange={(e) => saveLead(r.id, { status: e.target.value, priority: r.priority, value: r.value })}
                    >
                      {STATUSES.map((st) => (
                        <option key={st} value={st}>
                          {st}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>{r.priority}</td>
                  <td className="admin-mono">{money(r.value)}</td>
                  <td>
                    <span className={`admin-badge admin-badge--${TIER_TONE[r.lead_tier] || 'muted'}`}>
                      {r.lead_tier} · {r.lead_score_total}
                    </span>
                  </td>
                  <td>
                    <button type="button" className="studio-btn studio-btn--ghost" onClick={() => setActive(r)}>
                      Open
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {active && (
        <LeadDrawer
          lead={active}
          isSuper={data.is_super}
          onClose={() => setActive(null)}
          onSave={saveLead}
          onDelete={deleteLead}
        />
      )}
    </section>
  );
}

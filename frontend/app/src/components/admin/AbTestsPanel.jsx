import { useEffect, useState } from 'react';
import { getJSON, putJSON, deleteReq } from '../../lib/api';
import { useSaveStatus } from './useSaveStatus';
import SaveBadge from './SaveBadge';

const MIN_EXPOSURES = 100;

function rate(v) {
  return v.exposures ? (v.conversions / v.exposures) * 100 : 0;
}

function Results({ stats, canEdit, onReset }) {
  const a = stats?.A || { exposures: 0, conversions: 0 };
  const b = stats?.B || { exposures: 0, conversions: 0 };
  if (!a.exposures && !b.exposures) {
    return <p className="admin-muted">No results yet. Visitors are counted the first time they see the element.</p>;
  }
  const enough = a.exposures >= MIN_EXPOSURES && b.exposures >= MIN_EXPOSURES;
  const rows = [
    ['A', a],
    ['B', b],
  ];
  return (
    <div className="ab-results">
      <table className="admin-table">
        <thead>
          <tr>
            <th>Variant</th>
            <th>Visitors</th>
            <th>Clicks</th>
            <th>Click rate</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, v]) => (
            <tr key={label}>
              <td>{label}</td>
              <td>{v.exposures}</td>
              <td>{v.conversions}</td>
              <td>{rate(v).toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="admin-muted">
        {enough
          ? 'Both variants have enough visitors for a first read; keep the test running before acting on small differences.'
          : `Wait for at least ${MIN_EXPOSURES} visitors per variant before drawing conclusions.`}{' '}
        Changing the split or the wording mid-test mixes old and new results.
      </p>
      {canEdit && (
        <button type="button" className="studio-btn studio-btn--ghost" onClick={onReset}>
          Reset results
        </button>
      )}
    </div>
  );
}

function AbTestCard({ test, stats, canEdit, onSaved, onReset }) {
  const [form, setForm] = useState(test);
  const { status, error, run } = useSaveStatus();

  useEffect(() => setForm(test), [test]);

  const set = (patch) => setForm((f) => ({ ...f, ...patch }));
  const dirty =
    form.enabled !== test.enabled ||
    form.allocation_b !== test.allocation_b ||
    form.variant_a !== test.variant_a ||
    form.variant_b !== test.variant_b;

  const save = async () => {
    try {
      const res = await run(() =>
        putJSON(`/api/admin/ab-tests/${test.id}`, {
          enabled: form.enabled,
          allocation_b: form.allocation_b,
          variant_a: form.variant_a,
          variant_b: form.variant_b,
        })
      );
      onSaved(res.test);
    } catch {
      /* SaveBadge surfaces the error */
    }
  };

  return (
    <article className="admin-card glass">
      <div className="admin-card-head">
        <div>
          <h3 className="dash-card-title">{test.label}</h3>
          <p className="admin-mono admin-muted-inline">{test.test_key}</p>
        </div>
        <div className="admin-section-head-actions">
          <SaveBadge status={status} error={error} />
          <label className="dash-toggle">
            <input
              type="checkbox"
              checked={form.enabled}
              disabled={!canEdit}
              onChange={(e) => set({ enabled: e.target.checked })}
            />
            Enabled
          </label>
        </div>
      </div>

      <div className="ab-variants">
        <label className="studio-field">
          Variant A
          <textarea
            rows={2}
            value={form.variant_a}
            disabled={!canEdit}
            onChange={(e) => set({ variant_a: e.target.value })}
          />
        </label>
        <label className="studio-field">
          Variant B
          <textarea
            rows={2}
            value={form.variant_b}
            disabled={!canEdit}
            onChange={(e) => set({ variant_b: e.target.value })}
          />
        </label>
      </div>

      <div className="ab-allocation">
        <label className="studio-field">
          Traffic to variant B: <strong>{form.allocation_b}%</strong>
          <input
            type="range"
            min="0"
            max="100"
            value={form.allocation_b}
            disabled={!canEdit}
            onChange={(e) => set({ allocation_b: Number(e.target.value) })}
          />
        </label>
        <div className="ab-split-bar" aria-hidden="true">
          <span className="ab-split-a" style={{ width: `${100 - form.allocation_b}%` }}>
            A {100 - form.allocation_b}%
          </span>
          <span className="ab-split-b" style={{ width: `${form.allocation_b}%` }}>
            B {form.allocation_b}%
          </span>
        </div>
      </div>

      <Results stats={stats} canEdit={canEdit} onReset={() => onReset(test)} />

      {canEdit && (
        <div className="ab-actions">
          <button
            type="button"
            className="studio-btn studio-btn--ghost"
            onClick={() => setForm(test)}
            disabled={!dirty}
          >
            Reset
          </button>
          <button
            type="button"
            className="studio-btn studio-btn--primary"
            onClick={save}
            disabled={!dirty || status === 'saving'}
          >
            Save changes
          </button>
        </div>
      )}
    </article>
  );
}

export default function AbTestsPanel() {
  const [tests, setTests] = useState([]);
  const [stats, setStats] = useState({});
  const [canEdit, setCanEdit] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    getJSON('/api/admin/ab-tests')
      .then((data) => {
        setTests(data.tests);
        setStats(data.stats || {});
        setCanEdit(data.can_edit);
      })
      .catch((err) => setError(err.message || 'Could not load A/B tests'))
      .finally(() => setLoading(false));
  }, []);

  const handleSaved = (updated) =>
    setTests((list) => list.map((t) => (t.id === updated.id ? updated : t)));

  const handleReset = async (test) => {
    if (!window.confirm(`Clear all collected results for "${test.label}"? This cannot be undone.`)) return;
    try {
      await deleteReq(`/api/admin/ab-tests/${test.id}/results`);
      setStats((s) => {
        const next = { ...s };
        delete next[test.test_key];
        return next;
      });
    } catch (err) {
      window.alert(err.message || 'Could not reset results.');
    }
  };

  if (loading) return <p className="admin-muted">Loading A/B tests…</p>;
  if (error) return <p className="admin-error">{error}</p>;

  return (
    <section className="admin-section">
      <div className="admin-section-head">
        <div>
          <h2>A/B tests</h2>
          <p className="admin-section-note">
            {tests.length} experiment{tests.length === 1 ? '' : 's'}
            {!canEdit && ' · read-only (requires superadmin)'}
          </p>
        </div>
      </div>

      {tests.length === 0 ? (
        <div className="admin-empty glass">
          <p className="admin-empty-title">No experiments configured</p>
          <p className="admin-muted">A/B test configs appear here once created.</p>
        </div>
      ) : (
        tests.map((t) => (
          <AbTestCard
            key={t.id}
            test={t}
            stats={stats[t.test_key]}
            canEdit={canEdit}
            onSaved={handleSaved}
            onReset={handleReset}
          />
        ))
      )}
    </section>
  );
}

import { useMemo, useState } from 'react';
import { useDashboard } from '../hooks/useDashboard';
import { usePageMeta } from '../hooks/usePageMeta';
import DashboardHeader from '../components/dashboard/DashboardHeader';
import KpiRow from '../components/dashboard/KpiRow';
import StatusPills from '../components/dashboard/StatusPills';
import StatusDonut from '../components/dashboard/StatusDonut';
import RequestToolbar from '../components/dashboard/RequestToolbar';
import RequestGrid from '../components/dashboard/RequestGrid';
import RecentActivity from '../components/dashboard/RecentActivity';
import QuickActions from '../components/dashboard/QuickActions';
import RoadmapModal from '../components/dashboard/RoadmapModal';
import DashboardSkeleton from '../components/dashboard/DashboardSkeleton';
import { priorityScore, sortTimestamp } from '../components/dashboard/dashboardUtils';
import { exportRequestsToCsv } from '../components/dashboard/exportCsv';
import './Dashboard.css';

const DEFAULT_FILTERS = { search: '', status: 'all', sort: 'newest', updatedOnly: false };

export default function Dashboard() {
  const { user, requests, loading, error } = useDashboard();
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [activeRequest, setActiveRequest] = useState(null);

  usePageMeta('Dashboard — Unitary X', { noindex: true });

  const counts = useMemo(() => {
    const c = { total: requests.length, New: 0, 'In Progress': 0, Done: 0, updates: 0 };
    requests.forEach((r) => {
      if (c[r.status] !== undefined) c[r.status] += 1;
      if (r.is_updated) c.updates += 1;
    });
    return c;
  }, [requests]);

  const kpis = useMemo(() => {
    const totalValue = requests.reduce((sum, r) => sum + (r.value || 0), 0);
    const completion = requests.length ? Math.round((counts.Done / requests.length) * 100) : 0;
    const avgValue = requests.length ? Math.floor(totalValue / requests.length) : 0;
    return { totalValue, completion, avgValue, updates: counts.updates };
  }, [requests, counts]);

  const filtered = useMemo(() => {
    const q = filters.search.trim().toLowerCase();
    const status = filters.status.toLowerCase();
    let list = requests.filter((r) => {
      const blob = `${r.id} ${r.service} ${r.status} ${r.message}`.toLowerCase();
      const matchSearch = !q || blob.includes(q);
      const matchStatus = status === 'all' || (r.status || '').toLowerCase() === status;
      const matchUpdated = !filters.updatedOnly || r.is_updated;
      return matchSearch && matchStatus && matchUpdated;
    });
    list = [...list].sort((a, b) => {
      switch (filters.sort) {
        case 'oldest':
          return sortTimestamp(a.created_at) - sortTimestamp(b.created_at);
        case 'highvalue':
          return (b.value || 0) - (a.value || 0);
        case 'priority':
          return (
            priorityScore(b.priority) - priorityScore(a.priority) ||
            sortTimestamp(b.created_at) - sortTimestamp(a.created_at)
          );
        default:
          return sortTimestamp(b.created_at) - sortTimestamp(a.created_at);
      }
    });
    return list;
  }, [requests, filters]);

  if (loading) return <DashboardSkeleton />;

  if (error) {
    // 401 → session expired; bounce to login. Any other error → simple message.
    if (error.status === 401) {
      window.location.href = '/login';
      return null;
    }
    return (
      <div className="dash-shell">
        <p className="dash-error">Could not load your dashboard. Please refresh and try again.</p>
      </div>
    );
  }

  return (
    <div className="dash-shell">
      <DashboardHeader firstName={user?.first_name} />

      <KpiRow kpis={kpis} />

      <div className="dash-two-col">
        <StatusDonut counts={counts} />
        <StatusPills counts={counts} />
      </div>

      <section className="dash-section">
        <div className="dash-section-head">
          <h2>My Project Requests</h2>
          <RequestToolbar
            filters={filters}
            setFilters={setFilters}
            resultCount={filtered.length}
            onReset={() => setFilters(DEFAULT_FILTERS)}
            onExport={() => exportRequestsToCsv(filtered)}
          />
        </div>
        <RequestGrid
          requests={filtered}
          isEmpty={requests.length === 0}
          onOpen={setActiveRequest}
        />
      </section>

      <div className="dash-bottom-grid">
        <RecentActivity requests={requests} />
        <QuickActions />
      </div>

      {activeRequest && (
        <RoadmapModal request={activeRequest} onClose={() => setActiveRequest(null)} />
      )}
    </div>
  );
}

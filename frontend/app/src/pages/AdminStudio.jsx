import { useEffect, useState } from 'react';
import { getJSON, postJSON } from '../lib/api';
import { usePageMeta } from '../hooks/usePageMeta';
import FoundersManager from '../components/admin/FoundersManager';
import ProjectsManager from '../components/admin/ProjectsManager';
import AnalyticsPanel from '../components/admin/AnalyticsPanel';
import LiveUsersPanel from '../components/admin/LiveUsersPanel';
import AbTestsPanel from '../components/admin/AbTestsPanel';
import TasksPanel from '../components/admin/TasksPanel';
import FinancePanel from '../components/admin/FinancePanel';
import ApprovalsPanel from '../components/admin/ApprovalsPanel';
import LeadsPanel from '../components/admin/LeadsPanel';
import AdminsPanel from '../components/admin/AdminsPanel';
import SessionsPanel from '../components/admin/SessionsPanel';
import BackupsPanel from '../components/admin/BackupsPanel';
import NewsletterPanel from '../components/admin/NewsletterPanel';
import './AdminStudio.css';

// `superadmin: true` tabs are entirely hidden from non-superadmin admins —
// these manage site content, other admin accounts, or raw DB backups, and
// the backend rejects non-superadmins outright (see api_superadmin_required /
// is_super_admin() in backend/app.py). `capability` tabs are hidden unless
// the signed-in admin's scope grants that capability (mirrors
// ADMIN_SCOPE_CAPABILITIES in backend/app.py). Tabs with neither are visible
// to every admin because their panel is read-accessible to all scopes, with
// any mutating action already gated on a `can_*` flag from its own API.
const TABS = [
  { key: 'leads', label: 'Leads', capability: 'lead_manage' },
  { key: 'founders', label: 'Team', superadmin: true },
  { key: 'projects', label: 'Projects', superadmin: true },
  { key: 'analytics', label: 'Analytics', capability: 'analytics_view' },
  { key: 'live', label: 'Live users', capability: 'analytics_view' },
  { key: 'abtests', label: 'A/B tests' },
  { key: 'tasks', label: 'Tasks' },
  { key: 'finance', label: 'Finance', capability: 'finance_ops' },
  { key: 'approvals', label: 'Approvals' },
  { key: 'admins', label: 'Admins', superadmin: true },
  { key: 'sessions', label: 'Sessions' },
  { key: 'newsletter', label: 'Newsletter', superadmin: true },
  { key: 'backups', label: 'Backups', superadmin: true },
];

function visibleTabs(user) {
  if (!user) return [];
  const isSuper = !!user.is_superadmin;
  const caps = user.capabilities || [];
  return TABS.filter((t) => {
    if (t.superadmin) return isSuper;
    if (t.capability) return isSuper || caps.includes(t.capability);
    return true;
  });
}

const PANELS = {
  leads: LeadsPanel,
  founders: FoundersManager,
  projects: ProjectsManager,
  analytics: AnalyticsPanel,
  live: LiveUsersPanel,
  abtests: AbTestsPanel,
  tasks: TasksPanel,
  finance: FinancePanel,
  approvals: ApprovalsPanel,
  admins: AdminsPanel,
  sessions: SessionsPanel,
  newsletter: NewsletterPanel,
  backups: BackupsPanel,
};

async function handleLogout() {
  try {
    await postJSON('/api/auth/logout', {});
  } catch {
    // Fall through to a hard redirect regardless — the session cookie is
    // cleared server-side and /login will re-gate if anything lingered.
  }
  window.location.href = '/login';
}

export default function AdminStudio() {
  const [session, setSession] = useState({ loading: true, user: null });
  const [tab, setTab] = useState(null);

  usePageMeta('Studio — Unitary X Admin', { noindex: true });

  useEffect(() => {
    getJSON('/api/auth/session')
      .then((data) => {
        if (!data.authenticated || data.user?.role !== 'admin') {
          window.location.href = '/login';
          return;
        }
        setSession({ loading: false, user: data.user });
        setTab(visibleTabs(data.user)[0]?.key || null);
      })
      .catch(() => {
        window.location.href = '/login';
      });
  }, []);

  if (session.loading) {
    return (
      <div className="studio-shell">
        <p className="studio-loading">Loading studio…</p>
      </div>
    );
  }

  const tabs = visibleTabs(session.user);

  return (
    <div className="studio-shell">
      <header className="studio-header glass">
        <div>
          <p className="studio-eyebrow">Unitary X · Admin studio</p>
          <h1>Content management</h1>
        </div>
        <div className="studio-header-actions">
          <a className="studio-btn" href="/">
            View site
          </a>
          <button type="button" className="studio-btn studio-btn--danger" onClick={handleLogout}>
            Log out
          </button>
        </div>
      </header>

      <nav className="studio-tabs" aria-label="Studio sections">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            className={`studio-tab ${tab === t.key ? 'active' : ''}`}
            onClick={() => setTab(t.key)}
            aria-pressed={tab === t.key}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <main className="studio-main">{(() => {
        const Panel = PANELS[tab];
        return Panel ? <Panel /> : <p className="admin-muted">Nothing to show yet.</p>;
      })()}</main>
    </div>
  );
}

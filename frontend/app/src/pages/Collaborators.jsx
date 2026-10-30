import { useState } from 'react';
import { motion } from 'framer-motion';
import NavBar from '../components/layout/NavBar';
import Footer from '../components/layout/Footer';
import SkeletonCard from '../components/common/SkeletonCard';
import { useCollaborators } from '../hooks/useCollaborators';
import { usePageMeta } from '../hooks/usePageMeta';
import './Collaborators.css';

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'startup', label: 'Startups' },
  { key: 'freelancer', label: 'Freelancers' },
];

const KIND_LABEL = { startup: 'Startup', freelancer: 'Freelancer' };

function Logo({ item }) {
  return (
    <span className="collab-logo">
      {item.logo_url ? (
        <img src={item.logo_url} alt={`${item.name} logo`} loading="lazy" />
      ) : (
        <span aria-hidden="true">{item.name.charAt(0).toUpperCase()}</span>
      )}
    </span>
  );
}

function CollaboratorCard({ item, index }) {
  return (
    <motion.article
      className="collab-card glass"
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.2 }}
      transition={{ delay: Math.min(index * 0.04, 0.3), type: 'spring', stiffness: 240, damping: 26 }}
    >
      <div className="collab-head">
        <Logo item={item} />
        <div className="collab-title">
          <h2 className="collab-name">{item.name}</h2>
          <span className={`collab-badge collab-badge--${item.kind}`}>{KIND_LABEL[item.kind] || item.kind}</span>
        </div>
      </div>
      {item.founder_name && (
        <p className="collab-founder">
          <span>{item.kind === 'freelancer' ? 'Freelancer' : 'Founder'}</span> {item.founder_name}
        </p>
      )}
      {item.goals && <p className="collab-goals">{item.goals}</p>}
      <a
        className="collab-link"
        href={item.website_url}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={`Visit ${item.name} (opens in a new tab)`}
      >
        Visit website <span aria-hidden="true">↗</span>
      </a>
    </motion.article>
  );
}

export default function Collaborators() {
  usePageMeta('Collaborators | Unitary X');
  const { collaborators, loading, error } = useCollaborators();
  const [filter, setFilter] = useState('all');

  const counts = {
    all: collaborators.length,
    startup: collaborators.filter((c) => c.kind === 'startup').length,
    freelancer: collaborators.filter((c) => c.kind === 'freelancer').length,
  };
  const visible = filter === 'all' ? collaborators : collaborators.filter((c) => c.kind === filter);

  return (
    <>
      <NavBar />
      <main className="collab-page">
        <header className="collab-intro">
          <span className="eyebrow">Collaborators</span>
          <h1 className="gradient-headline collab-title-main">The teams we build alongside.</h1>
          <p className="collab-lead">
            Startups and freelancers we work with. Each card links to their own site.
          </p>
        </header>

        {counts.startup > 0 && counts.freelancer > 0 && (
          <div className="collab-filters" role="group" aria-label="Filter collaborators">
            {FILTERS.map((f) => (
              <button
                key={f.key}
                type="button"
                className={`collab-filter ${filter === f.key ? 'is-active' : ''}`}
                aria-pressed={filter === f.key}
                onClick={() => setFilter(f.key)}
              >
                {f.label} <span className="collab-filter-count">{counts[f.key]}</span>
              </button>
            ))}
          </div>
        )}

        {loading ? (
          <div className="collab-grid" aria-busy="true">
            {[0, 1, 2].map((i) => (
              <SkeletonCard key={i} className="collab-skeleton" />
            ))}
          </div>
        ) : error ? (
          <p className="collab-empty glass">We could not load collaborators right now. Please try again shortly.</p>
        ) : visible.length === 0 ? (
          <p className="collab-empty glass">
            {collaborators.length === 0 ? 'Collaborators will be listed here soon.' : 'No collaborators in this group yet.'}
          </p>
        ) : (
          <div className="collab-grid">
            {visible.map((c, i) => (
              <CollaboratorCard key={c.id} item={c} index={i} />
            ))}
          </div>
        )}
      </main>
      <Footer />
    </>
  );
}

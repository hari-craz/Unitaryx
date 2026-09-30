import { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import ProjectCard from './ProjectCard';
import SkeletonCard from '../../common/SkeletonCard';
import { useProjects } from '../../../hooks/useProjects';
import { usePrefersReducedMotion } from '../../../hooks/usePrefersReducedMotion';
import './ProjectsGrid.css';

const LABEL_OVERRIDES = { ai: 'AI' };

const searchText = (p) =>
  [p.title, p.description, p.category, ...(p.tags || []), ...(p.stack || [])].join(' ').toLowerCase();

function label(cat) {
  const key = (cat || '').toLowerCase();
  return LABEL_OVERRIDES[key] || key.charAt(0).toUpperCase() + key.slice(1);
}

export default function ProjectsGrid() {
  const { projects, loading } = useProjects();
  const reduceMotion = usePrefersReducedMotion();
  const [active, setActive] = useState('all');
  const [query, setQuery] = useState('');

  const domains = useMemo(() => {
    const set = new Set(projects.map((p) => (p.category || '').toLowerCase()).filter(Boolean));
    return ['all', ...Array.from(set)];
  }, [projects]);

  const filtered = useMemo(() => {
    const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
    return projects.filter(
      (p) =>
        (active === 'all' || (p.category || '').toLowerCase() === active) &&
        terms.every((t) => searchText(p).includes(t))
    );
  }, [projects, active, query]);

  const filtering = active !== 'all' || query.trim() !== '';
  const clearFilters = () => {
    setActive('all');
    setQuery('');
  };

  let body;
  if (loading) {
    body = (
      <div className="projects-grid">
        {Array.from({ length: 6 }).map((_, i) => (
          <SkeletonCard key={i} className="project-skeleton" />
        ))}
      </div>
    );
  } else if (!projects.length) {
    body = <p className="projects-empty">Project case studies are coming soon.</p>;
  } else {
    body = (
      <>
        {projects.length > 3 && (
          <div className="projects-search">
            <label className="visually-hidden" htmlFor="projects-search-input">
              Search projects
            </label>
            <input
              id="projects-search-input"
              type="search"
              placeholder="Search projects, e.g. Arduino or Flask"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              maxLength={60}
            />
            <span className="projects-count" role="status" aria-live="polite">
              {filtering ? `${filtered.length} of ${projects.length} projects` : `${projects.length} projects`}
            </span>
          </div>
        )}
        {domains.length > 2 && (
          <div className="projects-filter" role="tablist" aria-label="Filter projects by domain">
            {domains.map((d) => (
              <button
                key={d}
                type="button"
                role="tab"
                aria-selected={active === d}
                className={`projects-filter-tab ${active === d ? 'active' : ''}`}
                onClick={() => setActive(d)}
              >
                {d === 'all' ? 'All' : label(d)}
              </button>
            ))}
          </div>
        )}
        {filtered.length === 0 && (
          <div className="projects-no-results glass">
            <p>No projects match your search.</p>
            <button type="button" onClick={clearFilters}>
              Clear search and filters
            </button>
          </div>
        )}
        <div className="projects-grid">
          {filtered.map((project, i) => (
            <motion.div
              key={project.id}
              initial={reduceMotion ? false : { opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.2 }}
              transition={{ duration: 0.45, delay: Math.min(0.3, (i % 3) * 0.08) }}
            >
              <ProjectCard project={project} />
            </motion.div>
          ))}
        </div>
      </>
    );
  }

  return (
    <section className="projects-section" id="projects">
      <div className="section-inner">
        <span className="eyebrow">Selected work</span>
        <h2 className="gradient-headline projects-title">Projects we&apos;ve shipped</h2>
        {body}
      </div>
    </section>
  );
}

import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import NavBar from '../components/layout/NavBar';
import Footer from '../components/layout/Footer';
import MagneticButton from '../components/common/MagneticButton';
import NotFound from './NotFound';
import { getJSON } from '../lib/api';
import { usePageMeta } from '../hooks/usePageMeta';
import './ProjectPage.css';

function projectIdFromSlug(slug) {
  const match = /(?:^|-)(\d+)$/.exec(slug || '');
  return match ? match[1] : null;
}

export default function ProjectPage() {
  const { slug } = useParams();
  const id = projectIdFromSlug(slug);
  const [state, setState] = useState({ loading: true, project: null, related: [] });

  useEffect(() => {
    let cancelled = false;
    setState({ loading: true, project: null, related: [] });
    if (!id) {
      setState({ loading: false, project: null, related: [] });
      return undefined;
    }
    Promise.all([
      getJSON(`/api/projects/${id}`).catch(() => null),
      getJSON('/api/projects').catch(() => []),
    ]).then(([project, all]) => {
      if (cancelled) return;
      const related = project
        ? all.filter((p) => p.id !== project.id && p.category === project.category).slice(0, 3)
        : [];
      setState({ loading: false, project, related });
    });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const { loading, project, related } = state;
  usePageMeta(
    project
      ? `${project.title} - ${project.category.charAt(0).toUpperCase()}${project.category.slice(1)} Project | Unitary X`
      : 'Project | Unitary X',
    {
      noindex: !loading && !project,
    }
  );

  if (!loading && !project) return <NotFound />;

  return (
    <>
      <NavBar />
      <main className="project-page">
        {loading ? (
          <div className="project-page-inner glass project-page-skeleton" aria-busy="true" />
        ) : (
          <article className="project-page-inner">
            <nav className="project-breadcrumb" aria-label="Breadcrumb">
              <Link to="/">Unitary X</Link>
              <span aria-hidden="true">/</span>
              <a href="/#projects">Projects</a>
              <span aria-hidden="true">/</span>
              <span aria-current="page">{project.title}</span>
            </nav>

            <header className="project-header">
              <span className="eyebrow">{project.category}</span>
              <h1 className="gradient-headline project-title">{project.title}</h1>
              <p className="project-lead">{project.description}</p>
              <dl className="project-facts">
                {project.duration && (
                  <div>
                    <dt>Typical delivery</dt>
                    <dd>{project.duration}</dd>
                  </div>
                )}
                {project.price && (
                  <div>
                    <dt>Indicative price</dt>
                    <dd>{project.price}</dd>
                  </div>
                )}
                <div>
                  <dt>Discipline</dt>
                  <dd>{project.category}</dd>
                </div>
              </dl>
            </header>

            {project.photo_url && (
              <img
                className="project-hero-photo glass"
                src={project.photo_url}
                alt={`${project.title} - ${project.category} project by Unitary X`}
              />
            )}

            {[
              ['Problem', project.problem],
              ['Approach', project.approach],
              ['Outcome', project.outcome],
            ]
              .filter(([, text]) => text)
              .map(([label, text]) => (
                <section className="project-section" key={label}>
                  <h2>{label}</h2>
                  <p>{text}</p>
                </section>
              ))}

            {project.stack?.length > 0 && (
              <section className="project-section">
                <h2>Stack</h2>
                <ul className="project-tags" aria-label="Technology stack">
                  {project.stack.map((t) => (
                    <li key={t}>{t.trim()}</li>
                  ))}
                </ul>
              </section>
            )}

            {project.tags?.length > 0 && (
              <ul className="project-tags" aria-label="Technologies and topics">
                {project.tags.map((t) => (
                  <li key={t}>{t.trim()}</li>
                ))}
              </ul>
            )}

            <section className="project-cta glass">
              <h2>Want something similar?</h2>
              <p>Tell us your goal and timeline. We usually reply within a day.</p>
              <MagneticButton as="a" href="/#contact">
                Start a project
              </MagneticButton>
            </section>

            {related.length > 0 && (
              <section className="project-related" aria-labelledby="related-heading">
                <h2 id="related-heading">More {project.category} projects</h2>
                <ul>
                  {related.map((p) => (
                    <li key={p.id}>
                      <Link to={`/projects/${p.slug}`}>
                        <strong>{p.title}</strong>
                        <span>{p.duration}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </article>
        )}
      </main>
      <Footer />
    </>
  );
}

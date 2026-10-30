import { useCollaborators } from '../../hooks/useCollaborators';
import './CollaboratorsStrip.css';

const MAX_SHOWN = 8;

// Short logo strip that links to the full /collaborators page. Renders nothing
// until at least one collaborator is published, so an empty list leaves no gap.
export default function CollaboratorsStrip() {
  const { collaborators } = useCollaborators();
  if (collaborators.length === 0) return null;

  const shown = collaborators.slice(0, MAX_SHOWN);
  const extra = collaborators.length - shown.length;

  return (
    <section className="collab-strip" id="collaborators" aria-labelledby="collab-strip-title">
      <div className="section-inner">
        <span className="eyebrow">Collaborators</span>
        <h2 className="collab-strip-title" id="collab-strip-title">
          Startups and freelancers we build with.
        </h2>
        <ul className="collab-strip-list">
          {shown.map((c) => (
            <li key={c.id}>
              <a className="collab-strip-item glass" href="/collaborators" aria-label={`${c.name} — see collaborators`}>
                {c.logo_url ? (
                  <img src={c.logo_url} alt="" loading="lazy" />
                ) : (
                  <span className="collab-strip-initial" aria-hidden="true">
                    {c.name.charAt(0).toUpperCase()}
                  </span>
                )}
                <span className="collab-strip-name">{c.name}</span>
              </a>
            </li>
          ))}
        </ul>
        <a className="collab-strip-more" href="/collaborators">
          {extra > 0 ? `See all ${collaborators.length} collaborators` : 'See all collaborators'} →
        </a>
      </div>
    </section>
  );
}

import { useRef } from 'react';
import { Link } from 'react-router-dom';
import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion';
import { usePrefersReducedMotion } from '../../../hooks/usePrefersReducedMotion';
import './ProjectCard.css';

const MAX_TILT = 6;

export default function ProjectCard({ project }) {
  const reduceMotion = usePrefersReducedMotion();
  const ref = useRef(null);
  const rotateX = useMotionValue(0);
  const rotateY = useMotionValue(0);
  const springX = useSpring(rotateX, { stiffness: 200, damping: 20 });
  const springY = useSpring(rotateY, { stiffness: 200, damping: 20 });
  const sweepX = useTransform(rotateY, [-MAX_TILT, MAX_TILT], ['0%', '100%']);

  const handleMove = (e) => {
    if (reduceMotion || !ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const px = (e.clientX - rect.left) / rect.width - 0.5;
    const py = (e.clientY - rect.top) / rect.height - 0.5;
    rotateY.set(px * MAX_TILT * 2);
    rotateX.set(-py * MAX_TILT * 2);
  };

  const reset = () => {
    rotateX.set(0);
    rotateY.set(0);
  };

  return (
    <motion.article
      ref={ref}
      className="project-card glass"
      data-cursor="view"
      onMouseMove={handleMove}
      onMouseLeave={reset}
      style={reduceMotion ? undefined : { rotateX: springX, rotateY: springY, transformPerspective: 800 }}
    >
      {!reduceMotion && (
        <motion.span className="project-card-sweep" style={{ left: sweepX }} aria-hidden="true" />
      )}
      {project.photo_url && (
        <img
          className="project-card-photo"
          src={project.photo_url}
          alt={`${project.title} — ${project.category} project by Unitary X`}
          loading="lazy"
        />
      )}
      <div className="project-card-body">
        {project.featured && <span className="project-card-badge">Featured</span>}
        <span className="eyebrow">{project.category}</span>
        <h3>
          <Link className="project-card-link" to={`/projects/${project.slug}`}>
            {project.title}
          </Link>
        </h3>
        <p>{project.description}</p>
        <div className="project-card-meta">
          {project.duration && <span>{project.duration}</span>}
          {project.price && <span>{project.price}</span>}
        </div>
      </div>
    </motion.article>
  );
}

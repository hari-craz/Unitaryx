import { motion } from 'framer-motion';
import DisciplineIcon from '../common/DisciplineIcon';
import { EASE_OUT } from '../../lib/motion';
import './HeroVisual.css';

const CHIPS = [
  { icon: 'web', label: 'Web', className: 'hero-chip--top' },
  { icon: 'software', label: 'Software', className: 'hero-chip--right' },
  { icon: 'hardware', label: 'Hardware', className: 'hero-chip--bottom' },
];

// Decorative only: slow rings, a soft orb and three drifting glass chips, all
// transform/opacity so it stays on the GPU. Entrance is timed (framer); the
// endless drift is CSS, which prefers-reduced-motion switches off globally.
export default function HeroVisual({ reduceMotion }) {
  return (
    <div className="hero-visual" aria-hidden="true">
      <span className="hero-ring hero-ring--outer" />
      <span className="hero-ring hero-ring--inner" />
      <span className="hero-orb" />
      {CHIPS.map((chip, i) => (
        <motion.div
          key={chip.icon}
          className={`hero-chip ${chip.className}`}
          initial={reduceMotion ? false : { opacity: 0, scale: 0.8, y: 16 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ delay: 0.6 + i * 0.18, duration: 0.9, ease: EASE_OUT }}
        >
          <span className="hero-chip-inner glass" style={{ animationDelay: `${i * -1.7}s` }}>
            <DisciplineIcon type={chip.icon} />
            {chip.label}
          </span>
        </motion.div>
      ))}
    </div>
  );
}

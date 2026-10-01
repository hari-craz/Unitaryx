import { motion, useTransform } from 'framer-motion';
import KineticText from '../common/KineticText';
import MagneticButton from '../common/MagneticButton';
import DisciplineIcon from '../common/DisciplineIcon';
import ScrollPanel from '../layout/ScrollPanel';
import HeroVisual from './HeroVisual';
import { EASE_OUT } from '../../lib/motion';
import { usePrefersReducedMotion } from '../../hooks/usePrefersReducedMotion';
import './Hero.css';

const DISCIPLINES = [
  { icon: 'web', label: 'Web' },
  { icon: 'software', label: 'Software' },
  { icon: 'hardware', label: 'Embedded Hardware' },
];

const HIGHLIGHTS = [
  '10–15 day typical turnaround',
  '100% source code handed over',
  '7 days of post-delivery support',
];

export default function Hero() {
  const reduceMotion = usePrefersReducedMotion();

  return (
    <ScrollPanel index={1} id="hero">
      {(scrollYProgress) => (
        <HeroContent scrollYProgress={scrollYProgress} reduceMotion={reduceMotion} />
      )}
    </ScrollPanel>
  );
}

// Timed entrance (seconds after load): chips (0.1), headline words (from 0.4,
// finishing around 1.4), then subtitle, buttons and highlights, so the first screen builds up
// instead of arriving all at once or sitting empty.
const rise = (delay, reduceMotion) =>
  reduceMotion
    ? {}
    : {
        initial: { opacity: 0, y: 18 },
        animate: { opacity: 1, y: 0 },
        transition: { delay, duration: 0.8, ease: EASE_OUT },
      };

function HeroContent({ scrollYProgress, reduceMotion }) {
  // Hero holds steady while it's the only thing on screen, then eases back
  // and fades as Services starts sliding up to cover it — scroll-scrubbed,
  // not a fixed-duration exit animation.
  const scale = useTransform(scrollYProgress, [0, 0.6, 1], [1, 1, 0.92]);
  const opacity = useTransform(scrollYProgress, [0, 0.6, 1], [1, 1, 0.35]);
  const y = useTransform(scrollYProgress, [0, 0.6, 1], [0, 0, -40]);

  return (
    <motion.div
      className="panel-inner hero-inner"
      style={reduceMotion ? undefined : { scale, opacity, y }}
    >
      <HeroVisual reduceMotion={reduceMotion} />
      <div className="hero-disciplines" role="list" aria-label="What we build">
        {DISCIPLINES.map((d, i) => (
          <motion.span
            className="hero-discipline"
            role="listitem"
            key={d.icon}
            {...rise(0.1 + i * 0.1, reduceMotion)}
          >
            <DisciplineIcon type={d.icon} />
            {d.label}
          </motion.span>
        ))}
      </div>
      <KineticText
        as="h1"
        className="gradient-headline hero-title"
        text="We build the systems behind ambitious ideas."
        delay={reduceMotion ? 0 : 0.4}
      />
      <motion.p className="hero-subtitle" {...rise(1.1, reduceMotion)}>
        Unitary X is a freelance dev studio delivering production-grade web, software, and embedded
        hardware — from first prototype to shipped product.
      </motion.p>
      <motion.div className="hero-actions" {...rise(1.3, reduceMotion)}>
        <MagneticButton as="a" href="#contact">
          Start a project
        </MagneticButton>
        <a className="hero-secondary-link" href="#projects">
          See our work →
        </a>
      </motion.div>
      <ul className="hero-highlights">
        {HIGHLIGHTS.map((h, i) => (
          <motion.li key={h} {...rise(1.55 + i * 0.12, reduceMotion)}>
            {h}
          </motion.li>
        ))}
      </ul>
    </motion.div>
  );
}

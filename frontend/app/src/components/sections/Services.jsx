import { motion, useTransform } from 'framer-motion';
import ScrollPanel from '../layout/ScrollPanel';
import DisciplineIcon from '../common/DisciplineIcon';
import { usePrefersReducedMotion } from '../../hooks/usePrefersReducedMotion';
import { fadeUp, popIn, withMotion } from '../../lib/motion';
import './Services.css';

const SERVICES = [
  {
    title: 'Web',
    icon: 'web',
    description: 'Marketing sites, dashboards, and full-stack products built for speed and clarity.',
    points: ['Marketing sites', 'Dashboards', 'Full-stack products'],
    rotate: -8,
    x: -60,
    y: -20,
  },
  {
    title: 'Software',
    icon: 'software',
    description: 'Backend systems, APIs, and internal tools engineered to hold up under real load.',
    points: ['Backend systems', 'APIs', 'Internal tools'],
    rotate: 4,
    x: 40,
    y: 30,
  },
  {
    title: 'Hardware',
    icon: 'hardware',
    description: 'Embedded firmware and connected devices, from prototype board to production run.',
    points: ['Embedded firmware', 'Connected devices', 'Prototype to production'],
    rotate: -3,
    x: -20,
    y: 50,
  },
];

export default function Services() {
  const reduceMotion = usePrefersReducedMotion();

  return (
    <ScrollPanel index={2} id="services" className="services-panel" wrapperClassName="services-panel-wrapper">
      {(scrollYProgress) => (
        <div className="panel-inner services-inner">
          <motion.span className="eyebrow" variants={withMotion(fadeUp, reduceMotion)} custom={0}>
            What we do
          </motion.span>
          <motion.h2
            className="gradient-headline services-title"
            variants={withMotion(fadeUp, reduceMotion)}
            custom={0.12}
          >
            Three disciplines, one delivery.
          </motion.h2>
          <div className="services-stack">
            {SERVICES.map((service, i) => (
              <ServiceCard
                key={service.title}
                service={service}
                index={i}
                scrollYProgress={scrollYProgress}
                reduceMotion={reduceMotion}
              />
            ))}
          </div>
        </div>
      )}
    </ScrollPanel>
  );
}

function ServiceCard({ service, index, scrollYProgress, reduceMotion }) {
  // The signature moment (CLAUDE.md §6): three scattered cards fly together
  // into an overlapping stack. Scroll-scrubbed across the panel's first half
  // so the assembly literally completes as you scroll, not on first view —
  // each card starts assembling at a slightly staggered progress point.
  const start = 0.05 + index * 0.08;
  const end = start + 0.35;
  const range = [start, end];

  const x = useTransform(scrollYProgress, range, [service.x, 0]);
  const y = useTransform(scrollYProgress, range, [service.y, 0]);
  const rotate = useTransform(scrollYProgress, range, [service.rotate, 0]);

  // Position and rotation stay scroll-scrubbed (the assembly), but opacity and
  // scale play on a timer once the panel arrives, so the cards are never an
  // empty panel waiting for the user to scroll.
  return (
    <motion.div
      className="services-card glass"
      variants={withMotion(popIn, reduceMotion)}
      custom={0.3 + index * 0.16}
      style={{
        '--stack-offset': index,
        ...(reduceMotion ? {} : { x, y, rotate }),
      }}
    >
      <DisciplineIcon type={service.icon} className="services-card-icon" />
      <h3>{service.title}</h3>
      <p>{service.description}</p>
      <ul className="services-card-points">
        {service.points.map((point) => (
          <li key={point}>{point}</li>
        ))}
      </ul>
    </motion.div>
  );
}

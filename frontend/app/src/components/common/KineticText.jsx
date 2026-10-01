import { motion } from 'framer-motion';
import { usePrefersReducedMotion } from '../../hooks/usePrefersReducedMotion';

const word = {
  hidden: { clipPath: 'inset(0 100% 0 0)', opacity: 0 },
  visible: {
    clipPath: 'inset(0 0% 0 0)',
    opacity: 1,
    transition: { duration: 0.6, ease: [0.16, 1, 0.3, 1] },
  },
};

// `delay` (seconds) postpones the whole word-by-word reveal, so a caller can
// slot the headline into a timed sequence.
export default function KineticText({ as: Tag = 'h1', text, className = '', delay = 0 }) {
  const reduceMotion = usePrefersReducedMotion();
  const words = text.split(' ');

  if (reduceMotion) {
    return <Tag className={className}>{text}</Tag>;
  }

  const MotionTag = motion[Tag] || motion.span;
  const container = {
    hidden: {},
    visible: { transition: { staggerChildren: 0.06, delayChildren: delay } },
  };

  return (
    <MotionTag className={className} variants={container} initial="hidden" animate="visible">
      {words.map((w, i) => (
        <motion.span key={i} variants={word} style={{ display: 'inline-block' }}>
          {w}
          {i < words.length - 1 ? ' ' : ''}
        </motion.span>
      ))}
    </MotionTag>
  );
}

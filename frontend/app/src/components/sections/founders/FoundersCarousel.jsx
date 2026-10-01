import { useMemo, useState } from 'react';
import { AnimatePresence, motion, useMotionValueEvent } from 'framer-motion';
import FounderCard from './FounderCard';
import SkeletonCard from '../../common/SkeletonCard';
import KineticText from '../../common/KineticText';
import ScrollPanel from '../../layout/ScrollPanel';
import { useFounders } from '../../../hooks/useFounders';
import { usePrefersReducedMotion } from '../../../hooks/usePrefersReducedMotion';
import { fadeUp, withMotion } from '../../../lib/motion';
import './FoundersCarousel.css';

const GROUP_SIZE = 3;
const OFFSET_X = 230;
const VH_PER_MEMBER = 65; // extra scroll runway per team member — the whole
// point of this panel: scrolling further is what advances the story.
const BASE_VH = 100;

function shortestDistance(index, active, count) {
  const raw = index - active;
  const wrapped = ((raw % count) + count) % count;
  return wrapped > count / 2 ? wrapped - count : wrapped;
}

function cardStyle(distance) {
  const abs = Math.abs(distance);
  if (abs > 2) {
    return { transform: `translate(-50%, -50%) translateX(${distance * OFFSET_X}px) scale(0.6)`, opacity: 0, zIndex: 0 };
  }
  return {
    transform: `translate(-50%, -50%) translateX(${distance * OFFSET_X}px) scale(${1 - abs * 0.18})`,
    filter: `blur(${abs * 2.5}px) brightness(${1 - abs * 0.15})`,
    opacity: 1 - abs * 0.35,
    zIndex: 10 - abs,
  };
}

// Jumps the page's scroll position to the point in the founders panel's
// runway that makes `index` the active member — dots/arrows stay usable
// without introducing a second source of truth for "which founder is active".
function scrollToFounderIndex(index, count) {
  const wrapper = document.getElementById('founders')?.parentElement;
  if (!wrapper || !count) return;
  const rect = wrapper.getBoundingClientRect();
  const wrapperTop = window.scrollY + rect.top;
  const runway = wrapper.offsetHeight - window.innerHeight;
  if (runway <= 0) return;
  const progress = (index + 0.5) / count;
  const targetY = wrapperTop + progress * runway;
  window.scrollTo({ top: targetY, behavior: 'smooth' });
}

export default function FoundersCarousel() {
  const { founders, loading } = useFounders();
  const reduceMotion = usePrefersReducedMotion();
  const count = founders.length;

  // Extra scroll room is only meaningful once there's more than one member
  // to scroll through, and pointless under reduced motion (panel collapses
  // to normal flow anyway).
  const useScrollRunway = !reduceMotion && count > 1;
  const heightVh = useScrollRunway ? BASE_VH + count * VH_PER_MEMBER : undefined;
  const mobileHeightVh = useScrollRunway ? BASE_VH + count * (VH_PER_MEMBER - 15) : undefined;

  return (
    <ScrollPanel index={3} id="founders" heightVh={heightVh} mobileHeightVh={mobileHeightVh}>
      {(scrollYProgress) => (
        <FoundersContent
          founders={founders}
          loading={loading}
          reduceMotion={reduceMotion}
          scrollYProgress={scrollYProgress}
          driveFromScroll={useScrollRunway}
        />
      )}
    </ScrollPanel>
  );
}

function FoundersContent({ founders, loading, reduceMotion, scrollYProgress, driveFromScroll }) {
  const count = founders.length;
  const [activeIndex, setActiveIndex] = useState(0);

  useMotionValueEvent(scrollYProgress, 'change', (v) => {
    if (!driveFromScroll || !count) return;
    setActiveIndex(Math.min(count - 1, Math.max(0, Math.floor(v * count))));
  });

  const groups = useMemo(() => {
    const total = Math.ceil(count / GROUP_SIZE) || 1;
    return Array.from({ length: total }, (_, g) => g * GROUP_SIZE);
  }, [count]);

  const activeGroup = Math.floor(activeIndex / GROUP_SIZE);
  const active = founders[activeIndex];
  const activeSocials = active ? Object.entries(active.socials || {}).filter(([, url]) => url) : [];

  const goTo = (index) => {
    const next = ((index % count) + count) % count;
    if (driveFromScroll) {
      scrollToFounderIndex(next, count);
    } else {
      setActiveIndex(next);
    }
  };

  if (loading) {
    return (
      <div className="panel-inner founders-panel-inner">
        <span className="eyebrow">The team</span>
        <KineticText as="h2" className="gradient-headline founders-title" text="Meet the builders of Unitary X" />
        <div className="founders-carousel">
          <div className="founders-stage">
            <SkeletonCard className="founder-skeleton" />
          </div>
        </div>
      </div>
    );
  }

  if (!count) {
    return (
      <div className="panel-inner founders-panel-inner">
        <span className="eyebrow">The team</span>
        <KineticText as="h2" className="gradient-headline founders-title" text="Meet the builders of Unitary X" />
        <div className="founders-empty glass">
          <div className="founders-empty-slots" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
          <p>Team profiles are coming soon.</p>
          <a className="founders-empty-cta" href="#contact">
            Get in touch →
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="panel-inner founders-panel-inner">
      <motion.div className="founders-header" variants={withMotion(fadeUp, reduceMotion)} custom={0.05}>
        <div>
          <span className="eyebrow">The team</span>
          <KineticText as="h2" className="gradient-headline founders-title" text="Meet the builders of Unitary X" />
        </div>
        {driveFromScroll && <span className="founders-scroll-hint">Keep scrolling to meet the team ↓</span>}
      </motion.div>

      <motion.div className="founders-body" variants={withMotion(fadeUp, reduceMotion)} custom={0.3}>
        {/* Left info card — fills what used to be dead space beside the
            carousel, and carries the active member's full detail so the photo
            cards can stay clean. Desktop only; on mobile the card overlay
            carries these details instead (see FounderCard). */}
        <div className="founders-info">
          <AnimatePresence mode="wait">
            {active && (
              <motion.div
                key={active.id}
                initial={reduceMotion ? false : { opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                exit={reduceMotion ? undefined : { opacity: 0, y: -14 }}
                transition={{ duration: 0.35 }}
                className="founders-info-inner"
              >
                <p className="founders-info-count">
                  {String(activeIndex + 1).padStart(2, '0')} <span>/ {String(count).padStart(2, '0')}</span>
                </p>
                <h3 className="founders-info-name">{active.name}</h3>
                <p className="founders-info-role">{active.role}</p>
                {active.bio && <p className="founders-info-bio">{active.bio}</p>}
                {activeSocials.length > 0 && (
                  <div className="founders-info-socials">
                    {activeSocials.map(([label, url]) => (
                      <a key={label} href={url} target="_blank" rel="noreferrer">
                        {label}
                      </a>
                    ))}
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <div className="founders-carousel">
        <div className="founders-stage">
          {founders.map((founder, i) => {
            const distance = shortestDistance(i, activeIndex, count);
            if (Math.abs(distance) > 2) return null;
            return (
              <motion.div
                key={founder.id}
                animate={cardStyle(distance)}
                transition={reduceMotion ? { duration: 0 } : { type: 'spring', stiffness: 260, damping: 30 }}
                style={{ position: 'absolute', top: '50%', left: '50%' }}
              >
                <FounderCard founder={founder} isActive={distance === 0} />
              </motion.div>
            );
          })}
        </div>

        <div className="founders-controls">
          <button
            type="button"
            className="founders-arrow"
            aria-label="Previous team member"
            onClick={() => goTo(activeIndex - 1)}
          >
            ←
          </button>

          <div className="founders-dots" role="tablist" aria-label="Team member groups">
            <span
              className="founders-dots-underline"
              style={{ transform: `translateX(${activeGroup * 100}%)`, width: `${100 / groups.length}%` }}
            />
            {groups.map((startIndex, g) => (
              <button
                key={startIndex}
                type="button"
                role="tab"
                aria-selected={g === activeGroup}
                aria-label={`Team members ${startIndex + 1} to ${Math.min(startIndex + GROUP_SIZE, count)}`}
                className={`founders-dot ${g === activeGroup ? 'active' : ''}`}
                onClick={() => goTo(startIndex)}
              />
            ))}
          </div>

          <button
            type="button"
            className="founders-arrow"
            aria-label="Next team member"
            onClick={() => goTo(activeIndex + 1)}
          >
            →
          </button>
        </div>
        </div>
      </motion.div>
    </div>
  );
}

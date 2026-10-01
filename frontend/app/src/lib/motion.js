// Shared entrance timing. The pinned panels (ScrollPanel) pass hidden/visible
// variant labels down to their children, so a child that declares these variants
// plays them on a timer once its panel scrolls into view, regardless of how fast
// the user scrolls afterwards. `custom` is the delay in seconds.
export const EASE_OUT = [0.16, 1, 0.3, 1];

export const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  visible: (delay = 0) => ({
    opacity: 1,
    y: 0,
    transition: { delay, duration: 0.75, ease: EASE_OUT },
  }),
};

export const popIn = {
  hidden: { opacity: 0, scale: 0.94 },
  visible: (delay = 0) => ({
    opacity: 1,
    scale: 1,
    transition: { delay, type: 'spring', stiffness: 140, damping: 20 },
  }),
};

// Returns the variants only when motion is allowed, so reduced-motion users get
// the final state immediately.
export const withMotion = (variants, reduceMotion) => (reduceMotion ? undefined : variants);

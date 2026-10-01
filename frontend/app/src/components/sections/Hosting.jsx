import { motion } from 'framer-motion';
import MagneticButton from '../common/MagneticButton';
import { usePrefersReducedMotion } from '../../hooks/usePrefersReducedMotion';
import './Hosting.css';

const MADE_FOR = ['Static sites', 'Docker apps', 'APIs'];

const WAYS = [
  {
    n: '01',
    label: 'Static websites',
    title: 'Fast, clean, ready to share.',
    detail: 'HTML · CSS · JavaScript · Vite · React / Vue static builds',
  },
  {
    n: '02',
    label: 'Dockerized apps',
    title: 'Built to run in containers.',
    detail: 'Web apps · APIs · backends · SaaS · Docker Compose projects',
  },
  {
    n: '03',
    label: 'Deployment ready',
    title: 'The essentials, handled.',
    detail: 'Free SSL · Nginx reverse proxy · custom domains · support',
  },
];

export const PLANS = [
  {
    key: 'starter',
    name: 'Starter',
    price: '₹99',
    suffix: '/ month',
    for: 'For personal projects & learning',
    features: ['Static website hosting', 'Dockerized app hosting', 'Free SSL', 'Nginx reverse proxy', 'Basic support'],
  },
  {
    key: 'developer',
    name: 'Developer',
    price: '₹249',
    suffix: '/ month',
    for: 'For developers & small projects',
    features: [
      'Static sites & Docker apps',
      'Free SSL + custom domain',
      'Docker deployment support',
      'Application assistance',
      'Technical support',
    ],
  },
  {
    key: 'business',
    name: 'Business',
    price: '₹499',
    suffix: '/ month',
    for: 'For startups & growing projects',
    features: [
      'Websites & Docker apps',
      'Docker deployment & management',
      'Git / GitHub deployment support',
      'Monitoring & backup options',
      'Priority support',
    ],
  },
  {
    key: 'custom',
    name: 'Custom',
    price: '₹999+',
    suffix: '/ month',
    for: 'For specialized deployments',
    features: [
      'Custom Docker infrastructure',
      'Multiple applications',
      'Compose / Swarm support',
      'CI/CD & GitHub integration',
      'Uptime alerts & dedicated support',
    ],
  },
];

const SERVICES = [
  { n: '01', title: 'Deploy your application', detail: 'Docker image · Docker Compose · GitHub-based deployment' },
  { n: '02', title: 'Connect and secure it', detail: 'Reverse proxy · SSL setup · custom domain configuration' },
  { n: '03', title: 'Keep it running well', detail: 'Container monitoring · troubleshooting · backup options' },
];

export const ADD_ONS = [
  { label: 'Backup', value: '₹50/mo' },
  { label: 'Custom deployment', value: '₹199' },
  { label: 'Advanced setup', value: 'Custom quote' },
];

const WHY = [
  'Affordable, transparent pricing',
  'Docker-first, developer-focused support',
  'Secure deployment with SSL and reverse proxy',
];

export default function Hosting() {
  const reduceMotion = usePrefersReducedMotion();
  const reveal = (i = 0) =>
    reduceMotion
      ? {}
      : {
          initial: { opacity: 0, y: 20 },
          whileInView: { opacity: 1, y: 0 },
          viewport: { once: true, amount: 0.25 },
          transition: { delay: Math.min(i * 0.05, 0.25), type: 'spring', stiffness: 200, damping: 24 },
        };

  return (
    <section className="hosting-section" id="hosting" aria-labelledby="hosting-title">
      <div className="section-inner">
        <span className="eyebrow">Unitary X Hosting</span>
        <h2 className="gradient-headline hosting-title" id="hosting-title">
          Host your next big idea.
        </h2>
        <p className="hosting-lead">
          Affordable, secure hosting for static sites and Dockerized applications, with real people to help you
          get from code to a live URL.
        </p>
        <div className="hosting-from">
          <span className="hosting-from-label">Hosting from</span>
          <span className="hosting-from-price">₹99 / month</span>
          <ul className="hosting-made-for" aria-label="Made for">
            {MADE_FOR.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>

        <h3 className="hosting-subhead">One platform. Three ways to ship.</h3>
        <ol className="hosting-ways">
          {WAYS.map((w, i) => (
            <motion.li className="hosting-way glass" key={w.n} {...reveal(i)}>
              <span className="hosting-way-label">
                {w.n} / {w.label}
              </span>
              <strong>{w.title}</strong>
              <span className="hosting-way-detail">{w.detail}</span>
            </motion.li>
          ))}
        </ol>

        <div className="hosting-plans-head">
          <h3 className="hosting-subhead">Hosting plans</h3>
          <span className="hosting-ssl">Every plan includes SSL</span>
        </div>
        <div className="hosting-plans">
          {PLANS.map((p, i) => (
            <motion.article className="hosting-plan glass" key={p.key} {...reveal(i)}>
              <h4 className="hosting-plan-name">{p.name}</h4>
              <p className="hosting-plan-price">
                <span>{p.price}</span> {p.suffix}
              </p>
              <p className="hosting-plan-for">{p.for}</p>
              <ul>
                {p.features.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
            </motion.article>
          ))}
        </div>

        <h3 className="hosting-subhead">More than just a server.</h3>
        <ol className="hosting-services">
          {SERVICES.map((s) => (
            <li key={s.n}>
              <span className="hosting-service-n">{s.n}</span>
              <div>
                <strong>{s.title}</strong>
                <span>{s.detail}</span>
              </div>
            </li>
          ))}
        </ol>
        <div className="hosting-addons" role="group" aria-label="Available add-ons">
          <span className="hosting-addons-label">Available add-ons</span>
          <ul>
            {ADD_ONS.map((a) => (
              <li key={a.label}>
                {a.label} <strong>{a.value}</strong>
              </li>
            ))}
          </ul>
        </div>

        <div className="hosting-cta glass-strong">
          <div>
            <span className="eyebrow">Ready to make it live?</span>
            <h3>Send us your project.</h3>
            <p>
              Message us with &ldquo;Hosting&rdquo; and tell us what you&apos;re building. We&apos;ll help you choose the
              setup that fits it.
            </p>
            <ul className="hosting-why">
              {WHY.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </div>
          <div className="hosting-cta-actions">
            <MagneticButton
              as="a"
              href="https://instagram.com/unitaryx__official"
              target="_blank"
              rel="noreferrer"
            >
              Message us on Instagram
            </MagneticButton>
            <a className="hosting-call" href="tel:+919363734565">
              Or call +91 93637 34565
            </a>
          </div>
        </div>

        <p className="hosting-terms">
          Static websites and Dockerized applications only. <a href="/terms">T&amp;Cs apply.</a>
        </p>
      </div>
    </section>
  );
}

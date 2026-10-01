import NewsletterSignup from './NewsletterSignup';
import './Footer.css';

const COLUMNS = [
  {
    heading: 'Studio',
    links: [
      { href: '/#services', label: 'Services' },
      { href: '/#founders', label: 'Team' },
      { href: '/#projects', label: 'Work' },
      { href: '/#hosting', label: 'Hosting' },
      { href: '/#about', label: 'About' },
    ],
  },
  {
    heading: 'Account',
    links: [
      { href: '/login', label: 'Log in' },
      { href: '/#faq', label: 'FAQ' },
      { href: '/#contact', label: 'Start a project' },
      { href: '/privacy', label: 'Privacy' },
      { href: '/terms', label: 'Terms' },
    ],
  },
];

export default function Footer() {
  const year = new Date().getFullYear();
  return (
    <footer className="site-footer">
      <div className="footer-inner">
        <div className="footer-brand">
          <p className="footer-logo">
            UNITARY <span>X</span>
          </p>
          <p className="footer-tagline">
            A freelance dev studio building web, software, and embedded hardware — from first
            prototype to shipped product.
          </p>
        </div>

        {COLUMNS.map((col) => (
          <div className="footer-col" key={col.heading}>
            <p className="footer-col-heading">{col.heading}</p>
            <ul>
              {col.links.map((l) => (
                <li key={l.href}>
                  <a href={l.href}>{l.label}</a>
                </li>
              ))}
            </ul>
          </div>
        ))}

        <div className="footer-col">
          <p className="footer-col-heading">Contact</p>
          <ul>
            <li>
              <a href="mailto:xunitary@gmail.com">xunitary@gmail.com</a>
            </li>
            <li>
              <a href="tel:+919363734565">+91 93637 34565</a>
            </li>
            <li>
              <a href="https://instagram.com/unitaryx__official" target="_blank" rel="noreferrer">
                @unitaryx__official
              </a>
            </li>
          </ul>
        </div>
      </div>

      <div className="footer-newsletter">
        <NewsletterSignup />
      </div>

      <div className="footer-bottom">
        <p>© {year} Unitary X. All rights reserved.</p>
      </div>
    </footer>
  );
}

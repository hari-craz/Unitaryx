import { useEffect, useState } from 'react';
import { getJSON, postJSON } from '../../lib/api';
import MagneticButton from '../common/MagneticButton';
import './NavBar.css';

async function logout() {
  try {
    await postJSON('/api/auth/logout', {});
  } catch {
    // Even if the request fails, fall through to a full reload so the UI
    // reflects the intended signed-out state.
  }
  window.location.href = '/';
}

const LINKS = [
  { href: '/#services', label: 'Services' },
  { href: '/#founders', label: 'Team' },
  { href: '/#projects', label: 'Work' },
  { href: '/#hosting', label: 'Hosting' },
  { href: '/#about', label: 'About' },
  { href: '/#faq', label: 'FAQ' },
  { href: '/#contact', label: 'Contact' },
];

export default function NavBar() {
  const [session, setSession] = useState({ loading: true, authenticated: false, user: null });
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    getJSON('/api/auth/session')
      .then((data) => setSession({ loading: false, authenticated: data.authenticated, user: data.user }))
      .catch(() => setSession({ loading: false, authenticated: false, user: null }));
  }, []);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const closeMenu = () => setOpen(false);

  let authAction = (
    <a className="nav-cta" href="/login">
      Log in
    </a>
  );
  if (!session.loading && session.authenticated) {
    const isAdmin = session.user?.role === 'admin';
    authAction = (
      <>
        <a className="nav-cta" href={isAdmin ? '/admin/studio' : '/dashboard'}>
          {isAdmin ? 'Studio' : 'Dashboard'}
        </a>
        <button type="button" className="nav-cta nav-cta--ghost" onClick={logout}>
          Log out
        </button>
      </>
    );
  }

  return (
    <header className={`navbar ${scrolled ? 'navbar--scrolled' : ''}`}>
      <div className="navbar-inner glass">
        <a className="nav-logo" href="/">
          UNITARY <span>X</span>
        </a>

        <nav className="nav-links" aria-label="Primary">
          {LINKS.map((l) => (
            <a key={l.href} href={l.href}>
              {l.label}
            </a>
          ))}
        </nav>

        <div className="nav-actions">
          <MagneticButton as="a" href="/#contact" className="nav-primary-cta">
            Start a project
          </MagneticButton>
          {authAction}
          <button
            type="button"
            className="nav-toggle"
            aria-label="Toggle menu"
            aria-expanded={open}
            onClick={() => setOpen((o) => !o)}
          >
            <span />
            <span />
            <span />
          </button>
        </div>
      </div>

      {open && (
        <div className="nav-mobile glass-strong">
          {LINKS.map((l) => (
            <a key={l.href} href={l.href} onClick={closeMenu}>
              {l.label}
            </a>
          ))}
          <a href={session.authenticated ? (session.user?.role === 'admin' ? '/admin/studio' : '/dashboard') : '/login'} onClick={closeMenu}>
            {session.authenticated ? (session.user?.role === 'admin' ? 'Studio' : 'Dashboard') : 'Log in'}
          </a>
          {session.authenticated && (
            <button
              type="button"
              className="nav-mobile-logout"
              onClick={() => {
                closeMenu();
                logout();
              }}
            >
              Log out
            </button>
          )}
        </div>
      )}
    </header>
  );
}

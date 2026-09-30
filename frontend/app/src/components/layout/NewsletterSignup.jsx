import { useState } from 'react';
import { postJSON } from '../../lib/api';
import './NewsletterSignup.css';

export default function NewsletterSignup() {
  const [email, setEmail] = useState('');
  const [website, setWebsite] = useState('');
  const [state, setState] = useState({ status: 'idle', message: '' });

  const submit = async (e) => {
    e.preventDefault();
    setState({ status: 'sending', message: '' });
    try {
      const res = await postJSON('/api/newsletter/subscribe', { email, website });
      setState({ status: 'done', message: res.message });
      setEmail('');
    } catch (err) {
      setState({ status: 'error', message: err.message || 'Something went wrong. Please try again.' });
    }
  };

  return (
    <form className="newsletter" onSubmit={submit} aria-labelledby="newsletter-heading">
      <p className="footer-col-heading" id="newsletter-heading">
        Occasional updates
      </p>
      <div className="newsletter-row">
        <label className="visually-hidden" htmlFor="newsletter-email">
          Email address
        </label>
        <input
          id="newsletter-email"
          type="email"
          required
          maxLength={150}
          autoComplete="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        {/* Honeypot: hidden from people and assistive tech, bots tend to fill it. */}
        <input
          className="newsletter-hp"
          type="text"
          name="website"
          tabIndex={-1}
          autoComplete="off"
          aria-hidden="true"
          value={website}
          onChange={(e) => setWebsite(e.target.value)}
        />
        <button type="submit" disabled={state.status === 'sending'}>
          {state.status === 'sending' ? 'Sending…' : 'Subscribe'}
        </button>
      </div>
      <p className="newsletter-note">
        We email occasionally about new work. Confirm by email; unsubscribe any time.
      </p>
      {state.message && (
        <p
          className={`newsletter-status ${state.status === 'error' ? 'is-error' : 'is-ok'}`}
          role={state.status === 'error' ? 'alert' : 'status'}
        >
          {state.message}
        </p>
      )}
    </form>
  );
}

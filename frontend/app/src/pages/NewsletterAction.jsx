import { useState } from 'react';
import { useParams } from 'react-router-dom';
import NavBar from '../components/layout/NavBar';
import Footer from '../components/layout/Footer';
import MagneticButton from '../components/common/MagneticButton';
import { postJSON } from '../lib/api';
import { usePageMeta } from '../hooks/usePageMeta';
import './NotFound.css';

const COPY = {
  confirm: {
    title: 'Confirm your subscription',
    lead: 'Press the button to start receiving occasional updates from Unitary X.',
    button: 'Confirm subscription',
    endpoint: '/api/newsletter/confirm',
  },
  unsubscribe: {
    title: 'Unsubscribe',
    lead: 'Press the button to stop receiving updates from Unitary X. Your address is removed immediately.',
    button: 'Unsubscribe',
    endpoint: '/api/newsletter/unsubscribe',
  },
};

// The action is a button (POST), never a GET, so mail scanners that prefetch
// links cannot subscribe or unsubscribe anyone by accident.
export default function NewsletterAction({ mode }) {
  const { token } = useParams();
  const copy = COPY[mode];
  const [state, setState] = useState({ status: 'idle', message: '' });
  usePageMeta(`${copy.title} — Unitary X`, { noindex: true });

  const run = async () => {
    setState({ status: 'working', message: '' });
    try {
      const res = await postJSON(copy.endpoint, { token });
      setState({ status: 'done', message: res.message });
    } catch (err) {
      setState({ status: 'error', message: err.message || 'Something went wrong. Please try again.' });
    }
  };

  return (
    <>
      <NavBar />
      <main className="not-found-shell">
        <div className="not-found-inner glass">
          <span className="eyebrow">Newsletter</span>
          <h1>{copy.title}</h1>
          {state.status === 'done' ? (
            <p role="status">{state.message}</p>
          ) : (
            <>
              <p>{copy.lead}</p>
              <MagneticButton type="button" onClick={run} disabled={state.status === 'working'}>
                {state.status === 'working' ? 'Working…' : copy.button}
              </MagneticButton>
              {state.status === 'error' && <p role="alert">{state.message}</p>}
            </>
          )}
          <a href="/">Back to homepage</a>
        </div>
      </main>
      <Footer />
    </>
  );
}

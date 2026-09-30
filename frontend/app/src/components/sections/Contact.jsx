import { useEffect, useState } from 'react';
import MagneticButton from '../common/MagneticButton';
import { apiFetch, getJSON } from '../../lib/api';
import './Contact.css';

const SERVICES = ['web', 'software', 'hardware', 'hosting'];

const CHANNELS = [
  { label: 'Phone', value: '+91 93637 34565', href: 'tel:+919363734565' },
  { label: 'Email', value: 'xunitary@gmail.com', href: 'mailto:xunitary@gmail.com' },
  { label: 'Instagram', value: '@unitaryx__official', href: 'https://instagram.com/unitaryx__official' },
];

const INITIAL_FORM = { name: '', email: '', phone: '', service: '', deadline: '', message: '', website: '' };

export default function Contact() {
  const [session, setSession] = useState({ loading: true, authenticated: false });
  const [form, setForm] = useState(INITIAL_FORM);
  const [status, setStatus] = useState({ state: 'idle', message: '', errors: {} });

  useEffect(() => {
    getJSON('/api/auth/session')
      .then((data) => {
        setSession({ loading: false, authenticated: data.authenticated });
        if (data.authenticated && data.user) {
          setForm((f) => ({ ...f, name: f.name || data.user.name || '', email: f.email || data.user.email || '' }));
        }
      })
      .catch(() => setSession({ loading: false, authenticated: false }));
  }, []);

  const update = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setStatus({ state: 'submitting', message: '', errors: {} });
    try {
      const data = await apiFetch('/api/contact', { method: 'POST', body: JSON.stringify(form) });
      if (data.success) {
        setStatus({ state: 'success', message: data.message, errors: {} });
        setForm(session.authenticated ? { ...INITIAL_FORM, name: form.name, email: form.email } : INITIAL_FORM);
      }
    } catch (err) {
      const errors = err.errors || {};
      setStatus({ state: 'error', message: err.message || 'Something went wrong.', errors });
    }
  };

  return (
    <section className="contact-section" id="contact">
      <div className="section-inner contact-inner">
        <div className="contact-intro">
          <span className="eyebrow">Start a project</span>
          <h2 className="gradient-headline contact-title">Tell us what you're building.</h2>
          <p className="contact-lead">
            Share your goal and timeline — the fastest way to begin. We usually reply within a day.
          </p>
          <ul className="contact-channels">
            {CHANNELS.map((c) => (
              <li key={c.label}>
                <span className="contact-channel-label">{c.label}</span>
                <a href={c.href} target={c.href.startsWith('http') ? '_blank' : undefined} rel="noreferrer">
                  {c.value}
                </a>
              </li>
            ))}
          </ul>
        </div>

        <div className="contact-form-col">
          <form className="contact-form glass" onSubmit={submit}>
            <div className="contact-field-row">
              <label>
                Name
                <input value={form.name} onChange={update('name')} required maxLength={100} autoComplete="name" />
                {status.errors.name && <span className="field-error">{status.errors.name}</span>}
              </label>
              <label>
                Email
                <input type="email" value={form.email} onChange={update('email')} required maxLength={150} autoComplete="email" />
                {status.errors.email && <span className="field-error">{status.errors.email}</span>}
              </label>
            </div>
            <div className="contact-field-row">
              <label>
                Phone
                <input value={form.phone} onChange={update('phone')} maxLength={20} autoComplete="tel" />
              </label>
              <label>
                Service
                <select value={form.service} onChange={update('service')} required>
                  <option value="">Select…</option>
                  {SERVICES.map((s) => (
                    <option key={s} value={s}>
                      {s[0].toUpperCase() + s.slice(1)}
                    </option>
                  ))}
                </select>
                {status.errors.service && <span className="field-error">{status.errors.service}</span>}
              </label>
            </div>
            <label>
              Target deadline
              <input value={form.deadline} onChange={update('deadline')} placeholder="e.g. 6 weeks" maxLength={30} />
            </label>
            <label>
              Project details
              <textarea rows={4} value={form.message} onChange={update('message')} required minLength={20} maxLength={3000} />
              {status.errors.message && <span className="field-error">{status.errors.message}</span>}
            </label>

            <input
              className="contact-hp"
              type="text"
              name="website"
              tabIndex={-1}
              autoComplete="off"
              aria-hidden="true"
              value={form.website}
              onChange={update('website')}
            />

            {!session.loading && !session.authenticated && (
              <p className="contact-note">
                No account needed. <a href="/login">Log in</a> if you would like to track this request on your dashboard.
              </p>
            )}

            <MagneticButton type="submit" disabled={status.state === 'submitting'}>
              {status.state === 'submitting' ? 'Sending…' : 'Send request'}
            </MagneticButton>

            {status.state === 'success' && <p className="contact-status contact-status--ok">{status.message}</p>}
            {status.state === 'error' && !Object.keys(status.errors).length && (
              <p className="contact-status contact-status--error">{status.message}</p>
            )}
          </form>
        </div>
      </div>
    </section>
  );
}

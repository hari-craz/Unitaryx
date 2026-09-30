import NavBar from '../components/layout/NavBar';
import Footer from '../components/layout/Footer';
import { usePageMeta } from '../hooks/usePageMeta';
import './Privacy.css';

const UPDATED = '30 September 2026';

export default function Privacy() {
  usePageMeta('Privacy notice | Unitary X');

  return (
    <>
      <NavBar />
      <main className="privacy-page">
        <article className="privacy-inner">
          <header>
            <span className="eyebrow">Privacy notice</span>
            <h1 className="gradient-headline privacy-title">How we handle your data.</h1>
            <p className="privacy-updated">Last updated {UPDATED}</p>
            <p className="privacy-lead">
              Unitary X is a freelance dev studio. This page explains what personal data this website collects, why,
              and what you can do about it. We collect only what the features below need.
            </p>
          </header>

          <section>
            <h2>What we collect, and why</h2>
            <dl>
              <dt>Project requests</dt>
              <dd>
                When you send a request through the contact form we store your name, email, phone number (optional),
                the service you are interested in, your deadline and your message. We use it to reply to you and to
                scope the work. It is visible to the Unitary X team and is emailed to us as a notification.
              </dd>

              <dt>Accounts</dt>
              <dd>
                If you create an account we store your name and email address, and a hash of your password (never the
                password itself). If you sign in with Google we receive your name, email address and profile photo
                from Google. We use this to sign you in, show your requests on your dashboard and let you post
                feedback.
              </dd>

              <dt>Public feedback</dt>
              <dd>
                Feedback you post (your name, rating and message) is shown publicly on the homepage. Do not include
                anything you do not want others to read.
              </dd>

              <dt>Newsletter</dt>
              <dd>
                If you subscribe we store your email address and send one confirmation email. You only receive updates
                after you confirm, and every message has an unsubscribe link. Unsubscribing deletes your address from
                the list.
              </dd>

              <dt>Sign-in page usage data</dt>
              <dd>
                On our sign-in page we record anonymous usage events: the page visited, how far you scrolled, the page
                you came from, your IP address, your browser and device description, and a random visitor ID kept in
                your browser&apos;s local storage (plus your email if you are signed in). We use it to understand how
                the site is used and to keep it secure. The rest of the public website does not run this tracking.
              </dd>
            </dl>
          </section>

          <section>
            <h2>Cookies</h2>
            <p>
              We use a session cookie that keeps you signed in and a security cookie that protects forms against
              forged requests. We do not use advertising or cross-site tracking cookies.
            </p>
          </section>

          <section>
            <h2>Who else handles your data</h2>
            <ul>
              <li>
                <strong>Cloudflare</strong> sits in front of the website and sees traffic in order to deliver and
                protect it.
              </li>
              <li>
                <strong>Google</strong> processes sign-in if you choose Google sign-in, and the sign-in page loads
                fonts from Google, which means Google receives your IP address when that page loads.
              </li>
              <li>
                <strong>Gmail (SMTP)</strong> is used to send our emails, such as confirmations, password-reset codes
                and notifications.
              </li>
              <li>Our servers and database are operated by Unitary X.</li>
            </ul>
            <p>We do not sell your personal data.</p>
          </section>

          <section>
            <h2>How long we keep it</h2>
            <p>
              We keep data for as long as it is needed for the purposes above. You can ask us to delete it sooner (see
              below).
            </p>
          </section>

          <section>
            <h2>Your choices</h2>
            <p>
              You can ask us for a copy of your data, to correct it, or to delete it, and you can unsubscribe from the
              newsletter at any time using the link in any email. Email{' '}
              <a href="mailto:xunitary@gmail.com">xunitary@gmail.com</a> or call{' '}
              <a href="tel:+919363734565">+91 93637 34565</a>.
            </p>
          </section>

          <section>
            <h2>Changes</h2>
            <p>If we change how we handle data we will update this page and its date.</p>
          </section>
        </article>
      </main>
      <Footer />
    </>
  );
}

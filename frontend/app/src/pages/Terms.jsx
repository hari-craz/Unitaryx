import NavBar from '../components/layout/NavBar';
import Footer from '../components/layout/Footer';
import { PLANS, ADD_ONS } from '../components/sections/Hosting';
import { usePageMeta } from '../hooks/usePageMeta';
import './Privacy.css';

const UPDATED = '1 October 2026';

export default function Terms() {
  usePageMeta('Terms | Unitary X');

  return (
    <>
      <NavBar />
      <main className="privacy-page">
        <article className="privacy-inner">
          <header>
            <span className="eyebrow">Terms</span>
            <h1 className="gradient-headline privacy-title">The terms we work under.</h1>
            <p className="privacy-updated">Last updated {UPDATED}</p>
            <p className="privacy-lead">
              These terms cover Unitary X hosting and our project work. They are meant to be read, so we have kept them
              short and plain. If anything is unclear, ask us before you start.
            </p>
          </header>

          <section>
            <h2>Hosting</h2>
            <h3>What it covers</h3>
            <p>
              Unitary X hosting is for <strong>static websites and Dockerized applications only</strong>. Every plan
              includes SSL. If your project needs something outside that, talk to us first: specialised setups are
              handled through the Custom plan or an advanced-setup quote.
            </p>

            <h3>Plans and prices</h3>
            <p>Prices are in Indian rupees, per month.</p>
            <ul>
              {PLANS.map((p) => (
                <li key={p.key}>
                  <strong>{p.name}</strong>: {p.price} {p.suffix}. {p.for}.
                </li>
              ))}
            </ul>
            <p>The features included in each plan are listed in the Hosting section of the homepage.</p>

            <h3>Add-ons</h3>
            <ul>
              {ADD_ONS.map((a) => (
                <li key={a.label}>
                  <strong>{a.label}</strong>: {a.value}.
                </li>
              ))}
            </ul>

            <h3>Your copy of your work</h3>
            <p>
              Keep your own copy of your code and data. Backup is available as an optional add-on, and the Business plan
              lists &ldquo;monitoring &amp; backup options&rdquo;. Ask us exactly what is covered on your plan before you rely on
              backups.
            </p>
          </section>

          <section>
            <h2>Project work</h2>
            <ul>
              <li>Scope, timeline and price are agreed with you before work starts.</li>
              <li>Typical turnaround is 10 to 15 days, depending on the project.</li>
              <li>Revision rounds are part of the engagement.</li>
              <li>You receive the full source code on delivery, and we support the delivered work for 7 days after.</li>
              <li>Academic and college projects are welcome and are delivered to the same standard.</li>
            </ul>
            <h3>Payment</h3>
            <p>We accept UPI, bank transfer and other common digital payment methods.</p>
          </section>

          <section>
            <h2>Using our services</h2>
            <ul>
              <li>You are responsible for the content and software you host or ask us to build, and you must have the right to use it.</li>
              <li>Do not use our services for anything unlawful or that harms other people or their systems.</li>
              <li>Keep your account and server credentials safe, and tell us if you think they have been exposed.</li>
              <li>We may suspend a service that breaks these terms or puts other customers at risk, and we will tell you why.</li>
            </ul>
          </section>

          <section>
            <h2>Availability</h2>
            <p>
              We work to keep hosted services running well and use monitoring on the plans that include it, but we
              cannot promise uninterrupted service.
            </p>
          </section>

          <section>
            <h2>Billing questions and ending a service</h2>
            <p>
              For billing, refunds or to end a hosting service, contact us at{' '}
              <a href="mailto:xunitary@gmail.com">xunitary@gmail.com</a> or{' '}
              <a href="tel:+919363734565">+91 93637 34565</a>. How we handle personal data is explained in our{' '}
              <a href="/privacy">privacy notice</a>.
            </p>
          </section>

          <section>
            <h2>Changes</h2>
            <p>If we change these terms we will update this page and its date.</p>
          </section>
        </article>
      </main>
      <Footer />
    </>
  );
}

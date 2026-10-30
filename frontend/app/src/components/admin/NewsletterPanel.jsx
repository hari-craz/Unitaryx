import { useState } from 'react';
import NewsletterSubscribers from './NewsletterSubscribers';
import NewsletterCampaigns from './NewsletterCampaigns';

const VIEWS = [
  { key: 'subscribers', label: 'Subscribers' },
  { key: 'campaigns', label: 'Write & send' },
];

export default function NewsletterPanel() {
  const [view, setView] = useState('subscribers');

  return (
    <section className="admin-section">
      <div className="admin-section-head">
        <div>
          <h2>Newsletter</h2>
          <p className="admin-section-note">Manage who is subscribed and send updates to confirmed subscribers.</p>
        </div>
      </div>

      <div className="studio-tabs" role="tablist" aria-label="Newsletter sections">
        {VIEWS.map((v) => (
          <button
            key={v.key}
            type="button"
            role="tab"
            aria-selected={view === v.key}
            className={`studio-tab ${view === v.key ? 'active' : ''}`}
            onClick={() => setView(v.key)}
          >
            {v.label}
          </button>
        ))}
      </div>

      {view === 'subscribers' ? <NewsletterSubscribers /> : <NewsletterCampaigns />}
    </section>
  );
}

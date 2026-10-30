import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { getJSON } from '../../lib/api';
import './Testimonials.css';

function Stars({ value }) {
  return (
    <div className="stars" role="img" aria-label={`${value} out of 5`}>
      {[1, 2, 3, 4, 5].map((n) => (
        <span key={n} className={`star ${n <= value ? 'on' : ''}`} aria-hidden="true">
          ★
        </span>
      ))}
    </div>
  );
}

export default function Testimonials() {
  const [items, setItems] = useState([]);

  useEffect(() => {
    getJSON('/api/testimonials')
      .then(setItems)
      .catch(() => setItems([]));
  }, []);

  // Nothing to show until an admin publishes at least one testimonial.
  if (items.length === 0) return null;

  return (
    <section className="testimonials-section" id="testimonials" aria-labelledby="testimonials-title">
      <div className="section-inner">
        <span className="eyebrow">Client words</span>
        <h2 className="section-title" id="testimonials-title">
          What clients say about working with us.
        </h2>

        <div className="testimonials-grid">
          {items.map((t, i) => (
            <motion.figure
              key={t.id}
              className="testimonial-card glass"
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.3 }}
              transition={{ delay: Math.min(i * 0.05, 0.3), type: 'spring', stiffness: 240, damping: 26 }}
            >
              <Stars value={t.rating} />
              <blockquote className="testimonial-quote">{t.review}</blockquote>
              <figcaption className="testimonial-author">
                <span className="testimonial-avatar" aria-hidden="true">
                  {t.name.charAt(0).toUpperCase()}
                </span>
                <span>
                  <span className="testimonial-name">{t.name}</span>
                  {t.role && <span className="testimonial-role">{t.role}</span>}
                </span>
              </figcaption>
            </motion.figure>
          ))}
        </div>
      </div>
    </section>
  );
}

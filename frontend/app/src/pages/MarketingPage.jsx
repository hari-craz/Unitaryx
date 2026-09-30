import { usePageMeta } from '../hooks/usePageMeta';
import NavBar from '../components/layout/NavBar';
import ScrollRail from '../components/layout/ScrollRail';
import Footer from '../components/layout/Footer';
import Hero from '../components/sections/Hero';
import Services from '../components/sections/Services';
import FoundersCarousel from '../components/sections/founders/FoundersCarousel';
import ProjectsGrid from '../components/sections/projects/ProjectsGrid';
import Hosting from '../components/sections/Hosting';
import About from '../components/sections/About';
import Process from '../components/sections/Process';
import Faq from '../components/sections/Faq';
import Feedback from '../components/sections/Feedback';
import Contact from '../components/sections/Contact';

export default function MarketingPage() {
  usePageMeta();

  return (
    <>
      <NavBar />
      <ScrollRail />
      <main>
        {/* Signature pin-and-cover stacked panels */}
        <div className="pinned-stack">
          <Hero />
          <Services />
          <FoundersCarousel />
        </div>
        {/* Normal-flow content that scrolls over the pinned stack. Projects leads
            here (not a pinned panel) because a grid of ~8 cards can't fit one
            pinned viewport without an inner scrollbar / blank mid-scroll gap. */}
        <div className="marketing-flow">
          <ProjectsGrid />
          <Hosting />
          <About />
          <Process />
          <Faq />
          <Feedback />
          <Contact />
        </div>
      </main>
      <Footer />
    </>
  );
}

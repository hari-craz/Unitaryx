import { Routes, Route } from 'react-router-dom';
import AmbientBackground from './components/layout/AmbientBackground';
import CustomCursor from './components/layout/CustomCursor';
import MarketingPage from './pages/MarketingPage';
import Dashboard from './pages/Dashboard';
import AdminStudio from './pages/AdminStudio';
import ProjectPage from './pages/ProjectPage';
import NewsletterAction from './pages/NewsletterAction';
import Privacy from './pages/Privacy';
import NotFound from './pages/NotFound';

export default function App() {
  return (
    <>
      <AmbientBackground />
      <CustomCursor />
      <Routes>
        <Route path="/" element={<MarketingPage />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/admin/studio" element={<AdminStudio />} />
        <Route path="/projects/:slug" element={<ProjectPage />} />
        <Route path="/newsletter/confirm/:token" element={<NewsletterAction mode="confirm" />} />
        <Route path="/newsletter/unsubscribe/:token" element={<NewsletterAction mode="unsubscribe" />} />
        <Route path="/privacy" element={<Privacy />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </>
  );
}

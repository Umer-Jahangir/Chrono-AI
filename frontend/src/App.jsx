import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/common/Layout';
import HomePage from './pages/HomePage';
import DashboardPage from './pages/DashboardPage';
import TimelinePage from './pages/TimelinePage';
import SearchPage from './pages/SearchPage';
import { AuthProvider, useAuth } from './auth/AuthContext';
import LoginPage from './components/auth/LoginPage';

function SessionGate() {
  const { status } = useAuth();

  if (status === 'checking') {
    return (
      <main className="min-h-screen bg-background flex items-center justify-center" role="status">
        <div className="text-center">
          <span className="material-symbols-outlined text-primary text-4xl animate-spin">progress_activity</span>
          <p className="mt-3 text-on-surface-variant">Verifying your Chrono session…</p>
        </div>
      </main>
    );
  }
  if (status !== 'authenticated') return <LoginPage />;

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<HomePage />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="timeline" element={<TimelinePage />} />
          <Route path="search" element={<SearchPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <SessionGate />
    </AuthProvider>
  );
}

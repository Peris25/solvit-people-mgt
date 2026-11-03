import React, { useState } from 'react';
import { Outlet, Navigate, Link } from 'react-router-dom';
import { useNotifications } from '../context/NotificationContext';
import { useAuth } from '../context/AuthContext';
import Sidebar from './Sidebar';
import AIAgent from './AIAgent';
import FirstLoginTour from './FirstLoginTour';
import RequiredPasswordChange from './RequiredPasswordChange';
import MfaSecurity from '../pages/MfaSecurity';
import './Portal.css';

export default function Layout() {
  const { user } = useAuth();
  const unreadCount = useNotifications()?.unreadCount;
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => window.matchMedia?.('(max-width: 767px)').matches ?? false);
  const [aiOpen, setAiOpen] = useState(false);

  if (user === undefined) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#F5F5F5', fontFamily: 'Arial' }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ width: '40px', height: '40px', backgroundColor: '#FF353F', margin: '0 auto 16px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <span style={{ color: '#fff', fontWeight: 900 }}>S</span>
          </div>
          <div style={{ fontSize: '13px', color: '#525252', fontWeight: 700 }}>Loading...</div>
        </div>
      </div>
    );
  }

  if (user === null) return <Navigate to="/login" replace />;
  if (user.must_change_password) return <RequiredPasswordChange />;
  if (user.mfa_required && !user.mfa_verified) return <MfaSecurity key={user.id} required />;

  // Solver — mobile bottom-nav-only interface (no sidebar)
  if (user.role === 'solver') {
    return (
      <div style={{ minHeight: '100vh', backgroundColor: '#F5F5F5', fontFamily: 'Nunito Sans, sans-serif' }}>
        <nav style={{ padding: '12px', textAlign: 'right' }}><Link to="/account-security" style={{ marginRight: '16px' }}>Account security</Link><Link to="/notifications">Notifications{unreadCount > 0 ? ` (${unreadCount} unread)` : ''}</Link></nav>
        <Outlet />
        <FirstLoginTour />
      </div>
    );
  }

  return (
    <div className="solvit-portal" style={{ display: 'flex', minHeight: '100vh', backgroundColor: '#F5F5F5', fontFamily: 'Nunito Sans, sans-serif' }}>
      <Sidebar collapsed={sidebarCollapsed} onToggle={setSidebarCollapsed} onAIToggle={() => setAiOpen(p => !p)} aiOpen={aiOpen} />
      <div className="portal-content" style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden', marginRight: aiOpen ? '380px' : 0, transition: 'margin-right 0.3s' }}>
        <header className="portal-topbar">
          <div className="portal-workspace-label"><span className="portal-brand-dot" aria-hidden="true" /><span>Solvit People</span><span className="portal-topbar-divider" aria-hidden="true">/</span><strong>{['hr_admin', 'hr_manager'].includes(user.role) ? 'HR workspace' : 'My workspace'}</strong></div>
          <Link to="/my-profile" className="portal-account-link"><span className="portal-account-initial" aria-hidden="true">{user.full_name?.[0] || 'S'}</span><span>{user.full_name || 'My Profile'}</span></Link>
        </header>
        <a href="#portal-page-content" className="portal-skip-link">Skip to page content</a>
        <main id="portal-page-content" tabIndex={-1} className="portal-main" style={{ flex: 1, overflowY: 'auto', padding: '24px', maxWidth: '1400px', margin: '0 auto', width: '100%', boxSizing: 'border-box' }}>
          <Outlet />
        </main>
      </div>
      {aiOpen && <AIAgent onClose={() => setAiOpen(false)} />}
      <FirstLoginTour />
    </div>
  );
}

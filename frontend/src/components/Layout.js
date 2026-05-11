import React, { useState } from 'react';
import { Outlet, Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import Sidebar from './Sidebar';
import AIAgent from './AIAgent';

export default function Layout() {
  const { user } = useAuth();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
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

  // Solver — mobile bottom-nav-only interface (no sidebar)
  if (user.role === 'solver') {
    return (
      <div style={{ minHeight: '100vh', backgroundColor: '#F5F5F5', fontFamily: 'Nunito Sans, sans-serif' }}>
        <Outlet />
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', minHeight: '100vh', backgroundColor: '#F5F5F5', fontFamily: 'Nunito Sans, sans-serif' }}>
      <Sidebar collapsed={sidebarCollapsed} onToggle={setSidebarCollapsed} onAIToggle={() => setAiOpen(p => !p)} aiOpen={aiOpen} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', marginRight: aiOpen ? '380px' : 0, transition: 'margin-right 0.3s' }}>
        <main style={{ flex: 1, overflowY: 'auto', padding: '24px', maxWidth: '1400px', margin: '0 auto', width: '100%' }}>
          <Outlet />
        </main>
      </div>
      {aiOpen && <AIAgent onClose={() => setAiOpen(false)} />}
    </div>
  );
}

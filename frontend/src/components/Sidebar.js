import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Bell, ChevronLeft, Settings, LogOut, Brain } from 'lucide-react';
import * as api from '../services/api';

const MENU_ITEMS = [
  { section: 'Core', items: [
    { path: '/dashboard', label: 'HR Dashboard', icon: '⊞', roles: ['hr_admin', 'hr_manager', 'executive'] },
    { path: '/employees', label: 'Employee Database', icon: '👥', roles: ['hr_admin', 'hr_manager', 'line_manager', 'finance', 'employee'] },
    { path: '/solvers', label: 'Solver Database', icon: '⚡', roles: ['hr_admin', 'hr_manager', 'line_manager', 'solver'] },
    { path: '/recruitment', label: 'Recruitment', icon: '🎯', roles: ['hr_admin', 'hr_manager', 'line_manager'] },
    { path: '/onboarding', label: 'Onboarding', icon: '🚀', roles: ['hr_admin', 'hr_manager', 'line_manager', 'employee', 'solver'] },
  ]},
  { section: 'Performance', items: [
    { path: '/performance', label: 'Performance Reviews', icon: '📊', roles: ['hr_admin', 'hr_manager', 'line_manager', 'employee'] },
    { path: '/surveys', label: 'Alignment Surveys', icon: '📋', roles: ['hr_admin', 'hr_manager', 'employee', 'solver'] },
    { path: '/retention', label: 'Retention & Risk', icon: '🛡', roles: ['hr_admin', 'hr_manager'] },
    { path: '/lnd', label: 'L&D', icon: '📚', roles: ['hr_admin', 'hr_manager', 'line_manager', 'employee'] },
    { path: '/projects', label: 'Project Ownership', icon: '💼', roles: ['hr_admin', 'hr_manager', 'employee'] },
  ]},
  { section: 'HR Operations', items: [
    { path: '/leave', label: 'Leave Management', icon: '🏖', roles: ['hr_admin', 'hr_manager', 'line_manager', 'employee'] },
    { path: '/compensation', label: 'Compensation', icon: '💰', roles: ['hr_admin', 'hr_manager', 'finance'] },
    { path: '/recognition', label: 'Recognition', icon: '🏆', roles: ['hr_admin', 'hr_manager', 'line_manager', 'employee', 'solver'] },
    { path: '/disciplinary', label: 'Disciplinary', icon: '⚖', roles: ['hr_admin', 'hr_manager', 'line_manager'] },
    { path: '/policies', label: 'Policy Library', icon: '📄', roles: ['hr_admin', 'hr_manager', 'employee', 'solver'] },
  ]},
  { section: 'Finance & Admin', items: [
    { path: '/budget', label: 'Budget Governance', icon: '📈', roles: ['hr_admin', 'finance', 'executive'] },
    { path: '/compliance', label: 'Statutory Compliance', icon: '✅', roles: ['hr_admin', 'finance', 'hr_manager'] },
    { path: '/calendar', label: 'HR Calendar', icon: '📅', roles: ['hr_admin', 'hr_manager', 'employee', 'solver'] },
    { path: '/forms', label: 'Forms', icon: '📝', roles: ['hr_admin', 'hr_manager', 'line_manager', 'employee', 'solver'] },
    { path: '/settings', label: 'Settings', icon: '⚙', roles: ['hr_admin', 'hr_manager'] },
  ]},
];

const ROLE_LABELS = { hr_admin: 'HR Admin', hr_manager: 'HR Manager', line_manager: 'Line Manager', finance: 'Finance', employee: 'Employee', solver: 'Solver', executive: 'MD / Executive' };
const ROLE_COLORS = { hr_admin: '#FF353F', hr_manager: '#F97316', line_manager: '#191919', finance: '#22C55E', employee: '#3B82F6', solver: '#8B5CF6', executive: '#EF4444' };

export default function Sidebar({ collapsed, onToggle, onAIToggle, aiOpen }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [notifications, setNotifications] = useState([]);
  const [showNotif, setShowNotif] = useState(false);

  // Poll notifications every 60s
  React.useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const r = await api.getNotifications();
        if (!cancelled) setNotifications(r.data || []);
      } catch { /* ignore */ }
    };
    if (user) {
      load();
      const t = setInterval(load, 60000);
      return () => { cancelled = true; clearInterval(t); };
    }
    return undefined;
  }, [user]);

  const unread = notifications.filter(n => !n.is_read).length;

  const markRead = async (id) => {
    try { await api.markNotificationRead(id); } catch { /* ignore */ }
    setNotifications(prev => prev.map(n => n.id === id ? { ...n, is_read: true } : n));
  };

  const markAllRead = async () => {
    const unreadIds = notifications.filter(n => !n.is_read).map(n => n.id);
    setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
    for (const id of unreadIds) {
      try { await api.markNotificationRead(id); } catch { /* ignore */ }
    }
  };

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const filteredMenu = MENU_ITEMS.map(section => ({
    ...section,
    items: section.items.filter(item => !item.roles || item.roles.includes(user?.role))
  })).filter(section => section.items.length > 0);

  const isActive = (path) => location.pathname === path;

  if (collapsed) {
    return (
      <div style={{ width: '56px', backgroundColor: '#191919', display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '16px 0', gap: '8px', transition: 'width 0.2s', zIndex: 50, minHeight: '100vh' }}>
        <div style={{ width: '36px', height: '36px', backgroundColor: '#FF353F', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', marginBottom: '16px' }} onClick={() => onToggle(false)}>
          <span style={{ color: '#fff', fontWeight: 900, fontSize: '16px' }}>S</span>
        </div>
        <button onClick={() => onToggle(false)} style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.5)', cursor: 'pointer', padding: '8px', transition: 'color 0.2s' }}>≡</button>
      </div>
    );
  }

  return (
    <div style={{ width: '240px', backgroundColor: '#191919', display: 'flex', flexDirection: 'column', minHeight: '100vh', fontFamily: 'Arial, Helvetica, sans-serif', flexShrink: 0 }}>
      {/* Logo */}
      <div style={{ padding: '20px 20px 12px', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{ width: '32px', height: '32px', backgroundColor: '#FF353F', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              <span style={{ color: '#fff', fontWeight: 900, fontSize: '16px' }}>S</span>
            </div>
            <div>
              <div style={{ color: '#fff', fontWeight: 900, fontSize: '14px', letterSpacing: '-0.03em' }}>SOLVIT</div>
              <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.1em' }}>People Platform</div>
            </div>
          </div>
          <button onClick={() => onToggle(true)} style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.4)', cursor: 'pointer', fontSize: '16px', padding: '4px' }}>‹</button>
        </div>
      </div>

      {/* User info */}
      <div style={{ padding: '12px 20px', borderBottom: '1px solid rgba(255,255,255,0.08)', position: 'relative' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ width: '32px', height: '32px', borderRadius: '50%', backgroundColor: ROLE_COLORS[user?.role] || '#525252', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
            <span style={{ color: '#fff', fontWeight: 700, fontSize: '12px' }}>{user?.full_name?.[0] || 'U'}</span>
          </div>
          <div style={{ overflow: 'hidden', flex: 1 }}>
            <div style={{ color: '#fff', fontSize: '12px', fontWeight: 700, letterSpacing: '-0.02em', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{user?.full_name || user?.email}</div>
            <div style={{ backgroundColor: ROLE_COLORS[user?.role] || '#525252', color: '#fff', fontSize: '9px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', padding: '1px 6px', display: 'inline-block', marginTop: '2px' }}>
              {ROLE_LABELS[user?.role] || user?.role}
            </div>
          </div>
          <button data-testid="notif-bell" onClick={() => setShowNotif(s => !s)} style={{ position: 'relative', background: 'none', border: 'none', cursor: 'pointer', padding: '6px', color: 'rgba(255,255,255,0.7)' }}>
            <Bell size={16} />
            {unread > 0 && (
              <span data-testid="notif-badge" style={{ position: 'absolute', top: '-2px', right: '-2px', backgroundColor: '#FF353F', color: '#fff', fontSize: '9px', fontWeight: 900, padding: '1px 5px', borderRadius: '8px', minWidth: '14px', textAlign: 'center', lineHeight: 1.2 }}>{unread > 99 ? '99+' : unread}</span>
            )}
          </button>
        </div>
        {showNotif && (
          <div data-testid="notif-dropdown" style={{ position: 'absolute', top: '60px', right: '8px', width: '320px', backgroundColor: '#fff', color: '#191919', boxShadow: '0 8px 32px rgba(0,0,0,0.4)', zIndex: 200, maxHeight: '420px', display: 'flex', flexDirection: 'column' }}>
            <div style={{ padding: '12px 16px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <strong style={{ fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.12em' }}>Notifications {unread > 0 && <span style={{ color: '#FF353F' }}>· {unread}</span>}</strong>
              {unread > 0 && <button data-testid="mark-all-read" onClick={markAllRead} style={{ background: 'none', border: 'none', color: '#FF353F', cursor: 'pointer', fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Mark all read</button>}
            </div>
            <div style={{ overflowY: 'auto', flex: 1 }}>
              {notifications.length === 0 ? (
                <div style={{ padding: '32px', textAlign: 'center', color: '#9CA3AF', fontSize: '12px' }}>No notifications</div>
              ) : notifications.slice(0, 20).map(n => (
                <div key={n.id} data-testid={`notif-${n.id}`} onClick={() => markRead(n.id)} style={{ padding: '12px 16px', borderBottom: '1px solid rgba(25,25,25,0.05)', cursor: 'pointer', backgroundColor: n.is_read ? '#fff' : '#FEF2F2' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px' }}>
                    <strong style={{ fontSize: '12px', color: '#191919', flex: 1 }}>{n.title}</strong>
                    {!n.is_read && <span style={{ width: '8px', height: '8px', backgroundColor: '#FF353F', borderRadius: '50%', flexShrink: 0, marginTop: '4px' }} />}
                  </div>
                  <p style={{ fontSize: '11px', color: '#525252', margin: '4px 0 0', lineHeight: 1.4 }}>{n.message}</p>
                  <div style={{ fontSize: '10px', color: '#9CA3AF', marginTop: '4px' }}>{n.created_at ? new Date(n.created_at).toLocaleString('en-KE', { dateStyle: 'short', timeStyle: 'short' }) : ''}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Navigation */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
        {filteredMenu.map(section => (
          <div key={section.section} style={{ marginBottom: '4px' }}>
            <div style={{ padding: '8px 20px 4px', fontSize: '9px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.2em', color: 'rgba(255,255,255,0.3)' }}>{section.section}</div>
            {section.items.map(item => (
              <button
                key={item.path}
                data-testid={`nav-${item.path.replace('/', '')}`}
                onClick={() => navigate(item.path)}
                style={{
                  width: '100%', padding: '8px 20px', display: 'flex', alignItems: 'center', gap: '10px',
                  backgroundColor: isActive(item.path) ? 'rgba(255,53,63,0.15)' : 'transparent',
                  borderLeft: isActive(item.path) ? '3px solid #FF353F' : '3px solid transparent',
                  border: 'none', borderRight: 'none', borderTop: 'none', borderBottom: 'none',
                  borderLeftColor: isActive(item.path) ? '#FF353F' : 'transparent',
                  borderLeftStyle: 'solid', borderLeftWidth: '3px',
                  color: isActive(item.path) ? '#fff' : 'rgba(255,255,255,0.6)',
                  cursor: 'pointer', textAlign: 'left', fontSize: '12px', fontFamily: 'Arial',
                  transition: 'all 0.15s'
                }}
                onMouseEnter={e => { if (!isActive(item.path)) e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.06)'; }}
                onMouseLeave={e => { if (!isActive(item.path)) e.currentTarget.style.backgroundColor = 'transparent'; }}
              >
                <span style={{ fontSize: '14px', width: '18px', textAlign: 'center' }}>{item.icon}</span>
                <span style={{ fontWeight: isActive(item.path) ? 700 : 400 }}>{item.label}</span>
              </button>
            ))}
          </div>
        ))}
      </div>

      {/* AI Agent toggle (HR Admin only) */}
      {(user?.role === 'hr_admin' || user?.role === 'hr_manager') && (
        <div style={{ padding: '12px 20px', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
          <button
            data-testid="ai-agent-toggle"
            onClick={onAIToggle}
            style={{ width: '100%', padding: '10px 14px', backgroundColor: aiOpen ? '#FF353F' : 'rgba(255,53,63,0.15)', color: aiOpen ? '#fff' : '#FF353F', border: '1px solid rgba(255,53,63,0.4)', cursor: 'pointer', fontSize: '12px', fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase', fontFamily: 'Arial', display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center', transition: 'all 0.2s' }}
          >
            <Brain size={14} />
            AI HR Agent
          </button>
        </div>
      )}

      {/* Logout */}
      <div style={{ padding: '12px 20px', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
        <button onClick={handleLogout} style={{ width: '100%', padding: '8px 12px', backgroundColor: 'transparent', color: 'rgba(255,255,255,0.5)', border: '1px solid rgba(255,255,255,0.1)', cursor: 'pointer', fontSize: '11px', fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', fontFamily: 'Arial', display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center', transition: 'all 0.2s' }}>
          <LogOut size={12} />
          Sign Out
        </button>
      </div>
    </div>
  );
}

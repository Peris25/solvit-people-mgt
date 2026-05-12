import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useTheme, themeTokens } from '../context/ThemeContext';
import {
  Bell, LogOut, Brain,
  LayoutDashboard, Users, Zap, Target, Rocket,
  BarChart3, ClipboardList, ShieldCheck, BookOpen, Briefcase,
  Palmtree, Wallet, Award, Scale, FileText,
  TrendingUp, CheckCircle2, CalendarDays, FileEdit,
  ListChecks, Settings as SettingsIcon, Cog, ChevronLeft, Menu,
  UploadCloud, Sun, Moon
} from 'lucide-react';
import * as api from '../services/api';

const ICON_SIZE = 15;

const MENU_ITEMS = [
  { section: 'Core', items: [
    { path: '/dashboard',   label: 'Dashboard',    Icon: LayoutDashboard, roles: ['hr_admin','hr_manager','executive','line_manager','finance','employee','solver','board','it_admin'] },
    { path: '/employees',   label: 'Employees',    Icon: Users,           roles: ['hr_admin','hr_manager','line_manager','finance','employee','executive'] },
    { path: '/solvers',     label: 'Solvers',      Icon: Zap,             roles: ['hr_admin','hr_manager','line_manager','solver','executive'] },
    { path: '/recruitment', label: 'Recruitment',  Icon: Target,          roles: ['hr_admin','hr_manager','line_manager','executive'] },
    { path: '/onboarding',  label: 'Onboarding',   Icon: Rocket,          roles: ['hr_admin','hr_manager','line_manager','employee','solver'] },
  ]},
  { section: 'Performance', items: [
    { path: '/performance', label: 'Performance',  Icon: BarChart3,       roles: ['hr_admin','hr_manager','line_manager','employee','executive'] },
    { path: '/surveys',     label: 'Surveys',      Icon: ClipboardList,   roles: ['hr_admin','hr_manager','employee','solver','executive'] },
    { path: '/retention',   label: 'Retention',    Icon: ShieldCheck,     roles: ['hr_admin','hr_manager','executive'] },
    { path: '/lnd',         label: 'L&D',          Icon: BookOpen,        roles: ['hr_admin','hr_manager','line_manager','employee'] },
    { path: '/projects',    label: 'Projects',     Icon: Briefcase,       roles: ['hr_admin','hr_manager','line_manager','employee'] },
  ]},
  { section: 'HR Operations', items: [
    { path: '/leave',        label: 'Leave',        Icon: Palmtree,       roles: ['hr_admin','hr_manager','line_manager','employee'] },
    { path: '/compensation', label: 'Compensation', Icon: Wallet,         roles: ['hr_admin','hr_manager','finance','executive'] },
    { path: '/recognition',  label: 'Recognition',  Icon: Award,          roles: ['hr_admin','hr_manager','line_manager','finance','employee','solver'] },
    { path: '/disciplinary', label: 'Disciplinary', Icon: Scale,          roles: ['hr_admin','hr_manager','line_manager','employee'] },
    { path: '/policies',     label: 'Policies',     Icon: FileText,       roles: ['hr_admin','hr_manager','line_manager','finance','employee','solver','executive'] },
  ]},
  { section: 'Finance & Admin', items: [
    { path: '/budget',     label: 'Budget',         Icon: TrendingUp,    roles: ['hr_admin','hr_manager','finance','executive'] },
    { path: '/compliance', label: 'Compliance',     Icon: CheckCircle2,  roles: ['hr_admin','hr_manager','finance'] },
    { path: '/calendar',   label: 'Calendar',       Icon: CalendarDays,  roles: ['hr_admin','hr_manager','line_manager','finance'] },
    { path: '/forms',      label: 'Forms',          Icon: FileEdit,      roles: ['hr_admin','hr_manager','line_manager','finance','employee','solver'] },
    { path: '/my-tasks',   label: 'My Tasks',       Icon: ListChecks,    roles: ['hr_admin','hr_manager','line_manager','employee','solver','finance','executive','it_admin'] },
    { path: '/data-import', label: 'Data Import',    Icon: UploadCloud,   roles: ['hr_admin','hr_manager','it_admin'] },
    { path: '/masters',    label: 'Masters Settings', Icon: Cog,          roles: ['it_admin','hr_admin','hr_manager','finance'] },
    { path: '/settings',   label: 'AI & Email Setup', Icon: SettingsIcon, roles: ['hr_admin','hr_manager','it_admin'] },
  ]},
];

const ROLE_LABELS = {
  hr_admin: 'HR Admin', hr_manager: 'HR Manager', line_manager: 'Line Manager',
  finance: 'Finance', employee: 'Employee', solver: 'Solver',
  executive: 'MD / Executive', board: 'Board', it_admin: 'IT Admin'
};
const ROLE_COLORS = {
  hr_admin: '#FF353F', hr_manager: '#FF353F', line_manager: '#191919',
  finance: '#22C55E', employee: '#3B82F6', solver: '#191919',
  executive: '#191919', board: '#191919', it_admin: '#525252'
};

export default function Sidebar({ collapsed, onToggle, onAIToggle, aiOpen }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { theme, toggle: toggleTheme } = useTheme();
  const tk = themeTokens(theme);
  const [notifications, setNotifications] = useState([]);
  const [showNotif, setShowNotif] = useState(false);

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

  const filteredMenu = (() => {
    if (user?.role === 'employee') {
      return [{
        section: 'My Workspace',
        items: [
          { path: '/my-tasks',    label: 'My Tasks',     Icon: ListChecks },
          { path: '/dashboard',   label: 'My Dashboard', Icon: LayoutDashboard },
          { path: '/leave',       label: 'Leave',        Icon: Palmtree },
          { path: '/performance', label: 'My Reviews',   Icon: BarChart3 },
          { path: '/surveys',     label: 'My Surveys',   Icon: ClipboardList },
          { path: '/lnd',         label: 'Development',  Icon: BookOpen },
          { path: '/recognition', label: 'Recognition',  Icon: Award },
          { path: '/policies',    label: 'Policies',     Icon: FileText },
        ]
      }];
    }
    return MENU_ITEMS.map(section => ({
      ...section,
      items: section.items.filter(item => !item.roles || item.roles.includes(user?.role))
    })).filter(section => section.items.length > 0);
  })();

  const isActive = (path) => location.pathname === path;

  if (collapsed) {
    return (
      <div style={{ width: '56px', backgroundColor: tk.sidebarBg, display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '16px 0', gap: '8px', zIndex: 50, minHeight: '100vh', borderRightWidth: '1px', borderRightStyle: 'solid', borderRightColor: tk.sidebarBorder }}>
        <div data-testid="solvit-logo-mark" style={{ width: '36px', height: '36px', backgroundColor: '#FF353F', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', marginBottom: '16px' }} onClick={() => onToggle(false)}>
          <span style={{ color: '#fff', fontWeight: 900, fontSize: '16px', fontFamily: 'Barlow' }}>S</span>
        </div>
        <button data-testid="sidebar-expand" onClick={() => onToggle(false)} style={{ background: 'none', border: 'none', color: tk.sidebarMuted, cursor: 'pointer', padding: '8px' }}>
          <Menu size={18} />
        </button>
      </div>
    );
  }

  return (
    <div style={{ width: '240px', backgroundColor: tk.sidebarBg, display: 'flex', flexDirection: 'column', minHeight: '100vh', fontFamily: 'Nunito Sans, sans-serif', flexShrink: 0, borderRightWidth: '1px', borderRightStyle: 'solid', borderRightColor: tk.sidebarBorder }}>
      {/* Logo */}
      <div style={{ padding: '20px 20px 12px', borderBottomWidth: '1px', borderBottomStyle: 'solid', borderBottomColor: tk.sidebarBorder }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{ width: '32px', height: '32px', backgroundColor: '#FF353F', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              <span style={{ color: '#fff', fontWeight: 900, fontSize: '16px', fontFamily: 'Barlow' }}>S</span>
            </div>
            <div>
              <div style={{ color: tk.sidebarText, fontWeight: 900, fontSize: '14px', letterSpacing: '-0.03em', fontFamily: 'Barlow' }}>SOLVIT</div>
              <div style={{ color: tk.sidebarSubtle, fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.1em' }}>People Platform</div>
            </div>
          </div>
          <button data-testid="sidebar-collapse" onClick={() => onToggle(true)} style={{ background: 'none', border: 'none', color: tk.sidebarSubtle, cursor: 'pointer', padding: '4px' }}>
            <ChevronLeft size={16} />
          </button>
        </div>
      </div>

      {/* User info */}
      <div style={{ padding: '12px 20px', borderBottomWidth: '1px', borderBottomStyle: 'solid', borderBottomColor: tk.sidebarBorder, position: 'relative' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ width: '32px', height: '32px', borderRadius: '50%', backgroundColor: ROLE_COLORS[user?.role] || '#525252', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
            <span style={{ color: '#fff', fontWeight: 700, fontSize: '12px' }}>{user?.full_name?.[0] || 'U'}</span>
          </div>
          <div style={{ overflow: 'hidden', flex: 1 }}>
            <div style={{ color: tk.sidebarText, fontSize: '12px', fontWeight: 700, letterSpacing: '-0.02em', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{user?.full_name || user?.email}</div>
            <div style={{ backgroundColor: ROLE_COLORS[user?.role] || '#525252', color: '#fff', fontSize: '9px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', padding: '1px 6px', display: 'inline-block', marginTop: '2px' }}>
              {ROLE_LABELS[user?.role] || user?.role}
            </div>
          </div>
          <button data-testid="notif-bell" onClick={() => setShowNotif(s => !s)} style={{ position: 'relative', background: 'none', border: 'none', cursor: 'pointer', padding: '6px', color: tk.sidebarMuted }}>
            <Bell size={16} />
            {unread > 0 && (
              <span data-testid="notif-badge" style={{ position: 'absolute', top: '-2px', right: '-2px', backgroundColor: '#FF353F', color: '#fff', fontSize: '9px', fontWeight: 900, padding: '1px 5px', minWidth: '14px', textAlign: 'center', lineHeight: 1.2 }}>{unread > 99 ? '99+' : unread}</span>
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
            <div style={{ padding: '8px 20px 4px', fontSize: '9px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.2em', color: tk.sidebarSubtle }}>{section.section}</div>
            {section.items.map(item => {
              const Icon = item.Icon;
              const active = isActive(item.path);
              return (
                <button
                  key={item.path}
                  data-testid={`nav-${item.path.replace('/', '')}`}
                  onClick={() => navigate(item.path)}
                  style={{
                    width: '100%', padding: '9px 20px', display: 'flex', alignItems: 'center', gap: '12px',
                    backgroundColor: active ? tk.sidebarActiveBg : 'transparent',
                    border: 'none',
                    borderLeftStyle: 'solid', borderLeftWidth: '3px',
                    borderLeftColor: active ? '#FF353F' : 'transparent',
                    color: active ? tk.sidebarActiveText : tk.sidebarMuted,
                    cursor: 'pointer', textAlign: 'left', fontSize: '12px',
                    fontFamily: 'Nunito Sans, sans-serif',
                    transition: 'background-color 0.15s, color 0.15s'
                  }}
                  onMouseEnter={e => { if (!active) e.currentTarget.style.backgroundColor = tk.sidebarHoverBg; }}
                  onMouseLeave={e => { if (!active) e.currentTarget.style.backgroundColor = 'transparent'; }}
                >
                  <Icon size={ICON_SIZE} strokeWidth={active ? 2.4 : 2} />
                  <span style={{ fontWeight: active ? 700 : 500 }}>{item.label}</span>
                </button>
              );
            })}
          </div>
        ))}
      </div>

      {/* AI Agent toggle */}
      {(user?.role === 'hr_admin' || user?.role === 'hr_manager') && (
        <div style={{ padding: '12px 20px', borderTopWidth: '1px', borderTopStyle: 'solid', borderTopColor: tk.sidebarBorder }}>
          <button
            data-testid="ai-agent-toggle"
            onClick={onAIToggle}
            style={{ width: '100%', padding: '10px 14px', backgroundColor: aiOpen ? '#FF353F' : 'rgba(255,53,63,0.12)', color: aiOpen ? '#fff' : '#FF353F', border: '1px solid rgba(255,53,63,0.35)', cursor: 'pointer', fontSize: '12px', fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase', fontFamily: 'Barlow, sans-serif', display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center', transition: 'all 0.2s' }}
          >
            <Brain size={14} />
            AI HR Agent
          </button>
        </div>
      )}

      {/* Theme toggle + Logout */}
      <div style={{ padding: '12px 20px', borderTopWidth: '1px', borderTopStyle: 'solid', borderTopColor: tk.sidebarBorder, display: 'flex', gap: '8px' }}>
        <button data-testid="theme-toggle" onClick={toggleTheme} title={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
          style={{ flex: '0 0 auto', padding: '8px 12px', backgroundColor: 'transparent', color: tk.sidebarMuted, borderWidth: '1px', borderStyle: 'solid', borderColor: tk.sidebarBorder, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          {theme === 'light' ? <Moon size={14} /> : <Sun size={14} />}
        </button>
        <button data-testid="logout-btn" onClick={handleLogout} style={{ flex: 1, padding: '8px 12px', backgroundColor: 'transparent', color: tk.sidebarMuted, borderWidth: '1px', borderStyle: 'solid', borderColor: tk.sidebarBorder, cursor: 'pointer', fontSize: '11px', fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', fontFamily: 'Barlow, sans-serif', display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center', transition: 'all 0.2s' }}>
          <LogOut size={12} />
          Sign Out
        </button>
      </div>
    </div>
  );
}

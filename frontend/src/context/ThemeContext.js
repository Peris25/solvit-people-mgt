import React, { createContext, useContext, useEffect, useState } from 'react';

const ThemeContext = createContext({ theme: 'light', setTheme: () => {}, toggle: () => {} });

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(() => {
    try { return localStorage.getItem('solvit_theme') || 'light'; } catch { return 'light'; }
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    try { localStorage.setItem('solvit_theme', theme); } catch { /* ignore */ }
  }, [theme]);

  const setTheme = (t) => setThemeState(t);
  const toggle = () => setThemeState(t => t === 'light' ? 'dark' : 'light');

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggle }}>
      {children}
    </ThemeContext.Provider>
  );
}

export const useTheme = () => useContext(ThemeContext);

/** Color tokens — read this once per render in components that need theme-aware inline styles. */
export function themeTokens(theme) {
  if (theme === 'dark') {
    return {
      sidebarBg:        '#191919',
      sidebarBorder:    'rgba(255,255,255,0.08)',
      sidebarText:      '#fff',
      sidebarMuted:     'rgba(255,255,255,0.6)',
      sidebarSubtle:    'rgba(255,255,255,0.3)',
      sidebarActiveBg:  'rgba(255,53,63,0.15)',
      sidebarActiveText:'#fff',
      sidebarHoverBg:   'rgba(255,255,255,0.06)',
      aiHeaderBg:       '#191919',
      aiHeaderText:     '#fff',
      aiHeaderMuted:    'rgba(255,255,255,0.5)',
      tourStepBg:       '#191919',
      tourStepText:     '#fff',
      tourStepMuted:    'rgba(255,255,255,0.75)',
      panelBg:          '#191919',
      panelText:        '#fff',
    };
  }
  // light (default)
  return {
    sidebarBg:        '#FFFFFF',
    sidebarBorder:    'rgba(25,25,25,0.06)',
    sidebarText:      '#191919',
    sidebarMuted:     '#525252',
    sidebarSubtle:    '#9CA3AF',
    sidebarActiveBg:  '#FFEEEE',
    sidebarActiveText:'#FF353F',
    sidebarHoverBg:   '#F5F5F5',
    aiHeaderBg:       '#FFFFFF',
    aiHeaderText:     '#191919',
    aiHeaderMuted:    '#9CA3AF',
    tourStepBg:       '#FFFFFF',
    tourStepText:     '#191919',
    tourStepMuted:    '#525252',
    panelBg:          '#FFFFFF',
    panelText:        '#191919',
  };
}

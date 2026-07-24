// Design tokens for the Companion frontend
// Single source of truth for colors, spacing, typography

export const theme = {
  colors: {
    bg: {
      root: '#1a1a1e',
      panel: '#18181c',
      surface: '#222226',
      hover: '#2a2a2e',
      elevated: '#2e2e32',
    },
    text: {
      primary: '#e0e0e0',
      secondary: '#888',
      muted: '#555',
      accent: '#e0c080',
    },
    chat: {
      user: '#2b5278',
      assistant: '#222226',
      system: 'rgba(255,255,255,0.06)',
    },
    status: {
      connected: '#4ade80',
      connecting: '#fbbf24',
      disconnected: '#ef4444',
      thinking: '#fbbf24',
      speaking: '#4ade80',
      idle: '#888',
    },
    border: '#2a2a2e',
    accent: '#4a7ab5',
    accentHover: '#5a8ac5',
    danger: '#ef4444',
    dangerHover: '#ff5555',
  },
  spacing: {
    xs: 4,
    sm: 8,
    md: 12,
    lg: 16,
    xl: 24,
  },
  radius: {
    sm: 4,
    md: 8,
    lg: 12,
    xl: 16,
    full: 9999,
  },
  fontSize: {
    xs: '0.7rem',
    sm: '0.8rem',
    md: '0.9rem',
    lg: '1.1rem',
    xl: '1.3rem',
  },
  fontWeight: {
    normal: 400,
    medium: 500,
    semibold: 600,
    bold: 700,
  },
  animation: {
    fast: '150ms',
    normal: '250ms',
    slow: '400ms',
  },
  zIndex: {
    dropdown: 100,
    modal: 200,
    tooltip: 300,
  },
  electron: {
    titleBarHeight: 32,
  },
} as const

export type Theme = typeof theme

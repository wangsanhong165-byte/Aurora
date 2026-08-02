// Design tokens for the Companion frontend
// Single source of truth for colors, spacing, typography

export const theme = {
  colors: {
    bg: {
      root: '#1a2030',
      panel: '#232b3d',
      surface: '#2d374b',
      hover: '#37435a',
      elevated: '#414f69',
    },
    text: {
      primary: '#eef0f7',
      secondary: '#aab2c2',
      muted: '#7f899c',
      accent: '#d97757',
    },
    chat: {
      user: 'rgba(217, 119, 87, 0.20)',
      assistant: 'rgba(36, 43, 58, 0.90)',
      system: 'rgba(210, 220, 255, 0.08)',
    },
    status: {
      connected: '#7dc9a0',
      connecting: '#e0b06c',
      disconnected: '#df858b',
      thinking: '#d97757',
      speaking: '#83d5dc',
      idle: '#7f899c',
    },
    border: '#30394b',
    accent: '#d97757',
    accentHover: '#e39576',
    danger: '#df858b',
    dangerHover: '#ef9ba0',
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
  icon: {
    nav: 18,
    action: 16,
    compact: 14,
    strokeWidth: 1.75,
  },
  zIndex: {
    dropdown: 100,
    modal: 200,
    tooltip: 300,
  },
  electron: {
    titleBarHeight: 36,
  },
} as const

export type Theme = typeof theme

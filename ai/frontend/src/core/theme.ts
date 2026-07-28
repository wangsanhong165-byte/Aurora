// Design tokens for the Companion frontend
// Single source of truth for colors, spacing, typography

export const theme = {
  colors: {
    bg: {
      root: '#0d0e12',
      panel: '#141519',
      surface: '#1a1c22',
      hover: '#21232a',
      elevated: '#21232a',
    },
    text: {
      primary: '#d8d7dc',
      secondary: '#8a8b94',
      muted: '#5a5b64',
      accent: '#c47a5a',
    },
    chat: {
      user: 'rgba(196, 122, 90, 0.18)',
      assistant: 'rgba(26, 28, 34, 0.78)',
      system: 'rgba(255,255,255,0.06)',
    },
    status: {
      connected: '#6fae7f',
      connecting: '#c79454',
      disconnected: '#c96b6b',
      thinking: '#c47a5a',
      speaking: '#6fae7f',
      idle: '#8a8b94',
    },
    border: '#26282f',
    accent: '#c47a5a',
    accentHover: '#d08766',
    danger: '#c96b6b',
    dangerHover: '#d9807f',
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
    titleBarHeight: 36,
  },
} as const

export type Theme = typeof theme

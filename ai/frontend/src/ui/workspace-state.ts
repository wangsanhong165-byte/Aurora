export type DrawerSection =
  | 'chat'
  | 'character'
  | 'memory'
  | 'voice'
  | 'capabilities'
  | 'settings'
  | 'developer'

export interface DrawerState {
  active: DrawerSection | null
  width: number
}

export type DrawerAction =
  | { type: 'select'; section: DrawerSection }
  | { type: 'resize'; width: number }

export const MIN_DRAWER_WIDTH = 320
export const MAX_DRAWER_WIDTH = 520
export const DEFAULT_DRAWER_WIDTH = 380

const DRAWER_SECTIONS: DrawerSection[] = [
  'chat',
  'character',
  'memory',
  'voice',
  'capabilities',
  'settings',
  'developer',
]

export function clampDrawerWidth(width: number): number {
  return Math.min(MAX_DRAWER_WIDTH, Math.max(MIN_DRAWER_WIDTH, Math.round(width)))
}

export function createInitialDrawerState(
  storedActive: string | null,
  storedWidth: number,
): DrawerState {
  const active = storedActive === 'closed'
    ? null
    : DRAWER_SECTIONS.includes(storedActive as DrawerSection)
      ? storedActive as DrawerSection
      : 'chat'
  return {
    active,
    width: Number.isFinite(storedWidth) && storedWidth > 0
      ? clampDrawerWidth(storedWidth)
      : DEFAULT_DRAWER_WIDTH,
  }
}

export function reduceDrawerState(state: DrawerState, action: DrawerAction): DrawerState {
  if (action.type === 'resize') {
    return { ...state, width: clampDrawerWidth(action.width) }
  }
  return {
    ...state,
    active: state.active === action.section ? null : action.section,
  }
}

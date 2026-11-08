import type { Person } from '../types'

// Fixed categorical order (validated for CVD in light + dark). Colour follows the person, never rank.
export const PEOPLE: Person[] = ['Peter', 'Dom', 'Russell', 'Simon']

export const personVar: Record<Person, string> = {
  Peter: 'var(--series-1)',
  Dom: 'var(--series-2)',
  Russell: 'var(--series-3)',
  Simon: 'var(--series-4)',
}

export const avatarUrl = (p: Person) => `/avatars/${p.toLowerCase()}.jpg`

export const LEAGUE_NAMES: Record<string, string> = {
  E0: 'Premier League', E1: 'Championship', E2: 'League One', E3: 'League Two', EC: 'National League',
  SC0: 'Scottish Premiership', SC1: 'Scottish Championship', SC2: 'Scottish League One', SC3: 'Scottish League Two',
}

const BET_LABELS: Record<string, string> = {
  win: 'to win', draw: 'draw', double_chance: 'win or draw', over_goals: 'over', under_goals: 'under',
  btts: 'both teams to score', btts_no: 'not both to score', team_over_goals: 'team over', other: 'other',
}

export function describeBets(bets: string): string {
  return bets
    .split('+')
    .map((b) => {
      const [kind, line] = b.split(':')
      return line ? `${BET_LABELS[kind] ?? kind} ${line}` : (BET_LABELS[kind] ?? kind)
    })
    .join(' & ')
}

export const gbp = (n: number, signed = false) =>
  `${signed && n > 0 ? '+' : n < 0 ? '−' : ''}£${Math.abs(n).toLocaleString('en-GB', { maximumFractionDigits: 0 })}`

export const pct = (n: number | null) => (n === null ? '–' : `${Math.round(n * 100)}%`)

// Mirrors pipeline/src/aker/admin.py (Firestore documents).
import type { Person } from '../types'

export type Reason = 'missing' | 'unsure' | 'unsettleable' | 'no_fixture'

export interface QueuePick {
  team: string
  bets: string[]
  selection_text: string
  source: string
}

export interface FixtureRow {
  home: string
  away: string
  league: string
  score: string | null
}

export interface QueueItem {
  id: string // `${matchday}_${person}`
  matchday: string
  person: Person
  reason: Reason
  current: QueuePick | null
  slip_teams: string[]
  placer: string
  week_picks: Partial<Record<Person, QueuePick>>
  fixtures: FixtureRow[]
  chat: string
}

export interface LabelDoc {
  matchday: string
  person: Person
  team: string | null // null = no pick that week
  bets: string[]
}

// Mirrors pipeline/src/aker/report.py (written to public/data/report.json).

export type Person = 'Dom' | 'Peter' | 'Russell' | 'Simon'
export type Outcome = 'won' | 'lost' | 'unsettled'

export interface Leg {
  person: Person
  team: string
  opponent: string | null
  home: boolean | null
  league: string | null
  bets: string // e.g. "win", "over_goals:2.5", "win+over_goals:2.5"
  selection_text: string
  outcome: Outcome
  score: string | null // from the picked team's side
  odds: number | null
  odds_estimated: boolean
  probability: number | null
}

export interface Week {
  matchday: string // ISO date
  placer: Person | 'unknown'
  legs: Leg[]
  complete: boolean
  won: boolean
  odds: number | null
  returned: number | null
}

export interface PersonStats {
  person: Person
  legs: number
  settled: number
  won: number
  hit_rate: number | null
  expected_wins: number
  luck: number
  average_odds: number | null
  sole_loser: number
  singles_profit: number
  scottish_legs: number
}

export interface ScottishQuestion {
  peter_share: number
  others_share: number
  odds_ratio: number | null
  p_value: number
  verdict: string
}

export interface Summary {
  weeks: number
  weeks_settled: number
  weeks_won: number
  staked: number
  returned: number
  profit: number
  biggest_win: Week | null
}

export interface Report {
  generated_at: string
  people: Person[]
  summary: Summary
  leaderboard: PersonStats[]
  scottish: ScottishQuestion
  weeks: Week[]
}

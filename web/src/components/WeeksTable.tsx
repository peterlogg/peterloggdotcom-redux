import { useState } from 'react'
import { describeBets, gbp, LEAGUE_NAMES } from '../lib/people'
import type { Leg, Week } from '../types'
import { Avatar } from './Avatar'

const OUTCOME_ICON = { won: '✓', lost: '✗', unsettled: '?' } as const
const PAGE = 15

function LegRow({ leg }: { leg: Leg }) {
  const vs = leg.opponent ? `${leg.home ? 'v' : '@'} ${leg.opponent}` : 'fixture not found'
  const detail = [describeBets(leg.bets), leg.score, leg.odds && `${leg.odds.toFixed(2)}${leg.odds_estimated ? '*' : ''}`]
    .filter(Boolean)
    .join(' · ')
  return (
    <div className="leg" title={leg.league ? LEAGUE_NAMES[leg.league] : undefined}>
      <span className={`outcome ${leg.outcome}`} aria-label={leg.outcome}>{OUTCOME_ICON[leg.outcome]}</span>
      <Avatar person={leg.person} size="sm" />
      <span>
        <span className="team">{leg.team}</span> <span className="muted">{vs}</span>
        <span className="muted hide-sm"> · {detail}</span>
      </span>
    </div>
  )
}

function Result({ week }: { week: Week }) {
  if (!week.complete) return <span className="badge partial">incomplete</span>
  return week.won ? <span className="badge won">✓ {gbp(week.returned ?? 0)}</span> : <span className="badge lost">✗ lost</span>
}

export function WeeksTable({ weeks }: { weeks: Week[] }) {
  const [shown, setShown] = useState(PAGE)
  const recent = [...weeks].reverse()
  return (
    <>
      <div className="table-wrap">
        <table className="weeks">
          <thead>
            <tr>
              <th>Date</th>
              <th>Legs</th>
              <th className="right hide-sm">Odds</th>
              <th className="right">Result</th>
            </tr>
          </thead>
          <tbody>
            {recent.slice(0, shown).map((w) => (
              <tr key={w.matchday}>
                <td>
                  {new Date(w.matchday).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}
                  {w.placer !== 'unknown' && <div className="muted">placed by {w.placer}</div>}
                </td>
                <td>
                  <div className="legs">{w.legs.map((l) => <LegRow key={l.person} leg={l} />)}</div>
                </td>
                <td className="right hide-sm">{w.odds ? `${w.odds.toFixed(1)}` : '–'}</td>
                <td className="right"><Result week={w} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {shown < recent.length && (
        <button className="more" onClick={() => setShown((n) => n + PAGE * 2)}>
          Show more weeks ({recent.length - shown} left)
        </button>
      )}
      <p className="muted">* odds estimated from a goals model (no bookie price for that market). Odds are Bet365 closing prices, not necessarily what we got.</p>
    </>
  )
}

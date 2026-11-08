import type { CSSProperties } from 'react'
import { gbp, pct, personVar } from '../lib/people'
import type { PersonStats } from '../types'
import { Avatar } from './Avatar'

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="stat">
      <div className="v">{value}</div>
      <div className="k">{label}</div>
    </div>
  )
}

export function Leaderboard({ stats }: { stats: PersonStats[] }) {
  return (
    <div className="people">
      {stats.map((s, i) => (
        <article key={s.person} className="card person" style={{ '--person': personVar[s.person] } as CSSProperties}>
          <div className="person-head">
            <Avatar person={s.person} />
            <h3>{s.person}</h3>
            <span className="rank">#{i + 1}</span>
          </div>
          <div className="person-stats">
            <Stat value={pct(s.hit_rate)} label={`hit rate (${s.won}/${s.settled})`} />
            <Stat value={`${s.luck > 0 ? '+' : ''}${s.luck.toFixed(1)}`} label="wins vs bookies' expectation" />
            <Stat value={s.average_odds?.toFixed(2) ?? '–'} label="average odds" />
            <Stat value={String(s.sole_loser)} label="weeks sunk alone" />
            <Stat value={gbp(s.singles_profit, true)} label="£5 singles profit" />
            <Stat value={String(s.scottish_legs)} label="Scottish picks" />
          </div>
        </article>
      ))}
    </div>
  )
}

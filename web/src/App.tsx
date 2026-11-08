import { useEffect, useState } from 'react'
import { ProfitChart, ScottishChart } from './components/Charts'
import { Leaderboard } from './components/Leaderboard'
import { WeeksTable } from './components/WeeksTable'
import { gbp, pct } from './lib/people'
import type { Report } from './types'

function useReport() {
  const [report, setReport] = useState<Report | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    fetch('/data/report.json')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setReport)
      .catch((e: Error) => setError(e.message))
  }, [])
  return { report, error }
}

function Tile({ value, label }: { value: string; label: string }) {
  return (
    <div className="card tile">
      <div className="value">{value}</div>
      <div className="label">{label}</div>
    </div>
  )
}

export default function App() {
  const { report, error } = useReport()
  if (error) return <main className="page"><p>Couldn't load the stats ({error}).</p></main>
  if (!report) return <main className="page"><p className="muted">Loading…</p></main>

  const { summary: s, scottish } = report
  const winRate = s.weeks_settled ? s.weeks_won / s.weeks_settled : null
  const first = report.weeks[0]?.matchday.slice(0, 4)

  return (
    <main className="page">
      <header className="header">
        <h1>The Aker</h1>
        <p className="lede">
          Every Saturday since {first}, four of us each pick a 3pm game and one of us puts £20 on the accumulator.
          Who's actually good at this, and does Peter pick Scottish teams more than everyone else?
        </p>
      </header>

      <section className="tiles" aria-label="Headline numbers">
        <Tile value={String(s.weeks)} label="Saturdays of picks" />
        <Tile value={`${s.weeks_won}/${s.weeks_settled}`} label={`akers won (${pct(winRate)}) of full weeks`} />
        <Tile value={gbp(s.profit, true)} label={`profit on ${gbp(s.staked)} staked`} />
        <Tile value={s.biggest_win ? gbp(s.biggest_win.returned ?? 0) : '–'} label={
          s.biggest_win ? `biggest win, ${new Date(s.biggest_win.matchday).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })}` : 'biggest win'
        } />
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Who's the best?</h2>
          <p className="muted">
            Ranked by hit rate. "Wins vs bookies' expectation" compares actual wins with what the odds said you'd get:
            positive means you beat the market (or got lucky).
          </p>
        </div>
        <Leaderboard stats={report.leaderboard} />
      </section>

      <section className="section card">
        <div className="section-head">
          <h2>Does Peter pick Scottish teams?</h2>
          <p className="verdict">{scottish.verdict}</p>
          <p className="muted">
            Fisher's exact test, Peter vs the other three: p {scottish.p_value < 0.001 ? '< 0.001' : `= ${scottish.p_value}`}.
          </p>
        </div>
        <ScottishChart stats={report.leaderboard} />
      </section>

      <section className="section card">
        <div className="section-head">
          <h2>Running profit</h2>
          <p className="muted">£20 a week, counting only weeks where all four picks are known. Dots are winning weeks.</p>
        </div>
        <ProfitChart weeks={report.weeks} />
      </section>

      <section className="section card">
        <div className="section-head">
          <h2>Every week</h2>
        </div>
        <WeeksTable weeks={report.weeks} />
      </section>

      <footer className="muted">
        Picks extracted from our WhatsApp chat; results and odds from football-data.co.uk. Updated{' '}
        {new Date(report.generated_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })}.
      </footer>
    </main>
  )
}

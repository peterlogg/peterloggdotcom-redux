import * as Plot from '@observablehq/plot'
import { useCallback } from 'react'
import { PEOPLE, gbp } from '../lib/people'
import type { PersonStats, Week } from '../types'
import { PlotFigure, cssVar } from './PlotFigure'

const seriesColour = (i: number) => cssVar(`--series-${i + 1}`)

function axisStyle() {
  return { color: cssVar('--text-secondary'), background: 'transparent', fontSize: '12px', fontFamily: 'inherit' }
}

/** Cumulative profit of the £20 aker, over weeks with all four legs settled. */
export function ProfitChart({ weeks }: { weeks: Week[] }) {
  const render = useCallback(
    (width: number) => {
      let running = 0
      const data = weeks
        .filter((w) => w.returned !== null)
        .map((w) => {
          running += (w.returned ?? 0) - 20
          return { date: new Date(w.matchday), profit: running, won: w.won, returned: w.returned ?? 0, odds: w.odds }
        })
      const ink = cssVar('--text-primary')
      return Plot.plot({
        width,
        height: 280,
        marginLeft: 52,
        style: axisStyle(),
        x: { type: 'utc', label: null },
        y: { label: 'Profit (£)', grid: true, tickFormat: (d: number) => gbp(d) },
        marks: [
          Plot.gridY({ stroke: cssVar('--grid'), strokeOpacity: 1 }),
          Plot.ruleY([0], { stroke: cssVar('--text-muted') }),
          Plot.lineY(data, { x: 'date', y: 'profit', stroke: seriesColour(0), strokeWidth: 2, curve: 'step-after' }),
          Plot.dot(data.filter((d) => d.won), {
            x: 'date', y: 'profit', r: 4, fill: seriesColour(0), stroke: cssVar('--surface-1'), strokeWidth: 2,
          }),
          Plot.ruleX(data, Plot.pointerX({ x: 'date', stroke: ink, strokeOpacity: 0.25 })),
          Plot.tip(data, Plot.pointerX({
            x: 'date', y: 'profit',
            title: (d: (typeof data)[number]) =>
              `${d.date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}\n` +
              `${d.won ? `Won ${gbp(d.returned)} at ${d.odds?.toFixed(1)}/1` : 'Lost £20'}\n` +
              `Running total ${gbp(d.profit, true)}`,
            fill: cssVar('--surface-1'), stroke: cssVar('--border'),
          })),
        ],
      })
    },
    [weeks],
  )
  return <PlotFigure render={render} ariaLabel="Cumulative aker profit over time" />
}

/** Share of each person's legs that were on Scottish teams. */
export function ScottishChart({ stats }: { stats: PersonStats[] }) {
  const render = useCallback(
    (width: number) => {
      const data = PEOPLE.map((person, i) => {
        const s = stats.find((x) => x.person === person)!
        return { person, share: s.settled ? s.scottish_legs / s.settled : 0, n: s.scottish_legs, of: s.settled, i }
      })
      return Plot.plot({
        width,
        height: 190,
        marginLeft: 70,
        marginRight: 56,
        style: axisStyle(),
        x: { label: null, tickFormat: '%', domain: [0, Math.max(0.25, ...data.map((d) => d.share)) * 1.1], grid: true },
        y: { label: null, domain: PEOPLE, padding: 0.3 },
        marks: [
          Plot.gridX({ stroke: cssVar('--grid'), strokeOpacity: 1 }),
          Plot.barX(data, {
            x: 'share', y: 'person', fill: (d: (typeof data)[number]) => seriesColour(d.i), rx: 4,
            tip: { fill: cssVar('--surface-1'), stroke: cssVar('--border') },
            title: (d: (typeof data)[number]) => `${d.person}: ${d.n} of ${d.of} picks Scottish`,
          }),
          Plot.ruleX([0], { stroke: cssVar('--text-muted') }),
          Plot.text(data, {
            x: 'share', y: 'person', text: (d: (typeof data)[number]) => `${Math.round(d.share * 100)}%`,
            dx: 8, textAnchor: 'start', fill: cssVar('--text-primary'), fontWeight: 600,
          }),
        ],
      })
    },
    [stats],
  )
  return <PlotFigure render={render} ariaLabel="Share of picks on Scottish teams, per person" />
}

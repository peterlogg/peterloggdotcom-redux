import { onAuthStateChanged } from 'firebase/auth'
import type { User } from 'firebase/auth'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Avatar } from '../components/Avatar'
import { describeBets } from '../lib/people'
import {
  auth, completeEmailLink, loadLabels, loadQueue, saveLabel, sendEmailLink, signInWithGoogle, signOutAdmin,
} from './firebase'
import type { LabelDoc, QueueItem, Reason } from './types'
import './admin.css'

const REASONS: { key: Reason | 'done'; label: string }[] = [
  { key: 'missing', label: 'Missing' },
  { key: 'unsure', label: 'Unsure' },
  { key: 'no_fixture', label: 'No fixture' },
  { key: 'unsettleable', label: "Can't settle" },
  { key: 'done', label: 'Labelled' },
]

const BET_TYPES = ['win', 'draw', 'double_chance', 'over_goals', 'under_goals', 'btts', 'btts_no', 'team_over_goals']
const NEEDS_LINE = new Set(['over_goals', 'under_goals', 'team_over_goals'])

function useAdminUser() {
  const [user, setUser] = useState<User | null | undefined>(undefined)
  const [linkError, setLinkError] = useState<string | null>(null)
  useEffect(() => {
    completeEmailLink().catch((e: Error) => setLinkError(e.message))
    return onAuthStateChanged(auth, setUser)
  }, [])
  return { user, linkError }
}

function SignIn({ error }: { error: string | null }) {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)
  async function send(e: React.FormEvent) {
    e.preventDefault()
    setSendError(null)
    try {
      await sendEmailLink(email.trim())
      setSent(true)
    } catch (err) {
      setSendError((err as Error).message)
    }
  }
  return (
    <main className="page admin-gate">
      <h1>Aker admin</h1>
      <button className="primary" onClick={() => signInWithGoogle()}>Sign in with Google</button>
      <p className="muted">or, for Hotmail / Outlook / other addresses:</p>
      {sent ? (
        <p>Check {email} for a sign-in link (it may land in junk). Open it on this device.</p>
      ) : (
        <form className="email-form" onSubmit={send}>
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@hotmail.com" />
          <button type="submit">Email me a sign-in link</button>
        </form>
      )}
      {(error || sendError) && <p className="error">{error ?? sendError}</p>}
    </main>
  )
}

export default function Admin() {
  const { user, linkError } = useAdminUser()
  if (user === undefined) return <main className="page"><p className="muted">Checking sign-in…</p></main>
  if (!user) return <SignIn error={linkError} />
  return <Labeller email={user.email ?? ''} />
}

function NotAdmin({ email }: { email: string }) {
  return (
    <main className="page admin-gate">
      <p>{email} isn't on the admin list. Ask Peter to add it.</p>
      <button onClick={() => signOutAdmin()}>Sign out</button>
    </main>
  )
}

function Labeller({ email }: { email: string }) {
  const [queue, setQueue] = useState<QueueItem[]>([])
  const [labels, setLabels] = useState<Map<string, LabelDoc>>(new Map())
  const [tab, setTab] = useState<Reason | 'done'>('missing')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [denied, setDenied] = useState(false)

  useEffect(() => {
    Promise.all([loadQueue(), loadLabels()])
      .then(([q, l]) => { setQueue(q); setLabels(l) })
      .catch((e: { code?: string; message: string }) =>
        e.code === 'permission-denied' ? setDenied(true) : setError(e.message))
  }, [])

  const visible = useMemo(
    () => queue.filter((i) => (tab === 'done' ? labels.has(i.id) : i.reason === tab && !labels.has(i.id))),
    [queue, labels, tab],
  )
  const counts = useMemo(() => {
    const c: Record<string, number> = { done: 0 }
    for (const i of queue) {
      if (labels.has(i.id)) c.done++
      else c[i.reason] = (c[i.reason] ?? 0) + 1
    }
    return c
  }, [queue, labels])

  const selected = queue.find((i) => i.id === selectedId) ?? visible[0] ?? null

  const onSaved = useCallback((id: string, label: LabelDoc) => {
    setLabels((prev) => new Map(prev).set(id, label))
    const idx = visible.findIndex((i) => i.id === id)
    setSelectedId(visible[idx + 1]?.id ?? null)
  }, [visible])

  if (denied) return <NotAdmin email={email} />

  return (
    <main className="admin">
      <header className="admin-bar">
        <strong>Aker admin</strong>
        <nav className="tabs">
          {REASONS.map((r) => (
            <button key={r.key} className={tab === r.key ? 'active' : ''} onClick={() => { setTab(r.key); setSelectedId(null) }}>
              {r.label} <span className="count">{counts[r.key] ?? 0}</span>
            </button>
          ))}
        </nav>
        <span className="muted">{email}</span>
        <button onClick={() => signOutAdmin()}>Sign out</button>
      </header>
      {error && <p className="error">{error}</p>}
      <div className="admin-body">
        <ul className="queue">
          {visible.map((i) => (
            <li key={i.id}>
              <button className={i.id === selected?.id ? 'active' : ''} onClick={() => setSelectedId(i.id)}>
                <Avatar person={i.person} size="sm" />
                <span>{i.matchday}</span>
                <span className="muted">{labels.get(i.id)?.team ?? i.current?.team ?? (i.slip_teams.length ? `slip: ${i.slip_teams.join(', ')}` : '')}</span>
              </button>
            </li>
          ))}
          {visible.length === 0 && <li className="muted pad">Nothing here 🎉</li>}
        </ul>
        {selected ? <ItemPanel key={selected.id} item={selected} label={labels.get(selected.id)} onSaved={onSaved} /> : <div />}
      </div>
    </main>
  )
}

function ItemPanel({ item, label, onSaved }: { item: QueueItem; label?: LabelDoc; onSaved: (id: string, l: LabelDoc) => void }) {
  const initialBet = (label?.bets[0] ?? item.current?.bets[0] ?? 'win').split(':')
  const [team, setTeam] = useState(label?.team ?? item.current?.team ?? item.slip_teams[0] ?? '')
  const [betType, setBetType] = useState(initialBet[0])
  const [line, setLine] = useState(initialBet[1] ?? '2.5')
  const [saving, setSaving] = useState(false)

  const teams = useMemo(
    () => [...new Set(item.fixtures.flatMap((f) => [f.home, f.away]))].sort(),
    [item.fixtures],
  )
  async function save(teamValue: string | null) {
    setSaving(true)
    const bets = teamValue ? [NEEDS_LINE.has(betType) ? `${betType}:${line}` : betType] : []
    const doc: LabelDoc = { matchday: item.matchday, person: item.person, team: teamValue, bets }
    await saveLabel(item.id, doc)
    setSaving(false)
    onSaved(item.id, doc)
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <Avatar person={item.person} />
        <div>
          <h2>{item.person} · {new Date(item.matchday).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })}</h2>
          <p className="muted">
            {item.reason.replace('_', ' ')} · placed by {item.placer}
            {item.current && ` · currently: ${item.current.team} (${describeBets(item.current.bets.join('+'))}, "${item.current.selection_text}")`}
          </p>
        </div>
      </div>

      <div className="week-picks">
        <span className="muted">This week:</span>
        {Object.entries(item.week_picks).map(([p, pick]) => (
          <span key={p} className="chip" title={pick?.selection_text ? `"${pick.selection_text}"` : undefined}>
            {p}: {pick?.team}
          </span>
        ))}
      </div>

      {item.slip_teams.length > 0 && (
        <div className="hints">
          <span className="muted">Unaccounted for on the bet slip:</span>
          {item.slip_teams.map((t) => <button key={t} className="chip pick" onClick={() => setTeam(t)}>{t}</button>)}
        </div>
      )}

      <div className="form">
        <label>
          Team
          <input list="teams" value={team} onChange={(e) => setTeam(e.target.value)} placeholder="Club" />
          <datalist id="teams">{teams.map((t) => <option key={t} value={t} />)}</datalist>
        </label>
        <label>
          Bet
          <select value={betType} onChange={(e) => setBetType(e.target.value)}>
            {BET_TYPES.map((b) => <option key={b} value={b}>{describeBets(b)}</option>)}
          </select>
        </label>
        {NEEDS_LINE.has(betType) && (
          <label>
            Line
            <input value={line} onChange={(e) => setLine(e.target.value)} inputMode="decimal" size={4} />
          </label>
        )}
        <button className="primary" disabled={!team || saving} onClick={() => save(team)}>Save</button>
        <button disabled={saving} onClick={() => save(null)}>No pick this week</button>
      </div>

      <p className="muted">Need context? Scroll back to this weekend in the WhatsApp group; the chat isn't stored here.</p>

      <div className="fixtures">
          <h3>Fixtures that day</h3>
          <ul>
            {item.fixtures.map((f) => (
              <li key={`${f.home}-${f.away}`}>
                <button className="link" onClick={() => setTeam(f.home)}>{f.home}</button>
                {' '}{f.score ?? 'v'}{' '}
                <button className="link" onClick={() => setTeam(f.away)}>{f.away}</button>
                <span className="muted"> · {f.league}</span>
              </li>
            ))}
            {item.fixtures.length === 0 && <li className="muted">No league games found (cup weekend?)</li>}
          </ul>
      </div>
    </section>
  )
}

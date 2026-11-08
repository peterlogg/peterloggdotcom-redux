import { useState } from 'react'
import type { CSSProperties } from 'react'
import { avatarUrl, personVar } from '../lib/people'
import type { Person } from '../types'

export function Avatar({ person, size = 'md' }: { person: Person; size?: 'sm' | 'md' }) {
  const [failed, setFailed] = useState(false)
  const style = { '--person': personVar[person] } as CSSProperties
  const cls = `avatar${size === 'sm' ? ' sm' : ''}`
  if (failed) {
    return (
      <span className={`${cls} avatar-fallback`} style={style} aria-label={person}>
        {person[0]}
      </span>
    )
  }
  return <img className={cls} style={style} src={avatarUrl(person)} alt={person} onError={() => setFailed(true)} />
}

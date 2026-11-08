import { initializeApp } from 'firebase/app'
import {
  GoogleAuthProvider, getAuth, isSignInWithEmailLink, sendSignInLinkToEmail, signInWithEmailLink, signInWithPopup, signOut,
} from 'firebase/auth'
import { collection, doc, getDocs, getFirestore, serverTimestamp, setDoc } from 'firebase/firestore'
import type { LabelDoc, QueueItem } from './types'

// Firebase web config is public by design: access is enforced by Auth + firestore.rules.
const app = initializeApp({
  apiKey: 'AIzaSyAimBNl2I_gTobpH0vqoNJQH9HquQBJfT0',
  authDomain: 'peterloggdotcom-redux.firebaseapp.com',
  projectId: 'peterloggdotcom-redux',
  appId: '1:576884406041:web:4b19826b24d8eaae8c3788',
})

export const auth = getAuth(app)
const db = getFirestore(app)

// Who is an admin is decided only by firestore.rules; the page just reacts to permission errors.

export const signInWithGoogle = () => signInWithPopup(auth, new GoogleAuthProvider())
export const signOutAdmin = () => signOut(auth)

const EMAIL_KEY = 'aker-admin-email'

/** Email a one-click sign-in link (for non-Google addresses like Hotmail). */
export async function sendEmailLink(email: string): Promise<void> {
  await sendSignInLinkToEmail(auth, email, { url: `${window.location.origin}/admin`, handleCodeInApp: true })
  try { localStorage.setItem(EMAIL_KEY, email) } catch { /* private mode: we'll ask again */ }
}

/** If this page was opened from a sign-in email, complete the sign-in. */
export async function completeEmailLink(): Promise<boolean> {
  const href = window.location.href
  if (!isSignInWithEmailLink(auth, href)) return false
  let email: string | null = null
  try { email = localStorage.getItem(EMAIL_KEY) } catch { /* ignore */ }
  email ??= window.prompt('Confirm your email address to finish signing in')
  if (!email) return false
  await signInWithEmailLink(auth, email, href)
  try { localStorage.removeItem(EMAIL_KEY) } catch { /* ignore */ }
  window.history.replaceState(null, '', '/admin')
  return true
}

export async function loadQueue(): Promise<QueueItem[]> {
  const snap = await getDocs(collection(db, 'review_queue'))
  return snap.docs
    .map((d) => ({ id: d.id, ...(d.data() as Omit<QueueItem, 'id'>) }))
    .sort((a, b) => a.matchday.localeCompare(b.matchday) || a.person.localeCompare(b.person))
}

export async function loadLabels(): Promise<Map<string, LabelDoc>> {
  const snap = await getDocs(collection(db, 'labels'))
  return new Map(snap.docs.map((d) => [d.id, d.data() as LabelDoc]))
}

export async function saveLabel(id: string, label: LabelDoc): Promise<void> {
  await setDoc(doc(db, 'labels', id), { ...label, labelled_by: auth.currentUser?.email ?? null, updated_at: serverTimestamp() })
}

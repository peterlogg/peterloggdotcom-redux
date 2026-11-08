import { initializeApp } from 'firebase/app'
import { GoogleAuthProvider, getAuth, signInWithPopup, signOut } from 'firebase/auth'
import { collection, doc, getDocs, getFirestore, serverTimestamp, setDoc } from 'firebase/firestore'
import type { LabelDoc, QueueItem } from './types'

// Public web config (safe to ship); set in web/.env as VITE_FIREBASE_*.
const app = initializeApp({
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
})

export const auth = getAuth(app)
const db = getFirestore(app, 'aker')

export const ADMIN_EMAILS = ['loggpeter@gmail.com', 'loggpeter@googlemail.com']

export const signIn = () => signInWithPopup(auth, new GoogleAuthProvider())
export const signOutAdmin = () => signOut(auth)

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
  await setDoc(doc(db, 'labels', id), { ...label, updated_at: serverTimestamp() })
}

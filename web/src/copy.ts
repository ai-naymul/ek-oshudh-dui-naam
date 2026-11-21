// All wording comes from config/copy_bn.json: built in as a fallback, then refreshed from /api/copy so an on-site edit
// to that file shows up without rebuilding the app.
import { useEffect, useReducer } from 'react'
import shipped from '../../config/copy_bn.json'
import { api } from './api'

type Vars = Record<string, string | number>
let ui: Record<string, string> = (shipped as { ui: Record<string, string> }).ui
const listeners = new Set<() => void>()

export async function refreshCopy() {
  try {
    const r = await api.copy()
    ui = { ...ui, ...r.ui }
    listeners.forEach((f) => f())
  } catch { /* the built-in copy stays */ }
}

export function t(key: string, vars?: Vars): string {
  let s = ui[key] ?? key
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(String(v))
  return s
}

export function useCopy() {
  const [, force] = useReducer((x: number) => x + 1, 0)
  useEffect(() => {
    listeners.add(force)
    return () => { listeners.delete(force) }
  }, [])
  return t
}

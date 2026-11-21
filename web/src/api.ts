// API client. Backend URL: ?api=... > local backend on Vite dev ports > VITE_API > same origin (the backend serves
// this page itself, the normal case). Every response is live, never cached.

function resolveBase(): string {
  const strip = (u: string) => u.replace(/\/$/, '')
  const fromQuery = new URLSearchParams(window.location.search).get('api')
  if (fromQuery) {
    return strip(fromQuery)
  }
  // Vite dev/preview: the local backend on the same machine
  if (['5173', '4173'].includes(window.location.port)) return `http://${window.location.hostname}:8000`
  const fromEnv = import.meta.env.VITE_API as string | undefined
  if (fromEnv) return strip(fromEnv)
  // Otherwise the backend is serving this page itself (one tunnel URL for app + API)
  return window.location.origin
}

export const API = resolveBase()

// Link for another phone: this page plus the backend it is talking to (the QR on the laptop screen encodes it).
export const shareUrl = () => {
  const page = `${window.location.origin}${window.location.pathname}`
  return API === window.location.origin ? page : `${page}?api=${encodeURIComponent(API)}`
}

export type Option = { product_id: number; brand: string; strength: string; form: string; maker: string; generic: string; score: number }
export type ItemView = {
  item_id: string; doc_id: string; source: string; reading: string; alternatives: string[]; handwritten: boolean
  agree: number | null; chosen: { product_id: number; brand: string; strength: string; form: string; maker: string } | null
  confidence: number; method: string; needs_confirm: boolean; options: Option[]
  schedule: { morning: number | null; noon: number | null; night: number | null; per_day: number | null; meal: string | null; days: number | null }
  per_day: number | null; has_crop: boolean
  agent: { product_id: number | null; brand: string | null; reason_bn: string; tools: string[] } | null
  doctor: string | null
  taking: Taking
}
export type Taking = 'current' | 'stopped' | 'unsure'
export type Finding = { rule: string; severity: 'red' | 'amber' | 'info'; title_bn: string; title_en: string; bn: string; en: string; source: string; meds: string[] }
export type Path = { brand: string; strength: string; form: string; maker: string; ingredients: { name: string; strength: string; class: string | null }[] }
export type Medicine = {
  med_id: string; brand: string; strength: string; form: string; path: Path; per_day: number | null; from_rx: boolean
  doctors: string[]; taking: Taking; checked: boolean; monthly_cost: number | null; cheaper: { brand: string; maker: string; unit_price: number }[]; items: string[]
}
export type Stats = {
  products: number; brand_names: number; generics: number
  examples: { ingredient: string; brand_count: number; brands: string[] }[]
  eval: { n_test: number; reader: string; method: string; top1: number; auto_accept: number; auto_error_audited: number | null } | null
}
export type Health = { registry: { products: number; ready: boolean }
  ai: { key_present: boolean; last_ok_at: number | null; last_error_at: number | null; last_error: string | null } }
export type TraceStep = { step: string; ms: number; [k: string]: unknown }
export type CheckResult = { case_id: string; medicines: Medicine[]; findings: Finding[]; unchecked: number; trace: TraceStep[]; policy: Record<string, unknown>; request_id: string; latency_ms: number }

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, { ...init, cache: 'no-store' })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new ApiError(res.status, (body as { detail?: string }).detail || `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  stats: () => call<Stats>('/api/stats'),
  newCase: () => call<{ case_id: string }>('/api/cases', { method: 'POST' }),
  getCase: (cid: string) => call<{ case_id: string; items: ItemView[] }>(`/api/cases/${encodeURIComponent(cid)}`),
  addImage: (cid: string, file: Blob, allowRepeat = false) => {
    const fd = new FormData()
    fd.append('file', file, 'photo.jpg')
    return call<{ doc_id: string | null; duplicate_of: string | null; kind: string; items: ItemView[]; latency_ms: number }>(
      `/api/cases/${cid}/images${allowRepeat ? '?allow_repeat=true' : ''}`, { method: 'POST', body: fd })
  },
  status: (cid: string, iid: string, taking: Taking) =>
    call<ItemView>(`/api/cases/${cid}/items/${iid}/status`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ taking }) }),
  remove: (cid: string, iid: string) => call<{ removed: string }>(`/api/cases/${cid}/items/${iid}`, { method: 'DELETE' }),
  health: () => call<Health>('/api/health'),
  sample: () => call<{ case_id: string; sample: boolean; items: ItemView[] }>('/api/cases/sample', { method: 'POST' }),
  copy: () => call<{ ui: Record<string, string> }>('/api/copy'),
  network: () => call<{ urls: string[] }>('/api/network'),
  addText: (cid: string, text: string) =>
    call<{ items: ItemView[] }>(`/api/cases/${cid}/text`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) }),
  confirm: (cid: string, iid: string, product_id: number | null, per_day?: number | null) =>
    call<ItemView>(`/api/cases/${cid}/items/${iid}/confirm`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ product_id, per_day }) }),
  addVoice: (cid: string, audio: Blob) => {
    const fd = new FormData()
    const ext = audio.type.includes('mp4') ? 'm4a' : 'webm'
    fd.append('file', new File([audio], `voice.${ext}`, { type: audio.type.split(';')[0] }))
    return call<{ transcript: string; items: ItemView[]; latency_ms: number }>(`/api/cases/${cid}/voice`, { method: 'POST', body: fd })
  },
  speech: async (cid: string): Promise<Blob> => {
    const res = await fetch(`${API}/api/cases/${cid}/speech`, { cache: 'no-store' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return res.blob()
  },
  resolve: (cid: string, iid: string) => call<ItemView>(`/api/cases/${cid}/items/${iid}/resolve`, { method: 'POST' }),
  check: (cid: string) => call<CheckResult>(`/api/cases/${cid}/check`),
  search: (q: string) => call<{ options: Option[]; path: Path | null; latency_ms: number; request_id: string }>(`/api/brands/search?q=${encodeURIComponent(q)}`),
  random: () => call<{ brand: string; path: Path; latency_ms: number; request_id: string }>('/api/brands/random'),
  cropUrl: (cid: string, iid: string) => `${API}/api/cases/${cid}/items/${iid}/crop.jpg`,
}

// Shrink photos on the phone before upload (~1600 px JPEG): 4 MB -> ~300 KB on a hotspot.
export async function shrink(file: File, max = 1600): Promise<Blob> {
  const bitmap = await createImageBitmap(file)
  const scale = Math.min(1, max / Math.max(bitmap.width, bitmap.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(bitmap.width * scale)
  canvas.height = Math.round(bitmap.height * scale)
  canvas.getContext('2d')!.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  return new Promise((resolve) => canvas.toBlob((b) => resolve(b || file), 'image/jpeg', 0.88))
}

export const bn = (n: number | string) => String(n).replace(/[0-9]/g, (d) => '০১২৩৪৫৬৭৮৯'[Number(d)])
export const bnInt = (n: number) => bn(n.toLocaleString('en-IN'))
export const bnPct = (x: number) => `${bn((x * 100).toFixed(1).replace(/\.0$/, ''))}%`

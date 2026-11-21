// API client. Backend URL: ?api=... (the QR carries the tunnel URL) > local backend on Vite ports > VITE_API >
// last QR-given backend (Pages only) > same origin (backend serves the app). Every response is live, never cached.

function resolveBase(): string {
  const strip = (u: string) => u.replace(/\/$/, '')
  const fromQuery = new URLSearchParams(window.location.search).get('api')
  if (fromQuery) {
    try { localStorage.setItem('api', fromQuery) } catch { /* private mode */ }
    return strip(fromQuery)
  }
  // Vite dev/preview: the local backend on the same machine
  if (['5173', '4173'].includes(window.location.port)) return `http://${window.location.hostname}:8000`
  const fromEnv = import.meta.env.VITE_API as string | undefined
  if (fromEnv) return strip(fromEnv)
  // Cloudflare Pages has no API of its own: use the backend this phone was last given by a QR code
  if (window.location.hostname.endsWith('.pages.dev')) {
    try { const saved = localStorage.getItem('api'); if (saved) return strip(saved) } catch { /* ignore */ }
  }
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
}
export type Finding = { rule: string; severity: 'red' | 'amber' | 'info'; title_bn: string; title_en: string; bn: string; en: string; source: string; meds: string[] }
export type Path = { brand: string; strength: string; form: string; maker: string; ingredients: { name: string; strength: string; class: string | null }[] }
export type Medicine = {
  med_id: string; brand: string; strength: string; form: string; path: Path; per_day: number | null; from_rx: boolean
  doctors: string[]; monthly_cost: number | null; cheaper: { brand: string; maker: string; unit_price: number }[]; items: string[]
}
export type TraceStep = { step: string; ms: number; [k: string]: unknown }
export type CheckResult = { case_id: string; medicines: Medicine[]; findings: Finding[]; trace: TraceStep[]; policy: Record<string, unknown>; request_id: string; latency_ms: number }

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, { ...init, cache: 'no-store' })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error((body as { detail?: string }).detail || `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  newCase: () => call<{ case_id: string }>('/api/cases', { method: 'POST' }),
  addImage: (cid: string, file: Blob) => {
    const fd = new FormData()
    fd.append('file', file, 'photo.jpg')
    return call<{ doc_id: string; kind: string; items: ItemView[]; latency_ms: number }>(`/api/cases/${cid}/images`, { method: 'POST', body: fd })
  },
  addText: (cid: string, text: string) =>
    call<{ items: ItemView[] }>(`/api/cases/${cid}/text`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) }),
  confirm: (cid: string, iid: string, product_id: number | null, per_day?: number | null) =>
    call<ItemView>(`/api/cases/${cid}/items/${iid}/confirm`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ product_id, per_day }) }),
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

import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { AlertTriangle, AlertOctagon, Info, Search, Shuffle, Share2, X, Loader2, Volume2, Pause } from 'lucide-react'
import { drawCard, shareCard } from './card'
import { api, bn, type CheckResult, type Path } from './api'
import { MedicineGraph } from './Welcome'

const spring = { type: 'spring' as const, bounce: 0, duration: 0.5 }
const STYLE = {
  red: { box: 'bg-danger-soft border-danger/30', text: 'text-danger', icon: <AlertOctagon />, word: 'সতর্কতা' },
  amber: { box: 'bg-warn-soft border-warn/30', text: 'text-warn', icon: <AlertTriangle />, word: 'খেয়াল রাখুন' },
  info: { box: 'bg-white border-line', text: 'text-muted', icon: <Info />, word: 'তথ্য' },
}

export function Results({ result, onBack }: { result: CheckResult; onBack: () => void }) {
  const [tab, setTab] = useState<'result' | 'proof'>('result')
  const [card, setCard] = useState(false)
  const dup = result.findings.find((f) => f.rule === 'DUP_INGREDIENT')
  const reds = result.findings.filter((f) => f.severity === 'red').length
  return (
    <motion.main className="mx-auto max-w-xl px-4 pb-16 pt-3" initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -24 }} transition={spring}>
      <div className="glass sticky top-0 z-10 -mx-4 mb-3 flex gap-2 px-4 py-2">
        {(['result', 'proof'] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`relative flex-1 rounded-xl py-2 font-semibold ${tab === t ? 'text-white' : 'text-muted'}`}>
            {tab === t && <motion.span layoutId="tab" className="absolute inset-0 rounded-xl bg-ink" transition={spring} />}
            <span className="relative">{t === 'result' ? 'ফলাফল' : 'কীভাবে বুঝলাম'}</span>
          </button>
        ))}
      </div>
      {tab === 'result' ? (
        <>
          <h2 className="display text-[1.6rem]">{reds ? `${bn(reds)}টি গুরুত্বপূর্ণ সতর্কতা` : 'আমাদের যাচাইয়ে বড় কোনো সমস্যা পাওয়া যায়নি'}</h2>
          {dup && <div className="card mt-3 flex justify-center p-3">
            <MedicineGraph a={(dup.meds.length && result.medicines.find((m) => m.med_id === dup.meds[0])?.brand) || 'A'}
              b={(result.medicines.find((m) => m.med_id === dup.meds[1])?.brand) || 'B'}
              ingredient={result.medicines.find((m) => m.med_id === dup.meds[0])?.path.ingredients[0]?.name || ''} /></div>}
          <div className="mt-4 space-y-3">
            {result.findings.map((f, i) => {
              const s = STYLE[f.severity]
              return (
                <motion.div key={i} className={`rounded-[22px] border p-4 ${s.box}`} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay: 0.08 * i }}>
                  <p className={`flex items-center gap-2 font-bold ${s.text}`}>{s.icon}{s.word}: {f.title_bn}</p>
                  <p className="mt-1 text-[17px]">{f.bn}</p>
                  <p className="mt-1 font-sans text-sm text-muted">{f.en}</p>
                  <p className="mt-2 font-sans text-xs text-muted">Source: {f.source}</p>
                </motion.div>
              )
            })}
          </div>
          <div className="mt-4 grid grid-cols-[auto_1fr] gap-3">
            <Listen caseId={result.case_id} />
            <motion.button whileTap={{ scale: 0.97 }} onClick={() => setCard(true)}
              className="flex items-center justify-center gap-2 rounded-2xl bg-brand py-4 text-lg font-semibold text-white shadow-lg shadow-brand/20">
              <Share2 size={20} /> <span className="whitespace-nowrap">ছবি কার্ড · শেয়ার</span>
            </motion.button>
          </div>
          <AnimatePresence>{card && <CardSheet result={result} onClose={() => setCard(false)} />}</AnimatePresence>
          <h3 className="mt-6 text-lg font-bold">আপনার ওষুধগুলো</h3>
          <div className="mt-2 space-y-2">
            {result.medicines.map((m) => (
              <div key={m.med_id} className="card p-3">
                <p className="font-sans font-bold">{m.brand} <span className="font-medium text-muted">{m.strength}</span></p>
                <p className="font-sans text-xs text-muted">{m.form}</p>
                <p className="font-sans text-sm text-muted">→ {m.path.ingredients.map((x) => x.name).join(' + ')}{m.path.ingredients[0]?.class ? ` · ${m.path.ingredients[0].class}` : ''}</p>
                <p className="text-sm text-muted">{m.from_rx ? `প্রেসক্রিপশন: ${m.doctors.join(', ')}` : 'শুধু ব্যাগে (প্রেসক্রিপশনে নেই)'}{m.monthly_cost != null && ` · মাসে প্রায় ৳${bn(Math.round(m.monthly_cost))}`}</p>
                {m.cheaper.length > 0 && <p className="mt-1 text-sm text-brand">একই ওষুধ কম দামে তালিকায় আছে: {m.cheaper.map((c) => `${c.brand} ৳${bn(c.unit_price)}`).join(', ')} (শুধু তথ্য; বদলানোর আগে ডাক্তারকে জিজ্ঞেস করুন)</p>}
              </div>
            ))}
          </div>
          <button onClick={onBack} className="mt-6 w-full rounded-2xl border border-line bg-white py-3 font-semibold">আরও ওষুধ যোগ করুন</button>
        </>
      ) : <Proof result={result} />}
    </motion.main>
  )
}

// Bangla voice reply: the template text of the findings, spoken by the TTS model on the server.
function Listen({ caseId }: { caseId: string }) {
  const [state, setState] = useState<'idle' | 'loading' | 'playing' | 'error'>('idle')
  const audio = useRef<HTMLAudioElement | null>(null)
  useEffect(() => () => { audio.current?.pause() }, [])
  async function toggle() {
    if (state === 'playing') { audio.current?.pause(); setState('idle'); return }
    setState('loading')
    try {
      const blob = await api.speech(caseId)
      const a = new Audio(URL.createObjectURL(blob))
      a.onended = () => setState('idle')
      audio.current = a
      await a.play()
      setState('playing')
    } catch { setState('error') }
  }
  return (
    <motion.button whileTap={{ scale: 0.95 }} onClick={toggle} aria-label="বাংলায় শুনুন"
      className="flex items-center gap-2 rounded-2xl bg-ink px-4 py-4 text-lg font-semibold text-white">
      {state === 'loading' ? <Loader2 size={20} className="animate-spin" /> : state === 'playing' ? <Pause size={20} /> : <Volume2 size={20} />}
      <span className="whitespace-nowrap">{state === 'error' ? 'আবার' : 'শুনুন'}</span>
    </motion.button>
  )
}

function CardSheet({ result, onClose }: { result: CheckResult; onClose: () => void }) {
  const [url, setUrl] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  useEffect(() => {
    let u: string | null = null
    drawCard(result).then((b) => { u = URL.createObjectURL(b); setUrl(u) })
    return () => { if (u) URL.revokeObjectURL(u) }
  }, [result])
  return (
    <>
      <motion.div className="fixed inset-0 z-40 bg-ink/40" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
      <motion.div role="dialog" aria-label="ছবি কার্ড" className="fixed inset-x-0 bottom-0 z-50 mx-auto flex max-h-[92dvh] max-w-xl flex-col rounded-t-[28px] bg-white px-4 pb-[max(16px,env(safe-area-inset-bottom))] pt-4"
        initial={{ y: '100%' }} animate={{ y: 0 }} exit={{ y: '100%' }} transition={{ type: 'spring', bounce: 0, duration: 0.4 }}>
        <div className="flex items-center justify-between">
          <p className="text-lg font-bold">ছবি কার্ড</p>
          <button onClick={onClose} aria-label="বন্ধ" className="grid h-9 w-9 place-items-center rounded-full bg-paper"><X size={18} /></button>
        </div>
        <div className="mt-3 min-h-0 flex-1 overflow-y-auto rounded-2xl border border-line bg-paper">
          {url ? <img src={url} alt="ফলাফলের ছবি কার্ড" className="w-full" /> : <div className="grid h-60 place-items-center"><Loader2 className="animate-spin text-brand" /></div>}
        </div>
        {note && <p className="mt-2 text-center text-sm text-muted">{note}</p>}
        <motion.button whileTap={{ scale: 0.97 }} disabled={!url} onClick={async () => setNote((await shareCard(result)) === 'shared' ? 'পাঠানো হয়েছে' : 'ছবি ডাউনলোড হয়েছে; হোয়াটসঅ্যাপে লেখা খোলা হয়েছে')}
          className="mt-3 flex w-full items-center justify-center gap-2 rounded-2xl bg-brand py-4 text-lg font-semibold text-white disabled:opacity-40">
          <Share2 size={20} /> শেয়ার করুন
        </motion.button>
      </motion.div>
    </>
  )
}

type Rates = { auto_accept_coverage: number; auto_accept_error: number; asked_in_top3: number; correct_if_user_picks_from_top3: number; wrong_n?: number; accepted_n?: number }
const pct = (x: unknown) => (typeof x === 'number' ? `${(x * 100).toFixed(1)}%` : '–')

// Matching quality, read from models/policy.json (written by training/eval_policy.py): nothing here is typed in by hand.
function EvalCard({ policy }: { policy: Record<string, unknown> }) {
  const test = policy.test as Rates | undefined
  const top1 = policy.top1_test as Record<string, number> | undefined
  if (!test || !top1) return null
  const audited = policy.test_audited as Rates | undefined
  const unseen = policy.unseen_names as { held_out_names: number; R1_top1: number; R2_top1: number } | undefined
  const rows: [string, string, number | undefined][] = [
    ['R1', 'fuzzy string match', top1.R1], ['R2', 'decision model (LightGBM)', top1.R2], ['R3', 'AI picks from top-5', top1.R3],
  ]
  return (
    <div className="card p-4">
      <p className="font-bold">How well does matching work?</p>
      <p className="text-xs text-muted">{String(policy.n_test ?? '')} handwritten medicine words by Bangladeshi doctors, never used for training · reader {String(policy.reader ?? '')}</p>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-muted"><th className="py-1 font-medium">Matcher</th><th className="py-1 text-right font-medium">Top-1 correct</th></tr></thead>
          <tbody>
            {rows.map(([k, label, v]) => (
              <tr key={k} className={String(policy.method).includes(k) ? 'font-semibold' : ''}>
                <td className="whitespace-nowrap py-1">{k} · {label}</td><td className="py-1 text-right tabular-nums">{pct(v)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
        <div className="rounded-lg bg-paper p-2"><p className="text-muted">Accepted automatically</p><p className="text-lg font-bold tabular-nums">{pct(test.auto_accept_coverage)}</p><p className="text-xs text-muted">wrong among them: {pct(test.auto_accept_error)}</p></div>
        <div className="rounded-lg bg-paper p-2"><p className="text-muted">Asked to confirm</p><p className="text-lg font-bold tabular-nums">{pct(1 - test.auto_accept_coverage)}</p><p className="text-xs text-muted">right answer in the 3 shown: {pct(test.asked_in_top3)}</p></div>
      </div>
      {audited && audited.wrong_n !== undefined && (
        <p className="mt-2 text-xs text-muted">We checked every wrong automatic accept against its image: {String(test.wrong_n! - audited.wrong_n)} were mistakes in the dataset's own labels (the image shows the brand we chose). After that check: {String(audited.wrong_n)} wrong of {String(audited.accepted_n)} ({pct(audited.auto_accept_error)}).</p>
      )}
      {unseen && <p className="mt-2 text-xs text-muted">On {unseen.held_out_names} medicine names the decision model never saw: R2 {pct(unseen.R2_top1)} vs R1 {pct(unseen.R1_top1)}.</p>}
      <p className="mt-2 text-xs text-muted">Shipped policy: {String(policy.method)} · thresholds fitted on a separate validation split (≤{pct(policy.max_auto_error)} wrong automatic accepts), reported once on test.</p>
    </div>
  )
}

function Proof({ result }: { result: CheckResult }) {
  const [q, setQ] = useState('')
  const [hit, setHit] = useState<{ title: string; path: Path | null; ms: number; id: string } | null>(null)
  async function search() { if (!q.trim()) return; const r = await api.search(q); setHit({ title: `"${q}" →`, path: r.path, ms: r.latency_ms, id: r.request_id }) }
  async function random() { const r = await api.random(); setHit({ title: `Random: ${r.brand} →`, path: r.path, ms: r.latency_ms, id: r.request_id }) }
  return (
    <div className="space-y-4 font-sans">
      <div className="card p-4">
        <p className="font-bold">Pipeline trace (this request)</p>
        <p className="text-xs text-muted">request {result.request_id} · {result.latency_ms} ms · policy {String(result.policy.method)}</p>
        <ol className="mt-3 space-y-2">
          {result.trace.map((s, i) => (
            <motion.li key={i} className="flex items-baseline justify-between gap-3 rounded-lg bg-paper px-3 py-2 text-sm" initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ ...spring, delay: i * 0.04 }}>
              <span><b>{s.step}</b> {s.step === 'match' ? `"${String(s.reading)}" → ${String(s.chosen)} (${String(s.method)}, ${String(s.confidence)})` : s.step === 'perceive' ? `${String(s.kind)} · ${String(s.lines)} lines · ${String(s.model)}` : `${String(s.findings ?? '')} findings`}</span>
              <span className="shrink-0 text-muted">{s.ms} ms</span>
            </motion.li>
          ))}
        </ol>
      </div>
      <EvalCard policy={result.policy} />
      <div className="card p-4">
        <p className="font-bold">Try any brand (live, 13,627 names)</p>
        <div className="mt-2 flex gap-2">
          <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && search()} placeholder="e.g. Nappa, নাপা, Maxpr0"
            className="min-w-0 flex-1 rounded-xl bg-paper px-3 py-2 outline-none focus:ring-2 focus:ring-brand/40" />
          <button onClick={search} aria-label="search" className="rounded-xl bg-brand px-3 text-white"><Search size={18} /></button>
          <button onClick={random} aria-label="random brand" className="rounded-xl bg-ink px-3 text-white"><Shuffle size={18} /></button>
        </div>
        {hit && <div className="mt-3 rounded-lg bg-paper p-3 text-sm">
          <p><b>{hit.title}</b> {hit.path ? `${hit.path.brand} ${hit.path.strength}` : 'not found'}</p>
          {hit.path && <p className="text-muted">{hit.path.brand} → {hit.path.ingredients.map((x) => `${x.name}${x.class ? ` (${x.class})` : ''}`).join(' + ')}</p>}
          <p className="text-xs text-muted">request {hit.id} · {hit.ms} ms</p>
        </div>}
      </div>
    </div>
  )
}

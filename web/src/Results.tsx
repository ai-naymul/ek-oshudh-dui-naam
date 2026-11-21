import { useState } from 'react'
import { motion } from 'motion/react'
import { AlertTriangle, AlertOctagon, Info, Search, Shuffle } from 'lucide-react'
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

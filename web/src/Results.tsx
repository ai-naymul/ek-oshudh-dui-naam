import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { AlertTriangle, AlertOctagon, Info, Search, Shuffle, Share2, Loader2, Volume2, Pause, Plus, ShieldCheck, FileText } from 'lucide-react'
import { drawCard, shareCard } from './card'
import { api, bn, bnPct, type CheckResult, type Finding, type Path } from './api'
import { SameMedicine, Sheet, spring } from './Shell'

const SEV = {
  red: { slip: 'bg-danger-soft', bar: 'bg-danger', text: 'text-danger', icon: <AlertOctagon size={22} />, word: 'সতর্কতা' },
  amber: { slip: 'bg-warn-soft', bar: 'bg-warn', text: 'text-warn', icon: <AlertTriangle size={22} />, word: 'খেয়াল রাখুন' },
  info: { slip: 'bg-white ring-1 ring-foil', bar: 'bg-foil', text: 'text-muted', icon: <Info size={20} />, word: 'তথ্য' },
} as const

export function Results({ result, onBack }: { result: CheckResult; onBack: () => void }) {
  const [tab, setTab] = useState<'result' | 'proof'>('result')
  const [card, setCard] = useState(false)
  const reds = result.findings.filter((f) => f.severity === 'red').length
  const ambers = result.findings.filter((f) => f.severity === 'amber').length
  const dup = result.findings.find((f) => f.rule === 'DUP_INGREDIENT')
  const med = (id?: string) => result.medicines.find((m) => m.med_id === id)
  const order = { red: 0, amber: 1, info: 2 }
  const findings = [...result.findings].sort((a, b) => order[a.severity] - order[b.severity])
  const verdict = reds ? { text: `${bn(reds)}টি গুরুত্বপূর্ণ সতর্কতা`, cls: 'text-danger' }
    : ambers ? { text: `${bn(ambers)}টি বিষয়ে খেয়াল রাখুন`, cls: 'text-warn' }
    : { text: 'আমাদের যাচাইয়ে বড় কোনো সমস্যা পাওয়া যায়নি', cls: 'text-rx' }
  const named = (ds: string[]) => ds.filter((d) => !/^D\d+$/.test(d))

  return (
    <motion.main className="mx-auto max-w-6xl px-4 pb-16 pt-6 lg:px-8 lg:pt-8" initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -24 }} transition={spring}>
      <div role="tablist" aria-label="ফলাফলের ভাগ" className="mx-auto mb-6 flex max-w-md gap-1 rounded-2xl bg-white p-1 ring-1 ring-foil">
        {(['result', 'proof'] as const).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className={`relative flex-1 rounded-xl py-2.5 text-[17px] font-semibold ${tab === t ? 'text-white' : 'text-muted'}`}>
            {tab === t && <motion.span layoutId="tab" className="absolute inset-0 rounded-xl bg-ink" transition={spring} />}
            <span className="relative">{t === 'result' ? 'ফলাফল' : 'কীভাবে বুঝলাম'}</span>
          </button>
        ))}
      </div>

      {tab === 'result' ? (
        <div className="grid gap-8 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:gap-10">
          <section>
            <h2 className={`display text-[2rem] lg:text-[2.6rem] ${verdict.cls}`}>{verdict.text}</h2>
            <p className="mt-1 text-muted">{bn(result.medicines.length)}টি ওষুধ মিলিয়ে দেখা হয়েছে। প্রতিটি কথা নিবন্ধিত তালিকা আর নির্দিষ্ট নিয়ম থেকে আসে, AI নিজে বানায় না।</p>
            <div className="mt-5 space-y-3">
              {findings.map((f, i) => <Slip key={i} f={f} i={i} />)}
            </div>
            <div className="mt-6 grid grid-cols-[auto_minmax(0,1fr)] gap-3">
              <Listen caseId={result.case_id} />
              <motion.button whileTap={{ scale: 0.97 }} onClick={() => setCard(true)}
                className="flex items-center justify-center gap-2 rounded-2xl bg-rx py-4 text-[18px] font-semibold text-white shadow-[0_10px_30px_-12px_rgba(11,93,75,0.6)]">
                <Share2 size={20} /><span className="whitespace-nowrap">ছবি কার্ড দেখুন ও পাঠান</span>
              </motion.button>
            </div>
            <AnimatePresence>{card && <CardSheet result={result} onClose={() => setCard(false)} />}</AnimatePresence>
          </section>

          <section className="space-y-6">
            {dup && med(dup.meds[0]) && med(dup.meds[1]) && (
              <div className="sheet px-5 py-6">
                <p className="print text-[15px] font-semibold text-danger">এই কেসে একই ওষুধ, দুই নামে</p>
                <div className="mt-4">
                  <SameMedicine a={med(dup.meds[0])!.brand} b={med(dup.meds[1])!.brand} ingredient={med(dup.meds[0])!.path.ingredients[0]?.name ?? ''} />
                </div>
              </div>
            )}
            <div>
              <p className="mb-2 px-1 text-[15px] font-semibold text-muted">আপনার ওষুধগুলো</p>
              <ul className="sheet divide-y divide-foil overflow-hidden">
                {result.medicines.map((m) => (
                  <li key={m.med_id} className="p-4">
                    <div className="flex items-baseline justify-between gap-3">
                      <p className="print text-[21px] font-semibold">{m.brand} <span className="font-normal text-muted">{m.strength}</span></p>
                      {m.monthly_cost != null && <p className="whitespace-nowrap text-[15px] text-muted">মাসে প্রায় ৳{bn(Math.round(m.monthly_cost))}</p>}
                    </div>
                    <p className="text-[15px] text-muted">{m.form}</p>
                    <p className="mt-1 text-[16px]"><span className="text-muted">ভেতরের ওষুধ: </span><span className="print">{m.path.ingredients.map((x) => x.name).join(' + ')}</span></p>
                    <p className="text-[15px] text-muted">
                      {m.from_rx ? <><FileText size={14} className="mr-1 inline" />প্রেসক্রিপশনে আছে{named(m.doctors).length ? ` (${named(m.doctors).join(', ')})` : ''}</> : 'প্রেসক্রিপশনে নেই, শুধু বাড়িতে আছে'}
                    </p>
                    {m.cheaper.length > 0 && (
                      <p className="mt-2 rounded-lg bg-rx-soft px-3 py-2 text-[15px] text-rx-deep">
                        একই ওষুধ কম দামে নিবন্ধিত আছে: <span className="print">{m.cheaper.map((c) => `${c.brand} ৳${bn(c.unit_price)}`).join(', ')}</span>। বদলানোর আগে ডাক্তারকে জিজ্ঞেস করুন।
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </div>
            <motion.button whileTap={{ scale: 0.97 }} onClick={onBack} className="flex w-full items-center justify-center gap-2 rounded-2xl bg-white py-3.5 text-[17px] font-semibold ring-1 ring-foil">
              <Plus size={18} /> আরও ওষুধ যোগ করুন
            </motion.button>
          </section>
        </div>
      ) : <Proof result={result} />}
    </motion.main>
  )
}

function Slip({ f, i }: { f: Finding; i: number }) {
  const s = SEV[f.severity]
  return (
    <motion.article className={`relative overflow-hidden rounded-[18px] py-4 pl-6 pr-4 ${s.slip}`}
      initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay: 0.08 * i }}>
      <span aria-hidden className={`absolute inset-y-0 left-0 w-1.5 ${s.bar}`} />
      <p className={`flex items-center gap-2 text-[18px] font-bold ${s.text}`}>{s.icon}{s.word}: {f.title_bn}</p>
      <p className="mt-1.5 text-[18px] leading-relaxed">{f.bn}</p>
      <details className="mt-2 text-[14px] text-muted">
        <summary className="cursor-pointer select-none">ইংরেজিতে ও উৎস</summary>
        <p className="print mt-1">{f.en}</p>
        <p className="mt-1">উৎস: {f.source}</p>
      </details>
    </motion.article>
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
      className="flex items-center gap-2 rounded-2xl bg-ink px-5 py-4 text-[18px] font-semibold text-white">
      {state === 'loading' ? <Loader2 size={20} className="animate-spin" /> : state === 'playing' ? <Pause size={20} /> : <Volume2 size={20} />}
      <span className="whitespace-nowrap">{state === 'error' ? 'আবার চেষ্টা' : state === 'playing' ? 'থামান' : 'শুনুন'}</span>
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
    <Sheet label="ছবি কার্ড" onClose={onClose}>
      <div className="mt-3 min-h-0 flex-1 overflow-y-auto rounded-2xl bg-paper ring-1 ring-foil lg:max-h-[60vh]">
        {url ? <img src={url} alt="ফলাফলের ছবি কার্ড" className="w-full" /> : <div className="grid h-60 place-items-center"><Loader2 className="animate-spin text-rx" /></div>}
      </div>
      {note && <p className="mt-2 text-center text-[15px] text-muted">{note}</p>}
      <motion.button whileTap={{ scale: 0.97 }} disabled={!url} onClick={async () => setNote((await shareCard(result)) === 'shared' ? 'পাঠানো হয়েছে' : 'ছবিটি ডাউনলোড হয়েছে')}
        className="mt-3 flex w-full items-center justify-center gap-2 rounded-2xl bg-rx py-4 text-[18px] font-semibold text-white disabled:opacity-40">
        <Share2 size={20} /> পাঠান বা সেভ করুন
      </motion.button>
    </Sheet>
  )
}

type Rates = { auto_accept_coverage: number; auto_accept_error: number; asked_in_top3: number; wrong_n?: number; accepted_n?: number }

// Matching quality, read from models/policy.json (written by training/eval_policy.py): nothing here is typed in by hand.
function EvalCard({ policy }: { policy: Record<string, unknown> }) {
  const test = policy.test as Rates | undefined
  const audited = policy.test_audited as Rates | undefined
  const top1 = (policy.top1_test_audited ?? policy.top1_test) as Record<string, number> | undefined
  const raw = policy.top1_test as Record<string, number> | undefined
  if (!test || !top1) return null
  const unseen = policy.unseen_names as { held_out_names: number; R1_top1: number; R2_top1: number } | undefined
  const rows: [string, string][] = [['R1', 'বানান মিলিয়ে (fuzzy)'], ['R2', 'প্রশিক্ষিত ডিসিশন মডেল (LightGBM)'], ['R3', 'AI-কে ৫টি থেকে বাছতে দেওয়া']]
  const best = Math.max(...rows.map(([k]) => top1[k] ?? 0))
  return (
    <div className="sheet p-5">
      <p className="flex items-center gap-2 text-[18px] font-bold"><ShieldCheck size={20} className="text-rx" />নাম মেলানো কতটা ঠিক?</p>
      <p className="mt-1 text-[15px] text-muted">বাংলাদেশি ডাক্তারদের হাতে লেখা {bn(String(policy.n_test ?? ''))}টি ওষুধের নাম, যা মডেল আগে কখনো দেখেনি।</p>
      <ul className="mt-4 space-y-3">
        {rows.map(([k, label]) => (
          <li key={k}>
            <div className="flex items-baseline justify-between gap-3 text-[16px]">
              <span className={String(policy.method).includes(k) ? 'font-semibold' : ''}>{k}: {label}</span>
              <span className="print whitespace-nowrap font-semibold tabular-nums">{bnPct(top1[k] ?? 0)}</span>
            </div>
            <div className="mt-1 h-2 overflow-hidden rounded-full bg-paper">
              <motion.div className={`h-full rounded-full ${top1[k] === best ? 'bg-rx' : 'bg-foil'}`} initial={{ width: 0 }} animate={{ width: `${(top1[k] ?? 0) * 100}%` }} transition={{ ...spring, duration: 0.8 }} />
            </div>
          </li>
        ))}
      </ul>
      <div className="mt-4 grid grid-cols-2 gap-2 text-[15px]">
        <div className="rounded-xl bg-paper p-3"><p className="text-muted">নিজে থেকে মেনে নেয়</p><p className="print text-[22px] font-semibold">{bnPct(test.auto_accept_coverage)}</p><p className="text-muted">তার মধ্যে ভুল {bnPct(audited?.auto_accept_error ?? test.auto_accept_error)}</p></div>
        <div className="rounded-xl bg-paper p-3"><p className="text-muted">আপনাকে জিজ্ঞেস করে</p><p className="print text-[22px] font-semibold">{bnPct(1 - test.auto_accept_coverage)}</p><p className="text-muted">দেখানো ৩টিতে সঠিকটি {bnPct(test.asked_in_top3)}</p></div>
      </div>
      <details className="mt-3 text-[14px] text-muted">
        <summary className="cursor-pointer select-none">সংখ্যাগুলো কীভাবে এল</summary>
        <p className="mt-1">ভুল ধরা মিলগুলো ছবির সাথে একে একে মিলিয়ে দেখা হয়েছে: ডেটাসেটের নিজের লেবেলে {bn((test.wrong_n ?? 0) - (audited?.wrong_n ?? 0))}টি ভুল ছিল (ছবিতে আমাদের বাছা নামটিই লেখা)। লেবেল যেমন ছিল তেমন ধরলে: R1 {bnPct(raw?.R1 ?? 0)}, R2 {bnPct(raw?.R2 ?? 0)}, R3 {bnPct(raw?.R3 ?? 0)}; নিজে থেকে মানা নামের মধ্যে ভুল {bnPct(test.auto_accept_error)}।</p>
        <p className="mt-1">সীমা ঠিক করা হয়েছে আলাদা যাচাই-সেটে, যাতে ৯৫% নিশ্চয়তায় ভুল ২%-এর নিচে থাকে; পরীক্ষা-সেট শুধু একবার মাপা হয়েছে।</p>
        {unseen && <p className="mt-1">যে {bn(unseen.held_out_names)}টি নাম ডিসিশন মডেল প্রশিক্ষণে দেখেনি, সেগুলোতে: R2 {bnPct(unseen.R2_top1)}, R1 {bnPct(unseen.R1_top1)}।</p>}
      </details>
    </div>
  )
}

function Proof({ result }: { result: CheckResult }) {
  const [q, setQ] = useState('')
  const [hit, setHit] = useState<{ title: string; path: Path | null; ms: number; id: string } | null>(null)
  const [busy, setBusy] = useState(false)
  async function search() { if (!q.trim()) return; setBusy(true); try { const r = await api.search(q); setHit({ title: q, path: r.path, ms: r.latency_ms, id: r.request_id }) } finally { setBusy(false) } }
  async function random() { setBusy(true); try { const r = await api.random(); setHit({ title: r.brand, path: r.path, ms: r.latency_ms, id: r.request_id }) } finally { setBusy(false) } }
  const STEP: Record<string, string> = { perceive: 'ছবি পড়া', match: 'নাম মেলানো', rules: 'নিয়ম যাচাই', transcribe: 'কথা থেকে লেখা', extract: 'ওষুধের নাম বের করা', agent: 'সূত্র খোঁজা', speak: 'বাংলায় কণ্ঠ' }
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="sheet p-5">
        <p className="text-[18px] font-bold">এই যাচাইয়ের প্রতিটি ধাপ</p>
        <p className="mt-1 text-[14px] text-muted">অনুরোধ নং <span className="print">{result.request_id}</span>, মোট {bn(Math.round(result.latency_ms))} মিলিসেকেন্ড। কোনো ফল আগে থেকে রাখা নয়।</p>
        <ol className="relative mt-4 space-y-2 before:absolute before:bottom-2 before:left-[11px] before:top-2 before:w-px before:bg-foil">
          {result.trace.map((s, i) => (
            <motion.li key={i} className="relative flex items-start gap-3" initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ ...spring, delay: Math.min(i, 10) * 0.04 }}>
              <span className="relative mt-1.5 h-[22px] w-[22px] shrink-0 rounded-full border-4 border-white bg-rx" />
              <div className="min-w-0 flex-1 rounded-xl bg-paper px-3 py-2 text-[15px]">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="font-semibold">{STEP[s.step] ?? s.step}</span>
                  <span className="print shrink-0 whitespace-nowrap text-muted">{bn(Math.round(s.ms))} ms</span>
                </div>
                <p className="print break-words text-muted">
                  {s.step === 'match' ? `"${String(s.reading)}" → ${String(s.chosen ?? '—')} (${String(s.method)}, ${String(s.confidence)})`
                    : s.step === 'perceive' ? `${String(s.kind)}, ${String(s.lines)} lines, ${String(s.model)}`
                    : s.step === 'rules' ? `${String(s.findings)} findings`
                    : s.step === 'agent' ? `tools: ${(s.tools as string[] | undefined)?.join(', ') || '—'} → ${String(s.suggestion ?? 'no suggestion')}`
                    : String(s.model ?? '')}
                </p>
              </div>
            </motion.li>
          ))}
        </ol>
      </div>
      <div className="space-y-6">
        <EvalCard policy={result.policy} />
        <div className="sheet p-5">
          <p className="text-[18px] font-bold">যেকোনো নাম নিজে পরীক্ষা করুন</p>
          <p className="mt-1 text-[14px] text-muted">ভুল বানান বা বাংলায় লিখলেও খুঁজে দেয়, সরাসরি নিবন্ধিত তালিকা থেকে</p>
          <div className="mt-3 flex gap-2">
            <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && search()} placeholder="যেমন Nappa, নাপা, Sec1o" aria-label="ওষুধের নাম"
              className="print min-w-0 flex-1 rounded-xl bg-paper px-3 py-2.5 text-[17px] outline-none focus:ring-2 focus:ring-rx/40" />
            <button onClick={search} aria-label="খুঁজুন" className="grid w-12 place-items-center rounded-xl bg-rx text-white"><Search size={18} /></button>
            <button onClick={random} aria-label="যেকোনো একটি নাম" className="grid w-12 place-items-center rounded-xl bg-ink text-white"><Shuffle size={18} /></button>
          </div>
          {busy && <Loader2 className="mt-3 animate-spin text-rx" size={18} />}
          {hit && !busy && (
            <div className="mt-3 rounded-xl bg-paper p-3 text-[16px]">
              {hit.path ? <>
                <p><span className="hand text-[20px]">{hit.title}</span> <span className="text-muted">→</span> <span className="print font-semibold">{hit.path.brand} {hit.path.strength}</span></p>
                <p className="print text-muted">{hit.path.form}, {hit.path.maker}</p>
                <p className="mt-1"><span className="text-muted">ভেতরের ওষুধ: </span><span className="print">{hit.path.ingredients.map((x) => x.name).join(' + ')}</span></p>
              </> : <p>এই নামে নিবন্ধিত কোনো ওষুধ পাওয়া যায়নি।</p>}
              <p className="print mt-1 text-[13px] text-muted">request {hit.id}, {hit.ms} ms</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

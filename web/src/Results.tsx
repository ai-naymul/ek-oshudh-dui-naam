import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { AlertTriangle, AlertOctagon, Info, Search, Shuffle, Share2, Loader2, Volume2, Pause, Plus, FileText, ChevronDown, Check } from 'lucide-react'
import { drawCard, shareCard } from './card'
import { api, bn, bnPct, type CheckResult, type Finding, type ItemView, type Medicine, type Path, type Taking } from './api'
import { useCopy } from './copy'
import { Converge, Press, Sheet, spring } from './Shell'

const SEV = {
  red: { slip: 'bg-danger-soft', bar: 'bg-danger', text: 'text-danger', icon: <AlertOctagon size={22} aria-hidden /> },
  amber: { slip: 'bg-warn-soft', bar: 'bg-warn', text: 'text-warn', icon: <AlertTriangle size={22} aria-hidden /> },
  info: { slip: 'bg-white ring-1 ring-foil', bar: 'bg-foil', text: 'text-muted', icon: <Info size={20} aria-hidden /> },
} as const

export function Results({ result, items, onBack, onRecheck }: {
  result: CheckResult; items: ItemView[]; onBack: () => void; onRecheck: () => Promise<void>
}) {
  const t = useCopy()
  const [card, setCard] = useState(false)
  const reds = result.findings.filter((f) => f.severity === 'red')
  const ambers = result.findings.filter((f) => f.severity === 'amber')
  const order = { red: 0, amber: 1, info: 2 }
  const findings = [...result.findings].sort((a, b) => order[a.severity] - order[b.severity])
  // Lines still waiting for a tap were left out of every rule: never show an all-clear while any are pending.
  const pending = result.unchecked ?? 0
  const verdict = reds.length ? { text: t('verdict.red', { n: bn(reds.length) }), cls: 'text-danger' }
    : ambers.length ? { text: t('verdict.amber', { n: bn(ambers.length) }), cls: 'text-warn' }
    : pending ? { text: t('verdict.partial', { n: bn(pending) }), cls: 'text-warn' }
    : { text: t('verdict.ok'), cls: 'text-rx' }
  const clear = !reds.length && !ambers.length
  const med = (id: string) => result.medicines.find((m) => m.med_id === id)
  const reveal = reds.find((f) => f.rule === 'DUP_INGREDIENT')

  return (
    <motion.main className="mx-auto max-w-2xl px-4 pb-16 pt-6 lg:pt-10" initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 24 }} transition={spring}>
      <h2 className={`display text-[2rem] sm:text-[2.4rem] ${verdict.cls}`}>{verdict.text}</h2>
      <p className="mt-1 text-muted">{t('verdict.sub', { n: bn(result.medicines.length) })}</p>
      {pending > 0 && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-warn-soft p-4">
          <p className="text-warn">{clear ? t('verdict.partial_sub') : <><span className="font-semibold">{t('verdict.partial', { n: bn(pending) })}।</span> {t('verdict.partial_sub')}</>}</p>
          <Press onClick={onBack} className="min-h-11 rounded-full bg-white px-4 font-semibold text-ink ring-1 ring-foil">{t('verdict.partial_action')}</Press>
        </div>
      )}
      {clear && <p className="mt-3 text-[0.95rem] text-muted">{t('verdict.scope')}</p>}

      {reveal && <Reveal meds={reveal.meds.map(med).filter(Boolean) as Medicine[]} items={items} caseId={result.case_id} />}

      <div className="mt-6 space-y-3">
        {findings.map((f, i) => (
          f.rule === 'DUP_ASK_CURRENT'
            ? <AskCard key={f.rule + f.meds.join()} f={f} i={i} meds={f.meds.map(med).filter(Boolean) as Medicine[]} caseId={result.case_id} onRecheck={onRecheck} />
            : <Slip key={f.rule + f.meds.join()} f={f} i={i} />
        ))}
      </div>

      <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-[auto_minmax(0,1fr)]">
        <Listen key={result.request_id} caseId={result.case_id} />
        <Press onClick={() => setCard(true)} className="flex min-h-14 items-center justify-center gap-2 rounded-2xl bg-rx px-4 text-[1.05rem] font-semibold text-white shadow-[0_10px_30px_-12px_rgba(11,93,75,0.6)]">
          <Share2 size={20} aria-hidden />{t('actions.card')}
        </Press>
      </div>
      <AnimatePresence>{card && <CardSheet result={result} items={items} onClose={() => setCard(false)} />}</AnimatePresence>

      <h3 className="mt-10 text-[1.15rem] font-bold">{t('meds.title')}</h3>
      <ul className="sheet mt-3 divide-y divide-foil overflow-hidden">
        {result.medicines.map((m) => <MedRow key={m.med_id} m={m} />)}
      </ul>
      <Press onClick={onBack} className="mt-4 flex min-h-12 w-full items-center justify-center gap-2 rounded-2xl bg-white text-[1rem] font-semibold ring-1 ring-foil">
        <Plus size={18} aria-hidden />{t('actions.more')}
      </Press>

      <HowWeKnow result={result} />
      <footer className="mt-8 text-[0.9rem] text-muted"><p>{t('app.disclaimer')}</p><p className="mt-1 font-semibold">{t('app.team')}</p></footer>
    </motion.main>
  )
}

// The duplicate made visible: the family's own photo lines (or the names) join at the one ingredient inside them.
function Reveal({ meds, items, caseId }: { meds: Medicine[]; items: ItemView[]; caseId: string }) {
  const t = useCopy()
  if (meds.length < 2) return null
  const face = (m: Medicine) => {
    const it = items.find((i) => m.items.includes(i.item_id) && i.has_crop)
    return (
      <div className="flex w-full min-w-0 flex-col items-center gap-2">
        {it && <img src={api.cropUrl(caseId, it.item_id)} alt="" className="h-12 w-full max-w-[240px] rounded-lg bg-white object-contain ring-1 ring-foil" />}
        <span className="print max-w-full truncate text-[1.3rem] font-semibold text-danger">{m.brand}</span>
      </div>
    )
  }
  const ingredient = meds[0].path.ingredients.filter((x) => meds.every((m) => m.path.ingredients.some((y) => y.name === x.name))).map((x) => x.name).join(' + ')
    || meds[0].path.ingredients[0]?.name || ''
  return (
    <section className="sheet lift mt-6 px-4 py-6 sm:px-6" aria-label={t('reveal.head', { n: bn(meds.length) })}>
      <p className="mb-4 text-center text-[1rem] font-semibold text-danger">{t('reveal.head', { n: bn(meds.length) })}</p>
      <Converge left={face(meds[0])} right={face(meds[1])} ingredient={ingredient} />
    </section>
  )
}

function Slip({ f, i }: { f: Finding; i: number }) {
  const t = useCopy()
  const s = SEV[f.severity]
  return (
    <motion.article className={`relative overflow-hidden rounded-[18px] py-4 pl-6 pr-4 ${s.slip}`} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay: 0.06 * i }}>
      <span aria-hidden className={`absolute inset-y-0 left-0 w-1.5 ${s.bar}`} />
      <p className={`flex items-center gap-2 text-[1.05rem] font-bold ${s.text}`}>{s.icon}{t(`sev.${f.severity}`)}: {f.title_bn}</p>
      <p className="mt-1.5 text-[1.05rem] leading-relaxed">{f.bn}</p>
      <details className="mt-2 text-[0.95rem] text-muted">
        <summary className="flex min-h-11 cursor-pointer select-none list-none items-center gap-1 [&::-webkit-details-marker]:hidden">
          <ChevronDown size={16} aria-hidden className="transition-transform [details[open]_&]:rotate-180" />{t('slip.more')}
        </summary>
        <p className="print mt-1">{f.en}</p>
        <p className="mt-1">{t('slip.source')}: {f.source}</p>
      </details>
    </motion.article>
  )
}

// "Are both taken now?" answered right on the finding; the check re-runs after each answer.
function AskCard({ f, i, meds, caseId, onRecheck }: { f: Finding; i: number; meds: Medicine[]; caseId: string; onRecheck: () => Promise<void> }) {
  const t = useCopy()
  const [busy, setBusy] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  async function set(m: Medicine, v: Taking) {
    setBusy(m.med_id); setErr(null)
    try { await Promise.all(m.items.map((iid) => api.status(caseId, iid, v))); await onRecheck() }
    catch { setErr(t('err.generic')) }
    finally { setBusy(null) }
  }
  return (
    <motion.article className="relative overflow-hidden rounded-[18px] bg-warn-soft py-4 pl-6 pr-4" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay: 0.06 * i }}>
      <span aria-hidden className="absolute inset-y-0 left-0 w-1.5 bg-warn" />
      <p className="flex items-center gap-2 text-[1.05rem] font-bold text-warn">{SEV.amber.icon}{f.title_bn}</p>
      <p className="mt-1.5 text-[1.05rem] leading-relaxed">{f.bn}</p>
      <ul className="mt-3 space-y-3">
        {meds.map((m) => (
          <li key={m.med_id} className="rounded-xl bg-white p-3">
            <p className="print text-[1.1rem] font-semibold">{m.brand} <span className="font-normal text-muted">{m.strength}</span></p>
            <div role="radiogroup" aria-label={`${m.brand}: ${t('status.label')}`} className="mt-2 flex flex-wrap gap-2">
              {(['current', 'stopped', 'unsure'] as Taking[]).map((o) => (
                <Press key={o} role="radio" aria-checked={m.taking === o} disabled={!!busy} onClick={() => set(m, o)}
                  className={`flex min-h-11 items-center gap-1.5 rounded-full px-4 text-[0.95rem] font-semibold ring-1 ${m.taking !== o ? 'bg-white ring-foil'
                    : o === 'current' ? 'bg-rx text-white ring-rx' : o === 'stopped' ? 'bg-ink text-white ring-ink' : 'bg-paper ring-2 ring-muted/50'}`}>
                  {busy === m.med_id ? <Loader2 size={15} className="animate-spin" aria-hidden /> : m.taking === o ? <Check size={15} strokeWidth={3} aria-hidden /> : null}{t(`status.${o}`)}
                </Press>
              ))}
            </div>
          </li>
        ))}
      </ul>
      {err && <p role="alert" className="mt-2 text-[0.95rem] text-danger">{err}</p>}
    </motion.article>
  )
}

function MedRow({ m }: { m: Medicine }) {
  const t = useCopy()
  const named = m.doctors.filter((d) => !/^D\d+$/.test(d))
  return (
    <li className="p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <p className="print text-[1.2rem] font-semibold">{m.brand} <span className="font-normal text-muted">{m.strength}</span></p>
        {m.monthly_cost != null && <p className="whitespace-nowrap text-[0.95rem] text-muted">{t('meds.month', { n: bn(Math.round(m.monthly_cost)) })}</p>}
      </div>
      <p className="text-[0.95rem] text-muted">{m.form}{m.taking === 'stopped' ? `, ${t('status.stopped')}` : ''}</p>
      {m.checked === false
        ? <p className="mt-1 font-semibold text-warn">{t('meds.unchecked')}</p>
        : <p className="mt-1"><span className="text-muted">{t('meds.inside')}: </span><span className="print">{m.path.ingredients.map((x) => x.name).join(' + ')}</span></p>}
      <p className="text-[0.95rem] text-muted">
        {m.from_rx ? <><FileText size={14} className="mr-1 inline" aria-hidden />{t('meds.on_rx')}{named.length ? ` (${named.join(', ')})` : ''}</> : t('meds.not_on_rx')}
      </p>
      {m.cheaper.length > 0 && (
        <p className="mt-2 rounded-lg bg-rx-soft px-3 py-2 text-[0.95rem] text-rx-deep">
          {t('meds.cheaper', { list: m.cheaper.map((c) => `${c.brand} ৳${bn(c.unit_price)}`).join(', ') })}
        </p>
      )}
    </li>
  )
}

// Bangla voice reply: the template text of the findings, spoken by the TTS model on the server. Tap to play.
function Listen({ caseId }: { caseId: string }) {
  const t = useCopy()
  const [state, setState] = useState<'idle' | 'loading' | 'playing' | 'error'>('idle')
  const audio = useRef<HTMLAudioElement | null>(null)
  const url = useRef<string | null>(null)
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false; audio.current?.pause(); if (url.current) URL.revokeObjectURL(url.current) } }, [])
  async function toggle() {
    if (state === 'loading') return
    if (state === 'playing') { audio.current?.pause(); setState('idle'); return }
    setState('loading')
    try {
      if (!audio.current) {
        const blob = await api.speech(caseId)
        if (!alive.current) return
        url.current = URL.createObjectURL(blob)
        audio.current = new Audio(url.current)
        audio.current.onended = () => setState('idle')
      }
      audio.current.currentTime = 0
      await audio.current.play()
      if (alive.current) setState('playing')
    } catch { if (alive.current) setState('error') }
  }
  return (
    <Press onClick={toggle} disabled={state === 'loading'} aria-busy={state === 'loading'} aria-label={t('actions.listen')} className="flex min-h-14 items-center justify-center gap-2 rounded-2xl bg-ink px-6 text-[1.05rem] font-semibold text-white">
      {state === 'loading' ? <Loader2 size={20} className="animate-spin" aria-hidden /> : state === 'playing' ? <Pause size={20} aria-hidden /> : <Volume2 size={20} aria-hidden />}
      <span className="whitespace-nowrap">{state === 'error' ? t('actions.retry') : state === 'playing' ? t('actions.stop') : t('actions.listen')}</span>
    </Press>
  )
}

function CardSheet({ result, items, onClose }: { result: CheckResult; items: ItemView[]; onClose: () => void }) {
  const t = useCopy()
  const [blob, setBlob] = useState<Blob | null>(null)
  const [url, setUrl] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  useEffect(() => {
    let u: string | null = null
    drawCard(result, items).then((b) => { u = URL.createObjectURL(b); setBlob(b); setUrl(u) }).catch(() => setNote(t('err.generic')))
    return () => { if (u) URL.revokeObjectURL(u) }
  }, [result, items])
  return (
    <Sheet label={t('card.title')} onClose={onClose}>
      <div className="mt-3 min-h-0 flex-1 overflow-y-auto rounded-2xl bg-paper ring-1 ring-foil">
        {url ? <img src={url} alt={t('card.title')} className="w-full" /> : <div className="grid h-60 place-items-center"><Loader2 className="animate-spin text-rx" aria-hidden /></div>}
      </div>
      {note && <p role="status" className="mt-2 text-center text-[0.95rem] text-muted">{note}</p>}
      <Press disabled={!blob} onClick={async () => { if (blob) { const r = await shareCard(blob, result); if (r) setNote(r === 'shared' ? t('card.sent') : t('card.saved')) } }}
        className="mt-3 flex min-h-14 w-full items-center justify-center gap-2 rounded-2xl bg-rx text-[1.05rem] font-semibold text-white disabled:opacity-40">
        <Share2 size={20} aria-hidden />{t('card.share')}
      </Press>
    </Sheet>
  )
}

type Rates = { auto_accept_coverage: number; auto_accept_error: number; asked_in_top3: number; wrong_n?: number; accepted_n?: number }

// One disclosure for everything technical: the steps of this check, the matching benchmark, and a live lookup.
function HowWeKnow({ result }: { result: CheckResult }) {
  const t = useCopy()
  const [open, setOpen] = useState(false)
  return (
    <section className="mt-10">
      <Press onClick={() => setOpen((v) => !v)} aria-expanded={open} className="flex min-h-14 w-full items-center justify-between rounded-2xl bg-white px-5 text-[1.05rem] font-bold ring-1 ring-foil">
        {t('how.title')}<motion.span animate={{ rotate: open ? 180 : 0 }} transition={spring}><ChevronDown size={22} aria-hidden /></motion.span>
      </Press>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div className="overflow-hidden" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} transition={spring}>
            <div className="space-y-4 pt-4">
              <Trace result={result} />
              <Benchmark policy={result.policy} />
              <TryBrand />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  )
}

function Trace({ result }: { result: CheckResult }) {
  const t = useCopy()
  const detail = (s: CheckResult['trace'][number]) =>
    s.step === 'match' ? `“${String(s.reading)}” → ${String(s.chosen ?? '—')} (${String(s.method)}, ${String(s.confidence)})`
      : s.step === 'perceive' ? `${String(s.kind)}, ${String(s.lines ?? '')} ${s.model ? `· ${String(s.model)}` : ''}${s.duplicate_of ? ` · = ${String(s.duplicate_of)}` : ''}`
      : s.step === 'rules' ? t('how.rules_out', { n: bn(String(s.findings)) })
      : s.step === 'agent' ? `${(s.tools as string[] | undefined)?.join(', ') || '—'} → ${String(s.suggestion ?? '—')}`
      : s.step === 'status' ? `${String(s.item)}: ${t(`status.${String(s.taking)}`)}`
      : String(s.model ?? s.item ?? '')
  return (
    <div className="sheet p-5">
      <p className="text-[1.05rem] font-bold">{t('how.steps')}</p>
      <p className="mt-1 text-[0.9rem] text-muted">{t('how.steps_sub', { id: result.request_id, ms: bn(Math.round(result.latency_ms)) })}</p>
      <ol className="mt-3 space-y-2">
        {result.trace.map((s, i) => (
          <li key={i} className="rounded-xl bg-paper px-3 py-2 text-[0.95rem]">
            <div className="flex items-baseline justify-between gap-3"><span className="font-semibold">{t(`step.${s.step}`)}</span><span className="print shrink-0 whitespace-nowrap text-muted">{bn(Math.round(s.ms))} ms</span></div>
            <p className="print break-words text-muted">{detail(s)}</p>
          </li>
        ))}
      </ol>
    </div>
  )
}

// Matching benchmark from models/policy.json: raw labels first, the audited figure beside it.
function Benchmark({ policy }: { policy: Record<string, unknown> }) {
  const t = useCopy()
  const test = policy.test as Rates | undefined
  const audited = policy.test_audited as Rates | undefined
  const raw = policy.top1_test as Record<string, number> | undefined
  if (!test || !raw) return null
  const rows: [string, string][] = [['R1', t('how.r1')], ['R2', t('how.r2')], ['R3', t('how.r3')]]
  return (
    <div className="sheet p-5">
      <p className="text-[1.05rem] font-bold">{t('how.bench_title')}</p>
      <p className="mt-1 text-[0.95rem] text-muted">{t('how.bench_sub', { n: bn(String(policy.n_test ?? '')) })}</p>
      <table className="mt-3 w-full text-[0.95rem]">
        <tbody>
          {rows.map(([k, label]) => (
            <tr key={k} className="border-t border-foil first:border-0">
              <td className="py-2 pr-2">{label}{String(policy.method) === k && <span className="ml-2 rounded-full bg-rx-soft px-2 py-0.5 text-[0.8rem] font-semibold text-rx">{t('how.shipped')}</span>}</td>
              <td className="print py-2 text-right font-semibold tabular-nums">{bnPct(raw[k] ?? 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-3 grid gap-2 text-[0.95rem] sm:grid-cols-2">
        <div className="rounded-xl bg-paper p-3"><p className="text-muted">{t('how.auto')}</p><p className="print text-[1.3rem] font-semibold">{bnPct(test.auto_accept_coverage)}</p>
          <p className="text-muted">{t('how.auto_wrong', { raw: bnPct(test.auto_accept_error), audited: bnPct(audited?.auto_accept_error ?? test.auto_accept_error) })}</p></div>
        <div className="rounded-xl bg-paper p-3"><p className="text-muted">{t('how.ask')}</p><p className="print text-[1.3rem] font-semibold">{bnPct(1 - test.auto_accept_coverage)}</p>
          <p className="text-muted">{t('how.ask_top3', { p: bnPct(test.asked_in_top3) })}</p></div>
      </div>
      <p className="mt-3 text-[0.9rem] text-muted">{t('how.method', { raw: bnPct(test.auto_accept_error), audited: bnPct(audited?.auto_accept_error ?? test.auto_accept_error) })}</p>
    </div>
  )
}

function TryBrand() {
  const t = useCopy()
  const [q, setQ] = useState('')
  const [hit, setHit] = useState<{ title: string; path: Path | null; ms: number; id: string } | null>(null)
  const [busy, setBusy] = useState(false)
  async function go(fn: () => Promise<{ title: string; path: Path | null; ms: number; id: string }>) {
    setBusy(true)
    try { setHit(await fn()) } catch { setHit({ title: q, path: null, ms: 0, id: '' }) } finally { setBusy(false) }
  }
  const search = () => q.trim() && go(async () => { const r = await api.search(q); return { title: q, path: r.path, ms: r.latency_ms, id: r.request_id } })
  const random = () => go(async () => { const r = await api.random(); return { title: r.brand, path: r.path, ms: r.latency_ms, id: r.request_id } })
  return (
    <div className="sheet p-5">
      <p className="text-[1.05rem] font-bold">{t('how.try')}</p>
      <p className="mt-1 text-[0.95rem] text-muted">{t('how.try_hint')}</p>
      <div className="mt-3 flex gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && search()} placeholder={t('how.try_placeholder')} aria-label={t('how.try')}
          className="print min-h-12 min-w-0 flex-1 rounded-xl bg-paper px-3 text-[1.05rem] outline-none focus:ring-2 focus:ring-rx/40" />
        <Press onClick={search} aria-label={t('how.try')} className="grid w-12 place-items-center rounded-xl bg-rx text-white"><Search size={18} aria-hidden /></Press>
        <Press onClick={random} aria-label={t('how.try_random')} className="grid w-12 place-items-center rounded-xl bg-ink text-white"><Shuffle size={18} aria-hidden /></Press>
      </div>
      {busy && <Loader2 className="mt-3 animate-spin text-rx" size={18} aria-hidden />}
      {hit && !busy && (
        <div className="mt-3 rounded-xl bg-paper p-3">
          {hit.path ? <>
            <p><span className="hand text-[1.2rem]">{hit.title}</span> <span className="text-muted">→</span> <span className="print font-semibold">{hit.path.brand} {hit.path.strength}</span></p>
            <p className="print text-[0.95rem] text-muted">{hit.path.form}, {hit.path.maker}</p>
            <p className="mt-1"><span className="text-muted">{t('meds.inside')}: </span><span className="print">{hit.path.ingredients.map((x) => x.name).join(' + ')}</span></p>
          </> : <p>{t('how.not_found')}</p>}
          {hit.id && <p className="print mt-1 text-[0.85rem] text-muted">request {hit.id}, {hit.ms} ms</p>}
        </div>
      )}
    </div>
  )
}

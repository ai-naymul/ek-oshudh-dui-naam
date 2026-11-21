import { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { Camera, FileText, Keyboard, Loader2, Check, AlertCircle, Mic, Quote, Sparkles, ArrowRight, CircleHelp } from 'lucide-react'
import { Recorder } from './Recorder'
import { api, bn, bnInt, shrink, type ItemView, type Stats } from './api'
import { spring } from './Shell'

type Busy = { kind: 'image' | 'voice' | 'text'; label: string; preview?: string } | null

const GROUP: Record<string, string> = { rx: 'প্রেসক্রিপশন', strip: 'স্ট্রিপ বা বাক্সের ছবি', text: 'লিখে দেওয়া নাম', voice: 'মুখে বলা নাম' }
const SAID: Record<string, string> = { rx: 'লেখা আছে', strip: 'লেখা আছে', voice: 'শোনা গেছে', text: 'লিখেছেন' }

export function CaseScreen({ caseId, items, setItems, onCheck, checking, stats }: {
  caseId: string; items: ItemView[]; setItems: (f: (prev: ItemView[]) => ItemView[]) => void; onCheck: () => void; checking: boolean; stats: Stats | null
}) {
  const rxInput = useRef<HTMLInputElement>(null)
  const stripInput = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState<Busy>(null)
  const [error, setError] = useState<string | null>(null)
  const [typing, setTyping] = useState(false)
  const [text, setText] = useState('')
  const [recording, setRecording] = useState(false)
  const [heard, setHeard] = useState<string[]>([])

  const onVoice = useCallback(async (audio: Blob) => {
    setRecording(false)
    setError(null)
    setBusy({ kind: 'voice', label: 'কথা শোনা হচ্ছে' })
    try {
      const res = await api.addVoice(caseId, audio)
      setHeard((h) => [...h, res.transcript])
      setItems((prev) => [...prev, ...res.items])
      if (!res.items.length) setError('কোনো ওষুধের নাম শোনা যায়নি। আরেকবার ধীরে বলুন, বা নাম লিখে দিন।')
    } catch (e) {
      setError(`কথাটি শোনা যায়নি (${(e as Error).message})। আবার বলুন, বা নাম লিখে দিন।`)
    }
    setBusy(null)
  }, [caseId, setItems])

  async function onFiles(files: FileList | null, label: string) {
    if (!files?.length) return
    setError(null)
    for (const f of Array.from(files)) {
      const preview = URL.createObjectURL(f)
      setBusy({ kind: 'image', label, preview })
      try {
        const res = await api.addImage(caseId, await shrink(f))
        setItems((prev) => [...prev, ...res.items])
        if (!res.items.length) setError('ছবিতে কোনো ওষুধের নাম পাওয়া যায়নি। আরেকটু কাছ থেকে, আলোতে তুলে আবার দিন।')
      } catch (e) {
        setError(`ছবিটি পড়া যায়নি (${(e as Error).message})। আবার চেষ্টা করুন।`)
      }
      URL.revokeObjectURL(preview)
    }
    setBusy(null)
  }

  async function onText() {
    if (!text.trim()) return
    setError(null)
    setBusy({ kind: 'text', label: 'নামগুলো মেলানো হচ্ছে' })
    try {
      const res = await api.addText(caseId, text)
      setItems((prev) => [...prev, ...res.items])
      setText('')
      setTyping(false)
    } catch (e) {
      setError(`নামগুলো যোগ করা যায়নি (${(e as Error).message})।`)
    }
    setBusy(null)
  }

  async function choose(it: ItemView, product_id: number | null) {
    const updated = await api.confirm(caseId, it.item_id, product_id, it.per_day)
    setItems((prev) => prev.map((x) => (x.item_id === it.item_id ? updated : x)))
  }

  const unconfirmed = items.filter((i) => i.needs_confirm).length
  const groups = groupByDoc(items)
  const checkButton = (
    <motion.button whileTap={{ scale: 0.97 }} disabled={!items.length || !!busy || checking} onClick={onCheck}
      className="flex w-full items-center justify-center gap-2 rounded-2xl bg-ink py-4 text-[19px] font-semibold text-white disabled:opacity-40">
      {checking ? <Loader2 size={20} className="animate-spin" /> : null}
      মিলিয়ে দেখুন{items.length ? ` (${bn(items.length)}টি ওষুধ)` : ''}
    </motion.button>
  )

  return (
    <motion.main className="mx-auto grid max-w-6xl gap-6 px-4 pb-40 pt-6 lg:grid-cols-[400px_minmax(0,1fr)] lg:gap-10 lg:px-8 lg:pb-16 lg:pt-10"
      initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -24 }} transition={spring}>
      {/* left: how to add */}
      <section className="lg:sticky lg:top-24 lg:self-start">
        <h2 className="display text-[1.9rem] lg:text-[2.2rem]">ওষুধগুলো যোগ করুন</h2>
        <p className="mt-1 text-muted">এক বা একাধিক ডাক্তারের প্রেসক্রিপশন, বাড়িতে থাকা ওষুধের স্ট্রিপ, অথবা নাম বলে বা লিখে দিন।</p>
        <div className="mt-5 grid grid-cols-2 gap-3">
          <Tile icon={<FileText />} label="প্রেসক্রিপশন" hint="ছবি" onClick={() => rxInput.current?.click()} />
          <Tile icon={<Camera />} label="স্ট্রিপ / বাক্স" hint="ছবি" onClick={() => stripInput.current?.click()} />
          <Tile icon={<Mic />} label="বলুন" hint="বাংলায়" onClick={() => setRecording(true)} />
          <Tile icon={<Keyboard />} label="লিখে দিন" hint="নাম" active={typing} onClick={() => setTyping((v) => !v)} />
        </div>
        <input ref={rxInput} type="file" accept="image/*" multiple hidden onChange={(e) => { onFiles(e.target.files, 'প্রেসক্রিপশন পড়া হচ্ছে'); e.target.value = '' }} />
        <input ref={stripInput} type="file" accept="image/*" capture="environment" hidden onChange={(e) => { onFiles(e.target.files, 'স্ট্রিপ পড়া হচ্ছে'); e.target.value = '' }} />
        <AnimatePresence>{recording && <Recorder onDone={onVoice} onClose={() => setRecording(false)} />}</AnimatePresence>
        <AnimatePresence>
          {typing && (
            <motion.div className="sheet mt-3 overflow-hidden p-3" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} transition={spring}>
              <label htmlFor="typed" className="text-[15px] text-muted">প্রতি লাইনে একটি ওষুধ, চাইলে মাত্রা আর কখন খান</label>
              <textarea id="typed" value={text} onChange={(e) => setText(e.target.value)} rows={4} autoFocus placeholder={'Napa 500 1+0+1\nSeclo 20 রাতে'}
                className="print mt-1 w-full resize-none rounded-xl bg-paper p-3 text-[18px] outline-none focus:ring-2 focus:ring-rx/40" />
              <motion.button whileTap={{ scale: 0.97 }} onClick={onText} disabled={!text.trim() || !!busy} className="mt-2 w-full rounded-xl bg-rx py-3 font-semibold text-white disabled:opacity-40">তালিকায় যোগ করুন</motion.button>
            </motion.div>
          )}
        </AnimatePresence>
        {error && <p role="alert" className="mt-4 flex items-start gap-2 rounded-xl bg-danger-soft p-3 text-[16px] text-danger"><AlertCircle className="mt-1 shrink-0" size={18} />{error}</p>}
        <div className="mt-6 hidden lg:block">
          {unconfirmed > 0 && <p className="mb-2 whitespace-nowrap text-center text-[15px] font-semibold text-warn">{bn(unconfirmed)}টি ওষুধ নিশ্চিত করা বাকি</p>}
          {checkButton}
        </div>
      </section>

      {/* right: what we found */}
      <section aria-live="polite" className="min-w-0">
        <AnimatePresence>{busy && <Working busy={busy} products={stats?.products} />}</AnimatePresence>
        {heard.map((h, k) => (
          <motion.p key={k} className="mb-4 flex gap-2 rounded-2xl bg-white p-3 text-[16px] ring-1 ring-foil" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={spring}>
            <Quote size={16} className="mt-1 shrink-0 text-pen" /><span><span className="text-muted">শুনেছি: </span><span className="text-pen">{h}</span></span>
          </motion.p>
        ))}
        {!items.length && !busy && <Empty />}
        <div className="space-y-6">
          {groups.map((g) => (
            <motion.div key={g.key} layout transition={spring}>
              <p className="mb-2 flex items-baseline gap-2 px-1 text-[15px] font-semibold text-muted">
                {GROUP[g.source] ?? 'ওষুধ'}{g.doctor && g.source === 'rx' && !/^D\d+$/.test(g.doctor) ? <span className="font-normal">({g.doctor})</span> : null}
              </p>
              <ul className="sheet divide-y divide-foil overflow-hidden">
                <AnimatePresence initial={false}>
                  {g.items.map((it, k) => (
                    <motion.li key={it.item_id} layout initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay: Math.min(k, 6) * 0.05 }}>
                      <ItemRow caseId={caseId} it={it} onChoose={(pid) => choose(it, pid)}
                        onResolve={async () => { const v = await api.resolve(caseId, it.item_id); setItems((prev) => prev.map((x) => (x.item_id === it.item_id ? v : x))) }} />
                    </motion.li>
                  ))}
                </AnimatePresence>
              </ul>
            </motion.div>
          ))}
        </div>
      </section>

      {/* phone: the action stays under the thumb */}
      <div className="glass-strong fixed inset-x-0 bottom-0 z-20 border-t border-foil px-4 pb-[max(16px,env(safe-area-inset-bottom))] pt-3 lg:hidden">
        <div className="mx-auto max-w-xl">
          {unconfirmed > 0 && <p className="mb-2 whitespace-nowrap text-center text-[15px] font-semibold text-warn">{bn(unconfirmed)}টি ওষুধ নিশ্চিত করা বাকি</p>}
          {checkButton}
        </div>
      </div>
      {stats && <p className="sr-only">নিবন্ধিত ওষুধ {bnInt(stats.products)}টি</p>}
    </motion.main>
  )
}

function groupByDoc(items: ItemView[]) {
  const out: { key: string; source: string; doctor: string | null; items: ItemView[] }[] = []
  for (const it of items) {
    const key = it.source === 'rx' || it.source === 'strip' ? it.doc_id : it.source
    let g = out.find((x) => x.key === key)
    if (!g) { g = { key, source: it.source, doctor: it.doctor, items: [] }; out.push(g) }
    g.items.push(it)
  }
  return out
}

function Empty() {
  return (
    <div className="grid place-items-center rounded-[20px] border-2 border-dashed border-foil px-6 py-14 text-center">
      <FileText className="text-foil" size={44} />
      <p className="mt-3 text-[18px] font-semibold">এখনো কোনো ওষুধ যোগ হয়নি</p>
      <p className="mt-1 max-w-sm text-muted">বাঁ দিক থেকে একটি প্রেসক্রিপশনের ছবি দিন, অথবা নাম লিখে বা বলে দিন। ওষুধগুলো এখানে একে একে দেখা যাবে।</p>
    </div>
  )
}

// While a photo is being read: the photo itself, with a scan line passing over it.
function Working({ busy, products }: { busy: NonNullable<Busy>; products?: number }) {
  const reduce = useReducedMotion()
  return (
    <motion.div className="sheet lift mb-6 flex items-center gap-4 overflow-hidden p-4" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, scale: 0.98 }} transition={spring}>
      {busy.preview ? (
        <div className="relative h-24 w-32 shrink-0 overflow-hidden rounded-xl bg-paper">
          <img src={busy.preview} alt="" className="h-full w-full object-cover" />
          {!reduce && <motion.div aria-hidden className="absolute inset-x-0 h-10 bg-gradient-to-b from-transparent via-rx/35 to-transparent"
            initial={{ y: '-40%' }} animate={{ y: '260%' }} transition={{ duration: 1.6, repeat: Infinity, ease: 'easeInOut', repeatType: 'reverse' }} />}
        </div>
      ) : <div className="grid h-14 w-14 shrink-0 place-items-center rounded-full bg-rx-soft text-rx"><Loader2 className="animate-spin" /></div>}
      <div>
        <p className="text-[18px] font-semibold">{busy.label}…</p>
        <p className="text-[15px] text-muted">
          {busy.kind === 'image' ? `AI প্রতিটি লাইন পড়ছে, তারপর নিবন্ধিত ${products ? bnInt(products) + 'টি ' : ''}ওষুধের তালিকা থেকে আসল ওষুধটি বেছে নেওয়া হবে।`
            : busy.kind === 'voice' ? 'কথা লেখায় আনা হচ্ছে, তারপর ওষুধের নামগুলো তালিকার সাথে মেলানো হবে।' : 'নামগুলো নিবন্ধিত তালিকার সাথে মেলানো হচ্ছে।'}
        </p>
      </div>
    </motion.div>
  )
}

function Tile({ icon, label, hint, onClick, active }: { icon: React.ReactNode; label: string; hint: string; onClick: () => void; active?: boolean }) {
  return (
    <motion.button whileTap={{ scale: 0.96 }} transition={{ duration: 0.1 }} onClick={onClick}
      className={`flex items-center gap-3 rounded-2xl bg-white px-3 py-3.5 text-left ring-1 ${active ? 'ring-2 ring-rx' : 'ring-foil'} hover:ring-rx/50`}>
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-rx-soft text-rx">{icon}</span>
      <span className="leading-tight"><span className="block whitespace-nowrap text-[17px] font-semibold">{label}</span><span className="text-[14px] text-muted">{hint}</span></span>
    </motion.button>
  )
}

function Status({ it }: { it: ItemView }) {
  if (!it.chosen && !it.needs_confirm) return <span className="flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full bg-danger-soft px-2.5 py-1 text-[14px] font-semibold text-danger"><CircleHelp size={14} />পাওয়া যায়নি</span>
  if (it.needs_confirm) return <span className="flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full bg-warn-soft px-2.5 py-1 text-[14px] font-semibold text-warn"><CircleHelp size={14} />নিশ্চিত করুন</span>
  return <span className="flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full bg-rx-soft px-2.5 py-1 text-[14px] font-semibold text-rx"><Check size={14} strokeWidth={3} />মিলেছে</span>
}

function ItemRow({ caseId, it, onChoose, onResolve }: { caseId: string; it: ItemView; onChoose: (pid: number | null) => void; onResolve: () => Promise<void> }) {
  const [looking, setLooking] = useState(false)
  const [cropOk, setCropOk] = useState(true)
  useEffect(() => setCropOk(true), [it.item_id])
  const s = it.schedule
  const slots = s && [s.morning, s.noon, s.night].some((v) => v !== null) ? `${bn(s.morning ?? 0)}+${bn(s.noon ?? 0)}+${bn(s.night ?? 0)}` : null
  const chips = [
    slots ? `দিনে ${slots}` : s?.per_day ? `দিনে ${bn(s.per_day)} বার` : null,
    s?.meal ? `খাবারের ${s.meal === 'after' ? 'পরে' : 'আগে'}` : null,
    s?.days ? `${bn(s.days)} দিন` : null,
  ].filter(Boolean) as string[]
  return (
    <div className="p-4">
      {it.has_crop && cropOk && (
        <div className="mb-3 overflow-hidden rounded-lg bg-white ring-1 ring-foil">
          <img src={api.cropUrl(caseId, it.item_id)} onError={() => setCropOk(false)} alt={`ছবির এই লাইনটি: ${it.reading}`} className="block max-h-16 w-auto max-w-full object-contain object-left" />
        </div>
      )}
      <div className="flex items-start gap-4">
        {!(it.has_crop && cropOk) && <div className="grid h-14 w-14 shrink-0 place-items-center rounded-lg bg-paper text-muted">{it.source === 'voice' ? <Mic size={22} /> : <Keyboard size={22} />}</div>}
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <p className="text-[14px] text-muted">{SAID[it.source] ?? 'লেখা আছে'}{it.handwritten ? ' (হাতের লেখা)' : ''}</p>
            <Status it={it} />
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className={`${it.handwritten || it.source === 'voice' ? 'hand text-[22px] text-pen' : 'print text-[19px] text-muted'} leading-tight`}>{it.reading || '—'}</span>
            {it.chosen && (
              <>
                <ArrowRight size={18} className="shrink-0 text-muted" aria-label="মিলেছে" />
                <span className="print text-[21px] font-semibold leading-tight">{it.chosen.brand} <span className="font-normal text-muted">{it.chosen.strength}</span></span>
              </>
            )}
          </div>
          {it.chosen && <p className="mt-0.5 text-[14px] text-muted">{it.chosen.form}{it.chosen.maker ? `, ${it.chosen.maker}` : ''}</p>}
          {chips.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {chips.map((c, k) => <span key={c} className={`whitespace-nowrap rounded-full px-2.5 py-0.5 text-[14px] ${k === 0 ? 'bg-rx-soft text-rx' : 'bg-paper text-muted'}`}>{c}</span>)}
            </div>
          )}
        </div>
      </div>
      {it.needs_confirm && (
        <div className="mt-3 rounded-xl bg-warn-soft/60 p-3">
          <p className="mb-2 text-[16px] font-semibold text-warn">{it.has_crop ? 'ছবির লেখার সাথে মিলিয়ে সঠিকটি বেছে নিন' : 'কোনটি বোঝাতে চেয়েছেন, বেছে নিন'}</p>
          {it.agent?.reason_bn && (
            <motion.p className="mb-2 flex gap-2 rounded-lg bg-white p-2.5 text-[16px]" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={spring}>
              <Sparkles size={16} className="mt-1 shrink-0 text-rx" /><span>{it.agent.reason_bn}</span>
            </motion.p>
          )}
          {it.agent && !it.agent.product_id && <p className="mb-2 text-[15px] text-muted">কেসের অন্য ওষুধে কোনো সূত্র পাওয়া যায়নি; নিজে মিলিয়ে বেছে নিন।</p>}
          <div className="flex flex-wrap gap-2">
            {it.options.map((o) => (
              <motion.button key={o.product_id} whileTap={{ scale: 0.95 }} onClick={() => onChoose(o.product_id)}
                className={`print rounded-full px-3.5 py-2 text-[17px] font-semibold ring-1 ${it.agent?.product_id === o.product_id ? 'bg-rx text-white ring-rx' : 'bg-white ring-foil hover:ring-rx/50'}`}>
                {o.brand} <span className={`font-normal ${it.agent?.product_id === o.product_id ? 'text-white/80' : 'text-muted'}`}>{o.strength}</span>
              </motion.button>
            ))}
            <motion.button whileTap={{ scale: 0.95 }} onClick={() => onChoose(null)} className="rounded-full px-3 py-2 text-[16px] text-muted underline">কোনোটিই না</motion.button>
          </div>
          {!it.agent && (
            <motion.button whileTap={{ scale: 0.97 }} disabled={looking} onClick={async () => { setLooking(true); try { await onResolve() } finally { setLooking(false) } }}
              className="mt-3 flex items-center gap-1.5 text-[16px] font-semibold text-rx disabled:opacity-60">
              {looking ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />} সূত্র খুঁজুন: কেসের অন্য ওষুধের সাথে মিলিয়ে দেখুক
            </motion.button>
          )}
        </div>
      )}
    </div>
  )
}

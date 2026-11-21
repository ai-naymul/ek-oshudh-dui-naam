import { useCallback, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Camera, FileText, Keyboard, Loader2, Check, AlertCircle, Mic, Quote } from 'lucide-react'
import { Recorder } from './Recorder'
import { api, bn, shrink, type ItemView } from './api'

const spring = { type: 'spring' as const, bounce: 0, duration: 0.45 }

type Busy = { kind: 'image' | 'text'; label: string } | null

export function CaseScreen({ caseId, items, setItems, onCheck }: {
  caseId: string; items: ItemView[]; setItems: (f: (prev: ItemView[]) => ItemView[]) => void; onCheck: () => void
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
    setBusy({ kind: 'text', label: 'কথা শোনা হচ্ছে' })
    try {
      const res = await api.addVoice(caseId, audio)
      setHeard((h) => [...h, res.transcript])
      setItems((prev) => [...prev, ...res.items])
      if (!res.items.length) setError('কোনো ওষুধের নাম শোনা যায়নি। আরেকবার ধীরে বলুন, বা লিখে দিন।')
    } catch (e) {
      setError(`শোনা যায়নি: ${(e as Error).message}`)
    }
    setBusy(null)
  }, [caseId, setItems])

  async function onFiles(files: FileList | null, label: string) {
    if (!files?.length) return
    setError(null)
    for (const f of Array.from(files)) {
      setBusy({ kind: 'image', label })
      try {
        const small = await shrink(f)
        const res = await api.addImage(caseId, small)
        setItems((prev) => [...prev, ...res.items])
        if (!res.items.length) setError('ছবিতে কোনো ওষুধের নাম পাওয়া যায়নি। আরেকটু কাছ থেকে, আলোতে তুলুন।')
      } catch (e) {
        setError(`পড়া যায়নি: ${(e as Error).message}`)
      }
    }
    setBusy(null)
  }

  async function onText() {
    if (!text.trim()) return
    setBusy({ kind: 'text', label: 'মিলিয়ে দেখা হচ্ছে' })
    try {
      const res = await api.addText(caseId, text)
      setItems((prev) => [...prev, ...res.items])
      setText('')
      setTyping(false)
    } catch (e) {
      setError((e as Error).message)
    }
    setBusy(null)
  }

  async function choose(it: ItemView, product_id: number | null) {
    const updated = await api.confirm(caseId, it.item_id, product_id, it.per_day)
    setItems((prev) => prev.map((x) => (x.item_id === it.item_id ? updated : x)))
  }

  const unconfirmed = items.filter((i) => i.needs_confirm).length
  return (
    <motion.main className="mx-auto max-w-xl px-4 pb-36 pt-4" initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -24 }} transition={spring}>
      <h2 className="display text-[1.6rem]">ওষুধগুলো যোগ করুন</h2>
      <p className="text-muted">এক বা একাধিক ডাক্তারের প্রেসক্রিপশন, ওষুধের স্ট্রিপ, অথবা নাম লিখে দিন।</p>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <Tile icon={<FileText />} label="প্রেসক্রিপশন" onClick={() => rxInput.current?.click()} />
        <Tile icon={<Camera />} label="স্ট্রিপ / বাক্স" onClick={() => stripInput.current?.click()} />
        <Tile icon={<Mic />} label="বলুন" onClick={() => setRecording(true)} />
        <Tile icon={<Keyboard />} label="লিখে দিন" onClick={() => setTyping((v) => !v)} />
      </div>
      <AnimatePresence>{recording && <Recorder onDone={onVoice} onClose={() => setRecording(false)} />}</AnimatePresence>
      {heard.map((h, i) => (
        <motion.p key={i} className="mt-3 flex gap-2 rounded-2xl bg-white p-3 text-[15px] ring-1 ring-line" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={spring}>
          <Quote size={16} className="mt-1 shrink-0 text-brand" /><span><span className="text-muted">শুনেছি: </span>{h}</span>
        </motion.p>
      ))}
      <input ref={rxInput} type="file" accept="image/*" multiple hidden onChange={(e) => { onFiles(e.target.files, 'প্রেসক্রিপশন পড়া হচ্ছে'); e.target.value = '' }} />
      <input ref={stripInput} type="file" accept="image/*" capture="environment" hidden onChange={(e) => { onFiles(e.target.files, 'স্ট্রিপ পড়া হচ্ছে'); e.target.value = '' }} />

      <AnimatePresence>
        {typing && (
          <motion.div className="card mt-3 overflow-hidden p-3" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} transition={spring}>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} placeholder={'যেমন:\nNapa 500 1+0+1\nSeclo 20 0+0+1'}
              className="w-full resize-none rounded-xl bg-paper p-3 text-base outline-none focus:ring-2 focus:ring-brand/40" />
            <motion.button whileTap={{ scale: 0.97 }} onClick={onText} className="mt-2 w-full rounded-xl bg-brand py-3 font-semibold text-white">যোগ করুন</motion.button>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {busy && (
          <motion.div className="card mt-4 flex items-center gap-3 p-4" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={spring}>
            <Loader2 className="animate-spin text-brand" />
            <div><p className="font-semibold">{busy.label}…</p><p className="text-sm text-muted">AI লেখা পড়ছে, তারপর নিবন্ধিত তালিকার সাথে মেলানো হচ্ছে</p></div>
          </motion.div>
        )}
      </AnimatePresence>
      {error && <p className="mt-3 flex items-start gap-2 rounded-xl bg-danger-soft p-3 text-danger"><AlertCircle className="mt-1 shrink-0" size={18} />{error}</p>}

      <div className="mt-5 space-y-3">
        <AnimatePresence initial={false}>
          {items.map((it, i) => (
            <motion.div key={it.item_id} layout initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay: Math.min(i, 6) * 0.05 }}>
              <ItemCard caseId={caseId} it={it} onChoose={(pid) => choose(it, pid)} />
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      <div className="glass-strong fixed inset-x-0 bottom-0 border-t border-line px-4 pb-[max(16px,env(safe-area-inset-bottom))] pt-3">
        <div className="mx-auto max-w-xl">
          {unconfirmed > 0 && <p className="mb-2 whitespace-nowrap text-center text-sm font-semibold text-warn">{bn(unconfirmed)}টি ওষুধ নিশ্চিত করা বাকি</p>}
          <motion.button whileTap={{ scale: 0.97 }} disabled={!items.length || !!busy} onClick={onCheck}
            className="w-full rounded-2xl bg-ink py-4 text-lg font-semibold text-white disabled:opacity-40">
            মিলিয়ে দেখুন {items.length ? `(${bn(items.length)}টি ওষুধ)` : ''}
          </motion.button>
        </div>
      </div>
    </motion.main>
  )
}

const SOURCE_WORD: Record<string, string> = { rx: 'লেখা আছে', strip: 'লেখা আছে', voice: 'শোনা গেছে', text: 'লিখেছেন' }

function Tile({ icon, label, onClick }: { icon: React.ReactNode; label: string; onClick: () => void }) {
  return (
    <motion.button whileTap={{ scale: 0.95 }} transition={{ duration: 0.1 }} onClick={onClick}
      className="card flex items-center gap-3 px-3 py-3.5 text-[16px] font-semibold text-ink">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-brand-soft text-brand">{icon}</span>
      <span className="whitespace-nowrap">{label}</span>
    </motion.button>
  )
}

function ItemCard({ caseId, it, onChoose }: { caseId: string; it: ItemView; onChoose: (pid: number | null) => void }) {
  const sched = it.schedule
  const slots = sched && [sched.morning, sched.noon, sched.night].some((v) => v !== null) ? `${bn(sched.morning ?? 0)}+${bn(sched.noon ?? 0)}+${bn(sched.night ?? 0)}` : null
  return (
    <div className={`card p-4 ${it.needs_confirm ? 'ring-2 ring-warn/50' : ''}`}>
      <div className="flex gap-3">
        {it.has_crop ? <img src={api.cropUrl(caseId, it.item_id)} alt={`লেখা: ${it.reading}`} className="h-14 w-24 shrink-0 rounded-lg border border-line object-contain bg-paper" />
          : <div className="grid h-14 w-24 shrink-0 place-items-center rounded-lg bg-paper text-muted">{it.source === 'voice' ? <Mic size={20} /> : <Keyboard size={20} />}</div>}
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted">{SOURCE_WORD[it.source] ?? 'লেখা আছে'}: <span className="font-sans text-ink">{it.reading || '—'}</span>{it.handwritten && ' · হাতের লেখা'}</p>
          {it.chosen ? <p className="truncate font-sans text-lg font-bold">{it.chosen.brand} <span className="text-base font-medium text-muted">{it.chosen.strength}</span></p>
            : <p className="font-semibold text-danger">তালিকায় পাওয়া যায়নি</p>}
        </div>
        {!it.needs_confirm && it.chosen && <Check className="shrink-0 text-brand" />}
      </div>
      {(slots || sched?.per_day || sched?.meal || sched?.days) && (
        <div className="mt-2 flex flex-wrap gap-1.5 text-[13px]">
          {slots && <span className="whitespace-nowrap rounded-full bg-brand-soft px-2.5 py-0.5 text-brand">দিনে {slots}</span>}
          {!slots && sched?.per_day && <span className="whitespace-nowrap rounded-full bg-brand-soft px-2.5 py-0.5 text-brand">দিনে {bn(sched.per_day)} বার</span>}
          {sched?.meal && <span className="whitespace-nowrap rounded-full bg-paper px-2.5 py-0.5 text-muted">খাবারের {sched.meal === 'after' ? 'পরে' : 'আগে'}</span>}
          {sched?.days && <span className="whitespace-nowrap rounded-full bg-paper px-2.5 py-0.5 text-muted">{bn(sched.days)} দিন</span>}
        </div>
      )}
      {it.needs_confirm && (
        <div className="mt-3">
          <p className="mb-2 text-sm font-semibold text-warn">{it.has_crop ? 'এটা কোনটা? ছবির সাথে মিলিয়ে বেছে নিন' : 'এটা কোনটা? বেছে নিন'}</p>
          <div className="flex flex-wrap gap-2">
            {it.options.map((o) => (
              <motion.button key={o.product_id} whileTap={{ scale: 0.95 }} onClick={() => onChoose(o.product_id)}
                className="rounded-full border border-line bg-paper px-3 py-1.5 font-sans text-sm font-semibold">
                {o.brand} <span className="font-normal text-muted">{o.strength}</span>
              </motion.button>
            ))}
            <motion.button whileTap={{ scale: 0.95 }} onClick={() => onChoose(null)} className="rounded-full px-3 py-1.5 text-sm text-muted underline">কোনোটাই না</motion.button>
          </div>
        </div>
      )}
    </div>
  )
}

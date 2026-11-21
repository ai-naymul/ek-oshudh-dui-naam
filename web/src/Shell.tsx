import { useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { QrCode, RotateCcw, X, Check } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { bn, shareUrl } from './api'

export const spring = { type: 'spring' as const, bounce: 0, duration: 0.45 }

// The mark: one capsule, two halves (one medicine, two names).
export function Mark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect x="3" y="10" width="26" height="12" rx="6" fill="#0b5d4b" />
      <rect x="16" y="10" width="13" height="12" rx="6" fill="#9fd3c2" />
      <rect x="16" y="10" width="6" height="12" fill="#9fd3c2" />
    </svg>
  )
}

const STEPS = ['ওষুধ যোগ করুন', 'নিশ্চিত করুন', 'ফলাফল']

export function TopBar({ step, onNew }: { step: number | null; onNew: (() => void) | null }) {
  const [qr, setQr] = useState(false)
  return (
    <header className="glass sticky top-0 z-30 border-b border-foil/70">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-4 lg:px-8">
        <div className="flex items-center gap-2.5">
          <Mark />
          <span className="display whitespace-nowrap text-[1.15rem] text-rx-deep">এক ওষুধ, দুই নাম</span>
        </div>
        {step !== null && (
          <ol className="mx-auto hidden items-center gap-1 md:flex" aria-label="ধাপ">
            {STEPS.map((s, i) => {
              const state = i < step ? 'done' : i === step ? 'now' : 'next'
              return (
                <li key={s} className="flex items-center gap-1">
                  {i > 0 && <span className={`h-px w-8 ${i <= step ? 'bg-rx' : 'bg-foil'}`} />}
                  <span aria-current={state === 'now' ? 'step' : undefined}
                    className={`flex items-center gap-2 rounded-full px-3 py-1 text-[15px] ${state === 'now' ? 'bg-rx text-white' : state === 'done' ? 'text-rx' : 'text-muted'}`}>
                    <span className={`grid h-5 w-5 place-items-center rounded-full text-[12px] font-semibold ${state === 'now' ? 'bg-white text-rx' : state === 'done' ? 'bg-rx text-white' : 'bg-foil text-muted'}`}>
                      {state === 'done' ? <Check size={12} strokeWidth={3} /> : bn(i + 1)}
                    </span>
                    <span className="whitespace-nowrap">{s}</span>
                  </span>
                </li>
              )
            })}
          </ol>
        )}
        <div className="ml-auto flex items-center gap-2">
          <motion.button whileTap={{ scale: 0.95 }} onClick={() => setQr(true)} aria-label="ফোনে খুলুন"
            className="flex items-center gap-1.5 rounded-full bg-white px-3 py-1.5 text-[15px] font-medium ring-1 ring-foil">
            <QrCode size={16} /><span className="hidden whitespace-nowrap sm:inline">ফোনে খুলুন</span>
          </motion.button>
          {onNew && (
            <motion.button whileTap={{ scale: 0.95 }} onClick={onNew} aria-label="নতুন যাচাই"
              className="flex items-center gap-1.5 rounded-full bg-white px-3 py-1.5 text-[15px] font-medium ring-1 ring-foil">
              <RotateCcw size={15} /><span className="hidden whitespace-nowrap sm:inline">নতুন যাচাই</span>
            </motion.button>
          )}
        </div>
      </div>
      <AnimatePresence>{qr && <QrSheet onClose={() => setQr(false)} />}</AnimatePresence>
    </header>
  )
}

// Bottom sheet on phones, centred panel on a laptop. Enters and leaves along the same path.
export function Sheet({ label, onClose, children }: { label: string; onClose: () => void; children: React.ReactNode }) {
  const reduce = useReducedMotion()
  return (
    <>
      <motion.div className="fixed inset-0 z-40 bg-ink/40" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
      <motion.div role="dialog" aria-label={label}
        className="fixed inset-x-0 bottom-0 z-50 mx-auto flex max-h-[92dvh] max-w-xl flex-col rounded-t-[28px] bg-white px-5 pb-[max(20px,env(safe-area-inset-bottom))] pt-4 lg:bottom-auto lg:top-1/2 lg:max-w-lg lg:-translate-y-1/2 lg:rounded-[28px]"
        initial={reduce ? { opacity: 0 } : { y: '100%' }} animate={reduce ? { opacity: 1 } : { y: 0 }} exit={reduce ? { opacity: 0 } : { y: '100%' }}
        transition={{ type: 'spring', bounce: 0, duration: 0.4 }}>
        <div className="flex items-center justify-between">
          <p className="text-lg font-bold">{label}</p>
          <button onClick={onClose} aria-label="বন্ধ" className="grid h-9 w-9 place-items-center rounded-full bg-paper"><X size={18} /></button>
        </div>
        {children}
      </motion.div>
    </>
  )
}

function QrSheet({ onClose }: { onClose: () => void }) {
  const url = shareUrl()
  const local = /^(localhost|127\.)/.test(window.location.hostname)
  return (
    <Sheet label="ফোনে খুলুন" onClose={onClose}>
      <p className="mt-1 text-muted">ফোনের ক্যামেরা দিয়ে স্ক্যান করুন। কোনো অ্যাপ ইনস্টল লাগবে না।</p>
      <div className="mt-4 flex justify-center"><QRCodeSVG value={url} size={232} marginSize={2} level="M" /></div>
      <div className="mt-3 overflow-x-auto rounded-xl bg-paper px-3 py-2"><p className="print whitespace-nowrap text-center text-[13px] text-muted">{url.replace(/^https?:\/\//, '').replace(/\/$/, '')}</p></div>
      {local && <p className="mt-2 text-sm text-warn">এটি এই ল্যাপটপের নিজস্ব ঠিকানা। একই ওয়াই-ফাইয়ের ফোনে খুলতে ল্যাপটপের নেটওয়ার্ক ঠিকানা দিয়ে অ্যাপটি খুলুন।</p>}
    </Sheet>
  )
}

// One medicine, two names: written names on the left join at the one ingredient on the right.
// `ink` sets the names in handwriting (as on a prescription); otherwise they are printed (as matched in the registry).
export function SameMedicine({ a, b, ingredient, ink = false, caption }: { a: string; b: string; ingredient: string; ink?: boolean; caption?: string }) {
  const reduce = useReducedMotion()
  const draw = (delay: number) => (reduce ? {} : { initial: { pathLength: 0 }, animate: { pathLength: 1 }, transition: { duration: 0.7, delay, ease: 'easeOut' as const } })
  const nameCls = ink ? 'hand text-[30px] leading-none' : 'print text-[24px] font-semibold text-danger'
  return (
    <div className="relative grid grid-cols-[minmax(0,1fr)_88px_minmax(0,1fr)] items-center">
      <div className="space-y-12 py-2">
        <motion.p key={`a-${a}`} className={`truncate text-right ${nameCls}`} initial={reduce ? false : { opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={spring} title={a}>{a}</motion.p>
        <motion.p key={`b-${b}`} className={`truncate text-right ${nameCls}`} initial={reduce ? false : { opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ ...spring, delay: 0.12 }} title={b}>{b}</motion.p>
      </div>
      <svg viewBox="0 0 88 120" className="h-[120px] w-[88px]" aria-hidden="true">
        <motion.path key={`pa-${a}`} d="M4 22 C48 22 44 60 84 60" stroke="#c8382a" strokeWidth="2.5" fill="none" strokeLinecap="round" {...draw(0.25)} />
        <motion.path key={`pb-${b}`} d="M4 98 C48 98 44 60 84 60" stroke="#c8382a" strokeWidth="2.5" fill="none" strokeLinecap="round" {...draw(0.4)} />
      </svg>
      <motion.div key={`i-${ingredient}`} className="justify-self-start" initial={reduce ? false : { opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} transition={{ ...spring, delay: 0.55 }}>
        <p className="print rounded-2xl border-2 border-ink bg-white px-4 py-2 text-[20px] font-semibold">{ingredient}</p>
        {caption && <p className="mt-2 text-[15px] font-semibold text-danger">{caption}</p>}
      </motion.div>
    </div>
  )
}

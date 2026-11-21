import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { QrCode, RotateCcw, X, Check, Minus, Plus } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { api, bn, type Health } from './api'
import { useCopy } from './copy'

// One spring for the whole app: critically damped (no bounce), ~0.45 s to settle (Apple: damping 1.0 by default).
export const spring = { type: 'spring' as const, bounce: 0, duration: 0.45 }

// Press feedback on pointer-down. Under reduced motion the scale is dropped by MotionConfig and the opacity remains.
export function Press({ className = '', children, ...rest }: React.ComponentProps<typeof motion.button>) {
  return (
    <motion.button whileTap={{ scale: 0.97, opacity: 0.82 }} transition={{ duration: 0.1 }} className={className} {...rest}>
      {children}
    </motion.button>
  )
}

// The mark: one capsule, two halves (one medicine, two names).
export function Mark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect x="3" y="10" width="26" height="12" rx="6" fill="var(--color-rx)" />
      <rect x="16" y="10" width="13" height="12" rx="6" fill="#9fd3c2" />
      <rect x="16" y="10" width="6" height="12" fill="#9fd3c2" />
    </svg>
  )
}

const SCALES = [0.9, 1, 1.15, 1.3]
function useTextScale() {
  const [i, setI] = useState(() => {
    try { const v = Number(localStorage.getItem('textScale')); return SCALES.includes(v) ? SCALES.indexOf(v) : 1 } catch { return 1 }
  })
  useEffect(() => {
    document.documentElement.style.setProperty('--text-scale', String(SCALES[i]))
    try { localStorage.setItem('textScale', String(SCALES[i])) } catch { /* private mode */ }
  }, [i])
  return { smaller: () => setI((x) => Math.max(0, x - 1)), bigger: () => setI((x) => Math.min(SCALES.length - 1, x + 1)),
           canSmaller: i > 0, canBigger: i < SCALES.length - 1 }
}

export function aiReady(h: Health | null) {
  if (!h) return false
  const { key_present, last_ok_at, last_error_at } = h.ai
  return key_present && !(last_error_at && (!last_ok_at || last_error_at > last_ok_at))
}

const STEP_KEYS = ['steps.add', 'steps.confirm', 'steps.result']

export function TopBar({ step, onNew, health }: { step: number | null; onNew: (() => void) | null; health: Health | null }) {
  const t = useCopy()
  const [qr, setQr] = useState(false)
  const size = useTextScale()
  const ready = aiReady(health)
  return (
    <header className="glass sticky top-0 z-30 border-b border-foil/70">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-2 px-4">
        <div className="flex shrink-0 items-center gap-2.5">
          <Mark />
          <span className="display hidden whitespace-nowrap text-[1.1rem] text-rx-deep min-[400px]:inline">{t('app.name')}</span>
        </div>
        {step !== null && (
          <ol className="mx-auto hidden items-center gap-1 lg:flex" aria-label="ধাপ">
            {STEP_KEYS.map((k, i) => {
              const state = i < step ? 'done' : i === step ? 'now' : 'next'
              return (
                <li key={k} className="flex items-center gap-1">
                  {i > 0 && <span className={`h-px w-6 ${i <= step ? 'bg-rx' : 'bg-foil'}`} />}
                  <span aria-current={state === 'now' ? 'step' : undefined}
                    className={`flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-[0.85rem] ${state === 'now' ? 'bg-rx text-white' : state === 'done' ? 'text-rx' : 'text-muted'}`}>
                    <span className={`grid h-5 w-5 place-items-center rounded-full text-[0.75rem] font-semibold ${state === 'now' ? 'bg-white text-rx' : state === 'done' ? 'bg-rx text-white' : 'bg-foil text-muted'}`}>
                      {state === 'done' ? <Check size={12} strokeWidth={3} /> : bn(i + 1)}
                    </span>
                    {t(k)}
                  </span>
                </li>
              )
            })}
          </ol>
        )}
        <div className="ml-auto flex items-center gap-1.5">
          <span role="status" title={ready ? t('top.ready') : `${t('top.ai_off')}. ${t('top.ai_off_hint')}`}
            className="hidden items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-1 text-[0.8rem] text-muted sm:flex">
            <span className={`h-2.5 w-2.5 rounded-full ${ready ? 'bg-rx' : 'bg-warn'}`} />{ready ? t('top.ready') : t('top.ai_off')}
          </span>
          <div className="flex items-center rounded-full bg-white ring-1 ring-foil">
            <Press onClick={size.smaller} disabled={!size.canSmaller} aria-label={t('top.smaller')} className="grid h-11 w-10 place-items-center rounded-l-full disabled:opacity-35"><Minus size={16} /></Press>
            <span aria-hidden className="text-[0.85rem] font-semibold">অ</span>
            <Press onClick={size.bigger} disabled={!size.canBigger} aria-label={t('top.bigger')} className="grid h-11 w-10 place-items-center rounded-r-full disabled:opacity-35"><Plus size={16} /></Press>
          </div>
          <Press onClick={() => setQr(true)} aria-label={t('top.qr')} className="flex h-11 items-center gap-1.5 rounded-full bg-white px-3 ring-1 ring-foil">
            <QrCode size={17} /><span className="hidden whitespace-nowrap text-[0.85rem] font-medium md:inline">{t('top.qr')}</span>
          </Press>
          {onNew && (
            <Press onClick={onNew} aria-label={t('top.new')} className="flex h-11 items-center gap-1.5 rounded-full bg-white px-3 ring-1 ring-foil">
              <RotateCcw size={16} /><span className="hidden whitespace-nowrap text-[0.85rem] font-medium md:inline">{t('top.new')}</span>
            </Press>
          )}
        </div>
      </div>
      <AnimatePresence>{qr && <QrSheet onClose={() => setQr(false)} />}</AnimatePresence>
    </header>
  )
}

// Bottom sheet on phones, centred panel on a laptop. Enters and leaves along the same path. Keyboard: focus moves in,
// Tab stays inside, Escape closes, focus returns to the button that opened it; the page behind does not scroll.
export function Sheet({ label, onClose, children }: { label: string; onClose: () => void; children: ReactNode }) {
  const t = useCopy()
  const reduce = useReducedMotion()
  const panel = useRef<HTMLDivElement>(null)
  const close = useRef(onClose)
  close.current = onClose
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null
    const items = () => Array.from(panel.current?.querySelectorAll<HTMLElement>('button, [href], input, textarea, select, [tabindex]:not([tabindex="-1"])') ?? [])
      .filter((el) => !el.hasAttribute('disabled'))
    items()[0]?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); close.current() }
      if (e.key !== 'Tab') return
      const f = items()
      if (!f.length) return
      if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus() }
      else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus() }
    }
    document.addEventListener('keydown', onKey)
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = overflow; opener?.focus?.() }
  }, [])
  return (
    <>
      <motion.div className="fixed inset-0 z-40 bg-ink/40" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
      <motion.div ref={panel} role="dialog" aria-modal="true" aria-label={label}
        className="fixed inset-x-0 bottom-0 z-50 mx-auto flex max-h-[92dvh] max-w-xl flex-col rounded-t-[28px] bg-white px-5 pb-[max(20px,env(safe-area-inset-bottom))] pt-4 lg:bottom-auto lg:top-[8vh] lg:max-h-[84vh] lg:max-w-lg lg:rounded-[28px]"
        initial={reduce ? { opacity: 0 } : { y: '100%' }} animate={reduce ? { opacity: 1 } : { y: 0 }} exit={reduce ? { opacity: 0 } : { y: '100%' }} transition={spring}>
        <div className="flex items-center justify-between gap-3">
          <p className="text-[1.1rem] font-bold">{label}</p>
          <Press onClick={onClose} aria-label={t('app.close')} className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-paper"><X size={20} /></Press>
        </div>
        {children}
      </motion.div>
    </>
  )
}

function QrSheet({ onClose }: { onClose: () => void }) {
  const t = useCopy()
  const local = /^(localhost|127\.)/.test(window.location.hostname)
  const [url, setUrl] = useState(local ? '' : `${window.location.origin}${window.location.pathname}`)
  useEffect(() => {
    if (!local) return
    api.network().then((r) => setUrl(r.urls[0] ? `${r.urls[0]}/` : `${window.location.origin}/`)).catch(() => setUrl(`${window.location.origin}/`))
  }, [local])
  return (
    <Sheet label={t('top.qr')} onClose={onClose}>
      <p className="mt-1 text-muted">{t('qr.scan')}</p>
      <div className="mt-4 flex min-h-[232px] justify-center">{url && <QRCodeSVG value={url} size={232} marginSize={2} level="M" />}</div>
      <div className="mt-3 overflow-x-auto rounded-xl bg-paper px-3 py-2"><p className="print whitespace-nowrap text-center text-[0.85rem] text-muted">{url.replace(/^https?:\/\//, '').replace(/\/$/, '')}</p></div>
      <p className="mt-2 text-[0.9rem] text-muted">{t('qr.same_wifi')}</p>
    </Sheet>
  )
}

// The reveal: two written names (or their photo crops) join at the one ingredient inside them.
// Each name sits at the centre of one grid column (25% and 75% of the width), so the connectors line up at any width
// and any text size.
export function Converge({ left, right, ingredient, caption, play = true }: {
  left: ReactNode; right: ReactNode; ingredient: string; caption?: string; play?: boolean
}) {
  const reduce = useReducedMotion()
  const still = reduce || !play
  return (
    <div>
      <div className="grid grid-cols-2 gap-3">
        <motion.div className="flex min-w-0 justify-center" initial={still ? false : { opacity: 0, x: -14 }} animate={{ opacity: 1, x: 0 }} transition={spring}>{left}</motion.div>
        <motion.div className="flex min-w-0 justify-center" initial={still ? false : { opacity: 0, x: 14 }} animate={{ opacity: 1, x: 0 }} transition={{ ...spring, delay: 0.1 }}>{right}</motion.div>
      </div>
      {/* the lines stretch with the width, so they grow down from the names instead of being "drawn" */}
      <motion.svg viewBox="0 0 100 30" preserveAspectRatio="none" className="h-12 w-full origin-top" aria-hidden="true"
        initial={still ? false : { opacity: 0, scaleY: 0 }} animate={{ opacity: 1, scaleY: 1 }} transition={{ ...spring, delay: 0.3 }}>
        <path d="M25 0 C25 18 50 12 50 30" stroke="var(--color-danger)" strokeWidth="2.5" fill="none" vectorEffect="non-scaling-stroke" strokeLinecap="round" />
        <path d="M75 0 C75 18 50 12 50 30" stroke="var(--color-danger)" strokeWidth="2.5" fill="none" vectorEffect="non-scaling-stroke" strokeLinecap="round" />
      </motion.svg>
      <motion.div className="flex flex-col items-center" initial={still ? false : { opacity: 0, scale: 0.94 }} animate={{ opacity: 1, scale: 1 }} transition={{ ...spring, delay: 0.75 }}>
        <p className="print max-w-full truncate rounded-2xl border-2 border-ink bg-white px-5 py-2 text-[1.2rem] font-semibold">{ingredient}</p>
        {caption && <p className="mt-2 text-[1rem] font-semibold text-danger">{caption}</p>}
      </motion.div>
    </div>
  )
}

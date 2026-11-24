import { useEffect, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { ChevronLeft, ChevronRight, Loader2, Pause, Play } from 'lucide-react'
import { bnInt, bnPct, type Stats } from './api'
import { useCopy } from './copy'
import { Converge, Press, spring } from './Shell'

// Numbers come from /api/stats (the registry and models/policy.json). The example is chosen by the person, not rotated.
const MAX_BRAND = 9, MAX_INGREDIENT = 20
// The example moves on by itself so it draws the eye while people talk: each pair is drawn in ~0.9 s, the ring
// pulses until ~1.6 s, then the next pair.
const ADVANCE_MS = 2000

export function Welcome({ stats, onStart, onSample, busy }: { stats: Stats | null; onStart: () => void; onSample: () => void; busy: boolean }) {
  const t = useCopy()
  // Two names in a large handwriting font, side by side on a phone: only names that fit are shown (nothing is cut off
  // with '…'). The server puts the story's pairs first (settings welcome_pairs: Napa + Ace, Alatrol + Atrizin, ...).
  const examples = (stats?.examples ?? [])
    .filter((e) => e.ingredient.length <= MAX_INGREDIENT)
    .map((e) => ({ ...e, brands: e.brands.filter((b) => b.length <= MAX_BRAND) }))
    .filter((e) => e.brands.length >= 2)
  const [i, setI] = useState(0)
  const reduce = useReducedMotion()
  const [auto, setAuto] = useState(true)    // stops for good once the person picks an example or presses pause
  const [hold, setHold] = useState(false)   // pointer or keyboard focus on the card: do not move it under them
  const moving = auto && !hold && !reduce && examples.length > 1
  useEffect(() => {
    if (!moving) return
    const id = window.setTimeout(() => setI((x) => x + 1), ADVANCE_MS)
    return () => window.clearTimeout(id)
  }, [i, moving])
  const pick = (step: number) => { setAuto(false); setI((x) => x + step) }
  const ex = examples.length ? examples[((i % examples.length) + examples.length) % examples.length] : null
  const lead = stats?.examples.find((e) => e.ingredient === 'Paracetamol') ?? stats?.examples[0]

  return (
    <motion.main className="mx-auto max-w-2xl px-5 pb-12 pt-8 lg:max-w-6xl lg:px-8 lg:pt-16" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 12 }} transition={spring}>
      {/* laptop: the message and actions on the left, the moving example beside them; phone: one column */}
      <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] lg:items-center lg:gap-14">
      <div>
      <h1 className="display whitespace-pre-line text-[2.3rem] text-ink sm:text-[3rem] lg:text-[3.6rem]">{t('welcome.title')}</h1>
      <p className="mt-4 text-[1.05rem] text-muted">
        {lead ? t('welcome.lead', { ingredient: lead.ingredient, n: bnInt(lead.brand_count) }) : t('welcome.lead_plain')}
      </p>
      <div className="mt-7 flex flex-col gap-3 sm:flex-row">
        <Press onClick={onStart} disabled={busy}
          className="flex min-h-14 items-center justify-center gap-2 rounded-2xl bg-rx px-8 text-[1.1rem] font-semibold text-white shadow-[0_10px_30px_-10px_rgba(11,93,75,0.6)] disabled:opacity-60">
          {busy && <Loader2 size={20} className="animate-spin" />}{t('welcome.start')}
        </Press>
        <Press onClick={onSample} disabled={busy} className="min-h-14 rounded-2xl bg-white px-6 text-[1rem] font-semibold text-rx ring-1 ring-foil disabled:opacity-60">
          {t('welcome.sample')}
        </Press>
      </div>
      <p className="mt-4 text-[0.95rem] text-muted">{t('welcome.how')}</p>
      </div>

      <section aria-label={t('welcome.example_head')} className="sheet lift mt-10 px-5 py-6 sm:px-7 lg:mt-0"
        onPointerEnter={() => setHold(true)} onPointerLeave={() => setHold(false)}
        onFocus={() => setHold(true)} onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setHold(false) }}>
        <p className="print text-[0.95rem] font-semibold text-rx">℞ {t('welcome.example_head')}</p>
        <div className="mt-4 min-h-[190px] rounded-xl bg-[repeating-linear-gradient(to_bottom,transparent_0,transparent_37px,rgba(36,64,142,0.08)_37px,rgba(36,64,142,0.08)_38px)] px-2 py-3">
          {ex ? (
            <AnimatePresence mode="wait" initial={false}>
              <motion.div key={ex.ingredient} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
                <Converge ingredient={ex.ingredient} pace={0.8}
                  left={<span className="hand whitespace-nowrap text-[1.7rem] leading-none">{ex.brands[0]}</span>}
                  right={<span className="hand whitespace-nowrap text-[1.7rem] leading-none">{ex.brands[1]}</span>} />
              </motion.div>
            </AnimatePresence>
          ) : <div className="grid h-[170px] place-items-center"><Loader2 className="animate-spin text-rx" /></div>}
        </div>
        {ex && (
          <div className="mt-4 flex items-center gap-3 border-t border-foil pt-4">
            {/* changes together with the picture above (same key and timing), never ahead of it */}
            <div className="min-w-0 flex-1">
              <AnimatePresence mode="wait" initial={false}>
                <motion.p key={ex.ingredient} className="text-[0.95rem] text-muted" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
                  {t('welcome.example_caption', { ingredient: ex.ingredient, n: bnInt(ex.brand_count), more: ex.brands.slice(2, 5).join(', ') })}
                </motion.p>
              </AnimatePresence>
            </div>
            <div className="flex shrink-0 gap-1">
              <Press onClick={() => pick(-1)} aria-label={t('welcome.example_prev')} className="grid h-11 w-11 place-items-center rounded-full bg-paper"><ChevronLeft size={20} /></Press>
              {!reduce && examples.length > 1 && (
                <Press onClick={() => setAuto((a) => !a)} aria-label={t(auto ? 'welcome.example_pause' : 'welcome.example_play')}
                  className="grid h-11 w-11 place-items-center rounded-full bg-paper">{auto ? <Pause size={18} /> : <Play size={18} />}</Press>
              )}
              <Press onClick={() => pick(1)} aria-label={t('welcome.example_next')} className="grid h-11 w-11 place-items-center rounded-full bg-paper"><ChevronRight size={20} /></Press>
            </div>
          </div>
        )}
        {stats?.eval && <p className="mt-4 text-[0.95rem] text-rx-deep">{t('welcome.tested', { n: bnInt(stats.eval.n_test) })} ({bnPct(stats.eval.top1)})</p>}
      </section>
      </div>

      <footer className="mt-8 text-[0.9rem] text-muted lg:mt-12">
        <p>{t('app.disclaimer')}</p>
        <p className="mt-1 font-semibold">{t('app.team')}</p>
      </footer>
    </motion.main>
  )
}

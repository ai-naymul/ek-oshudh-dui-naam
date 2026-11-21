import { useState } from 'react'
import { motion } from 'motion/react'
import { ChevronLeft, ChevronRight, Loader2 } from 'lucide-react'
import { bnInt, bnPct, type Stats } from './api'
import { useCopy } from './copy'
import { Converge, Press, spring } from './Shell'

// Numbers come from /api/stats (the registry and models/policy.json). The example is chosen by the person, not rotated.
export function Welcome({ stats, onStart, onSample, busy }: { stats: Stats | null; onStart: () => void; onSample: () => void; busy: boolean }) {
  const t = useCopy()
  const examples = stats?.examples.filter((e) => e.brands.length >= 2) ?? []
  const [i, setI] = useState(0)
  const ex = examples.length ? examples[((i % examples.length) + examples.length) % examples.length] : null
  const lead = stats?.examples.find((e) => e.ingredient === 'Paracetamol') ?? stats?.examples[0]

  return (
    <motion.main className="mx-auto max-w-2xl px-5 pb-12 pt-8 lg:pt-14" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 12 }} transition={spring}>
      <h1 className="display whitespace-pre-line text-[2.3rem] text-ink sm:text-[3rem]">{t('welcome.title')}</h1>
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

      <section aria-label={t('welcome.example_head')} className="sheet lift mt-10 px-5 py-6 sm:px-7">
        <p className="print text-[0.95rem] font-semibold text-rx">℞ {t('welcome.example_head')}</p>
        <div className="mt-4 min-h-[190px] rounded-xl bg-[repeating-linear-gradient(to_bottom,transparent_0,transparent_37px,rgba(36,64,142,0.08)_37px,rgba(36,64,142,0.08)_38px)] px-2 py-3">
          {ex ? (
            <Converge key={ex.ingredient} ingredient={ex.ingredient}
              left={<span className="hand truncate text-[1.7rem] leading-none" title={ex.brands[0]}>{ex.brands[0]}</span>}
              right={<span className="hand truncate text-[1.7rem] leading-none" title={ex.brands[1]}>{ex.brands[1]}</span>} />
          ) : <div className="grid h-[170px] place-items-center"><Loader2 className="animate-spin text-rx" /></div>}
        </div>
        {ex && (
          <div className="mt-4 flex items-center gap-3 border-t border-foil pt-4">
            <p className="min-w-0 flex-1 text-[0.95rem] text-muted">
              {t('welcome.example_caption', { ingredient: ex.ingredient, n: bnInt(ex.brand_count), more: ex.brands.slice(2, 5).join(', ') })}
            </p>
            <div className="flex shrink-0 gap-1">
              <Press onClick={() => setI((x) => x - 1)} aria-label={t('welcome.example_prev')} className="grid h-11 w-11 place-items-center rounded-full bg-paper"><ChevronLeft size={20} /></Press>
              <Press onClick={() => setI((x) => x + 1)} aria-label={t('welcome.example_next')} className="grid h-11 w-11 place-items-center rounded-full bg-paper"><ChevronRight size={20} /></Press>
            </div>
          </div>
        )}
        {stats?.eval && <p className="mt-4 text-[0.95rem] text-rx-deep">{t('welcome.tested', { n: bnInt(stats.eval.n_test) })} ({bnPct(stats.eval.top1)})</p>}
      </section>

      <footer className="mt-8 text-[0.9rem] text-muted">
        <p>{t('app.disclaimer')}</p>
        <p className="mt-1 font-semibold">{t('app.team')}</p>
      </footer>
    </motion.main>
  )
}

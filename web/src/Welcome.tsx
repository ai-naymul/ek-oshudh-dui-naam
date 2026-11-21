import { useEffect, useState } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { Camera, ScanSearch, MessageCircle, ShieldCheck } from 'lucide-react'
import { bn, bnInt, bnPct, type Stats } from './api'
import { SameMedicine, spring } from './Shell'

// Every number here comes from /api/stats (the registry and models/policy.json), never typed in.
export function Welcome({ stats, onStart, starting }: { stats: Stats | null; onStart: () => void; starting: boolean }) {
  const reduce = useReducedMotion()
  const examples = stats?.examples.filter((e) => e.brands.length >= 2) ?? []
  const [i, setI] = useState(0)
  useEffect(() => {
    if (examples.length < 2 || reduce) return
    const t = window.setInterval(() => setI((x) => (x + 1) % examples.length), 5200)
    return () => window.clearInterval(t)
  }, [examples.length, reduce])
  const ex = examples.length ? examples[i % examples.length] : null
  const para = stats?.examples.find((e) => e.ingredient === 'Paracetamol')
  const lead = para ?? stats?.examples[0]

  return (
    <motion.main className="mx-auto grid max-w-6xl gap-10 px-5 pb-12 pt-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] lg:items-center lg:gap-16 lg:px-8 lg:pt-16"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, y: -12 }} transition={spring}>
      <section>
        <h1 className="display text-[2.4rem] text-ink sm:text-[3.2rem] lg:text-[3.6rem]">একই ওষুধ, ভিন্ন নাম,<br />দ্বিগুণ ঝুঁকি।</h1>
        <p className="mt-5 max-w-[34rem] text-[19px] text-muted">
          {lead
            ? <>বাংলাদেশে শুধু <span className="print font-semibold text-ink">{lead.ingredient}</span> বিক্রি হয় {bnInt(lead.brand_count)}টি আলাদা নামে। দুই ডাক্তার দুই নামে একই ওষুধ লিখলে বাড়িতে কেউ টেরও পায় না।</>
            : 'দুই ডাক্তার দুই নামে একই ওষুধ লিখলে বাড়িতে কেউ টেরও পায় না।'}
        </p>
        <motion.button whileTap={{ scale: 0.97 }} transition={{ duration: 0.1 }} onClick={onStart} disabled={starting}
          className="mt-8 w-full rounded-2xl bg-rx py-4 text-[20px] font-semibold text-white shadow-[0_10px_30px_-10px_rgba(11,93,75,0.6)] disabled:opacity-60 sm:w-auto sm:px-12">
          মিলিয়ে দেখা শুরু করুন
        </motion.button>

        <ol className="mt-10 space-y-4">
          {[
            [<Camera key="c" size={20} />, 'প্রেসক্রিপশন বা ওষুধের স্ট্রিপের ছবি দিন, নাম বলুন বা লিখুন'],
            [<ScanSearch key="s" size={20} />, stats ? `প্রতিটি নাম মেলানো হয় নিবন্ধিত ${bnInt(stats.products)}টি ওষুধের তালিকার সাথে` : 'প্রতিটি নাম মেলানো হয় নিবন্ধিত ওষুধের তালিকার সাথে'],
            [<MessageCircle key="m" size={20} />, 'ফল আসে বাংলায়: লেখা, কণ্ঠ আর একটি ছবি কার্ড'],
          ].map(([icon, text], k) => (
            <li key={k} className="flex items-center gap-4">
              <span className="relative grid h-11 w-11 shrink-0 place-items-center rounded-full bg-rx-soft text-rx">
                {icon}
                <span className="absolute -right-1 -top-1 grid h-5 w-5 place-items-center rounded-full bg-rx text-[12px] font-semibold text-white">{bn(k + 1)}</span>
              </span>
              <span className="text-[18px]">{text}</span>
            </li>
          ))}
        </ol>
        <p className="mt-8 max-w-[34rem] text-[15px] text-muted">এটি ডাক্তারের পরামর্শের বিকল্প নয়। প্রতিটি সতর্কবার্তা ডাক্তার বা ফার্মাসিস্টকে দেখান।</p>
      </section>

      <section aria-label="উদাহরণ" className="sheet lift relative overflow-hidden px-5 py-7 sm:px-8 lg:py-10">
        <div className="relative">
          <p className="print text-[15px] font-semibold text-rx">℞ দুই প্রেসক্রিপশন, দুই নাম</p>
          {/* faint pad rule lines only where the names are written */}
          <div className="mt-4 min-h-[150px] rounded-xl bg-[repeating-linear-gradient(to_bottom,transparent_0,transparent_37px,rgba(36,64,142,0.08)_37px,rgba(36,64,142,0.08)_38px)] py-3">
            {ex ? <SameMedicine key={ex.ingredient} a={ex.brands[0]} b={ex.brands[1]} ingredient={ex.ingredient} ink caption="একই ওষুধ" />
              : <div className="h-[150px] animate-pulse rounded-2xl bg-paper" />}
          </div>
          <div className="mt-6 border-t border-foil pt-4">
            {ex && <p className="text-[16px] text-muted">নিবন্ধিত তালিকায় <span className="print font-semibold text-ink">{ex.ingredient}</span> আছে {bnInt(ex.brand_count)}টি ব্র্যান্ড নামে, যেমন <span className="print text-ink">{ex.brands.slice(2, 5).join(', ')}</span>।</p>}
            {examples.length > 1 && (
              <div className="mt-4 flex gap-1.5" role="tablist" aria-label="উদাহরণ বদলান">
                {examples.map((e, k) => (
                  <button key={e.ingredient} role="tab" aria-selected={k === i % examples.length} aria-label={e.ingredient} onClick={() => setI(k)}
                    className={`h-2 rounded-full transition-all ${k === i % examples.length ? 'w-6 bg-rx' : 'w-2 bg-foil'}`} />
                ))}
              </div>
            )}
          </div>
          {stats?.eval && (
            <p className="mt-5 flex items-start gap-2 rounded-xl bg-rx-soft px-3 py-2.5 text-[15px] text-rx-deep">
              <ShieldCheck size={18} className="mt-0.5 shrink-0" />
              <span>বাংলাদেশি ডাক্তারদের হাতে লেখা {bnInt(stats.eval.n_test)}টি ওষুধের নামে পরীক্ষা: সঠিক মিল {bnPct(stats.eval.top1)}। নিশ্চিত না হলে অ্যাপ নিজে না ধরে আপনাকে জিজ্ঞেস করে।</span>
            </p>
          )}
        </div>
      </section>
    </motion.main>
  )
}

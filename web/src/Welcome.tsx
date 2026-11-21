import { useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { FileText, ScanSearch, MessageCircle, QrCode, X } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { shareUrl } from './api'

const spring = { type: 'spring' as const, bounce: 0, duration: 0.6 }

// The idea in one picture: two different brands lead to the same ingredient.
export function MedicineGraph({ a = 'Napa', b = 'Ace', ingredient = 'Paracetamol' }: { a?: string; b?: string; ingredient?: string }) {
  const reduce = useReducedMotion()
  const draw = (delay: number) => (reduce ? { initial: false } : {
    initial: { pathLength: 0, opacity: 0 }, animate: { pathLength: 1, opacity: 1 }, transition: { duration: 0.7, delay, ease: 'easeOut' as const },
  })
  const pop = (delay: number) => (reduce ? { initial: false } : {
    initial: { opacity: 0, scale: 0.9, y: 6 }, animate: { opacity: 1, scale: 1, y: 0 }, transition: { ...spring, delay },
  })
  return (
    <svg viewBox="0 0 340 170" className="w-full max-w-[380px]" role="img" aria-label={`${a} আর ${b} দুটোতেই ${ingredient}`}>
      <motion.path d="M96 40 C150 40 150 85 196 85" stroke="#c8382a" strokeWidth="2.5" fill="none" {...draw(0.5)} />
      <motion.path d="M96 130 C150 130 150 85 196 85" stroke="#c8382a" strokeWidth="2.5" fill="none" {...draw(0.7)} />
      <motion.g {...pop(0.1)}>
        <rect x="8" y="22" width="88" height="36" rx="12" fill="#fdeeec" stroke="#c8382a" />
        <text x="52" y="45" textAnchor="middle" fontSize="15" fontWeight="700" fill="#c8382a" fontFamily="Inter Variable">{a}</text>
      </motion.g>
      <motion.g {...pop(0.25)}>
        <rect x="8" y="112" width="88" height="36" rx="12" fill="#fdeeec" stroke="#c8382a" />
        <text x="52" y="135" textAnchor="middle" fontSize="15" fontWeight="700" fill="#c8382a" fontFamily="Inter Variable">{b}</text>
      </motion.g>
      <motion.g {...pop(1.0)}>
        <rect x="196" y="66" width="136" height="38" rx="12" fill="#fff" stroke="#14201c" strokeWidth="1.5" />
        <text x="264" y="90" textAnchor="middle" fontSize="15" fontWeight="700" fill="#14201c" fontFamily="Inter Variable">{ingredient}</text>
      </motion.g>
      <motion.g {...pop(1.3)}>
        <rect x="206" y="118" width="116" height="26" rx="13" fill="#c8382a" />
        <text x="264" y="136" textAnchor="middle" fontSize="13" fontWeight="700" fill="#fff">একই ওষুধ!</text>
      </motion.g>
    </svg>
  )
}

function QrSheet({ onClose }: { onClose: () => void }) {
  const url = shareUrl()
  const local = /^(localhost|127\.|192\.168\.)/.test(window.location.hostname)
  return (
    <>
      <motion.div className="fixed inset-0 z-40 bg-ink/40" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
      <motion.div role="dialog" aria-label="ফোনে খুলুন" className="fixed inset-x-0 bottom-0 z-50 mx-auto max-w-xl rounded-t-[28px] bg-white px-5 pb-[max(24px,env(safe-area-inset-bottom))] pt-4"
        initial={{ y: '100%' }} animate={{ y: 0 }} exit={{ y: '100%' }} transition={{ type: 'spring', bounce: 0, duration: 0.4 }}>
        <div className="flex items-center justify-between">
          <p className="text-lg font-bold">ফোনের ক্যামেরা দিয়ে স্ক্যান করুন</p>
          <button onClick={onClose} aria-label="বন্ধ" className="grid h-9 w-9 place-items-center rounded-full bg-paper"><X size={18} /></button>
        </div>
        <div className="mt-4 flex justify-center"><QRCodeSVG value={url} size={232} marginSize={2} level="M" /></div>
        <div className="mt-3 overflow-x-auto rounded-xl bg-paper px-3 py-2"><p className="whitespace-nowrap text-center font-sans text-[11px] text-muted">{url.replace(/^https?:\/\//, '').replace(/\/$/, '')}</p></div>
        <p className="mt-2 text-sm text-muted">{local ? 'এটি এই ল্যাপটপের লোকাল ঠিকানা; অন্য ফোনের জন্য পাবলিক লিংক থেকে খুলুন।' : 'কোনো অ্যাপ ইনস্টল লাগবে না, ব্রাউজারেই চলবে।'}</p>
      </motion.div>
    </>
  )
}

export function Welcome({ onStart }: { onStart: () => void }) {
  const [qr, setQr] = useState(false)
  return (
    <motion.main className="mx-auto flex min-h-dvh max-w-xl flex-col px-5 pb-10 pt-6"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, y: -12 }} transition={spring}>
      <div className="flex justify-end">
        <motion.button whileTap={{ scale: 0.95 }} onClick={() => setQr(true)} className="flex items-center gap-1.5 rounded-full bg-white px-3 py-1.5 text-sm font-semibold shadow-sm ring-1 ring-line">
          <QrCode size={16} /> ফোনে খুলুন
        </motion.button>
      </div>
      <AnimatePresence>{qr && <QrSheet onClose={() => setQr(false)} />}</AnimatePresence>
      <p className="mt-4 text-sm font-semibold tracking-wide text-brand">এক ওষুধ, দুই নাম</p>
      <h1 className="display mt-2 text-[2.1rem] text-ink">একই ওষুধ, ভিন্ন নাম,<br />দ্বিগুণ ঝুঁকি।</h1>
      <p className="mt-3 text-muted">
        বাংলাদেশে শুধু প্যারাসিটামলেরই ১১৬টা ব্র্যান্ড নাম। দুই ডাক্তারের প্রেসক্রিপশনে দুই নামে একই ওষুধ থাকলে কেউ টেরও পায় না।
      </p>
      <div className="card mt-6 flex justify-center px-3 py-5"><MedicineGraph /></div>
      <ul className="mt-6 space-y-3 text-[17px]">
        {[[<FileText key="a" size={18} />, 'প্রেসক্রিপশন বা ওষুধের স্ট্রিপের ছবি দিন'],
          [<ScanSearch key="b" size={18} />, 'নিবন্ধিত ২১,৩৬৩টি ওষুধের সাথে মিলিয়ে দেখা হবে'],
          [<MessageCircle key="c" size={18} />, 'বাংলায় সহজ উত্তর, প্রতিটির উৎসসহ']].map(([icon, text], i) => (
          <li key={i} className="flex items-center gap-3">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-brand-soft text-brand">{icon}</span>{text}
          </li>))}
      </ul>
      <motion.button whileTap={{ scale: 0.97 }} transition={{ duration: 0.1 }} onClick={onStart}
        className="mt-auto w-full rounded-2xl bg-brand py-4 text-lg font-semibold text-white shadow-lg shadow-brand/20">
        শুরু করুন
      </motion.button>
      <p className="mt-3 text-center text-xs text-muted">এটি ডাক্তারের পরামর্শের বিকল্প নয়। প্রতিটি সতর্কবার্তা ডাক্তার বা ফার্মাসিস্টকে দেখান।</p>
    </motion.main>
  )
}

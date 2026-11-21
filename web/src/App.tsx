import { useEffect, useState } from 'react'
import { AnimatePresence, MotionConfig, motion } from 'motion/react'
import { Loader2, X } from 'lucide-react'
import { api, type CheckResult, type ItemView, type Stats } from './api'
import { Welcome } from './Welcome'
import { CaseScreen } from './CaseScreen'
import { Results } from './Results'
import { TopBar, spring } from './Shell'

type Screen = 'loading' | 'welcome' | 'case' | 'results'

export default function App() {
  const [screen, setScreen] = useState<Screen>(() => (new URLSearchParams(window.location.search).get('case') ? 'loading' : 'welcome'))
  const [caseId, setCaseId] = useState<string | null>(null)
  const [items, setItems] = useState<ItemView[]>([])
  const [result, setResult] = useState<CheckResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [stats, setStats] = useState<Stats | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.stats().then(setStats).catch(() => setStats(null)) }, [])

  // Opened by link (?case=...): continue that case: confirm screen if anything is unsure, else results.
  useEffect(() => {
    const cid = new URLSearchParams(window.location.search).get('case')
    if (!cid) return
    api.getCase(cid).then(async (c) => {
      setCaseId(c.case_id)
      setItems(c.items)
      if (c.items.some((i) => i.needs_confirm) || !c.items.length) setScreen('case')
      else { setResult(await api.check(c.case_id)); setScreen('results') }
    }).catch(() => { setError('এই যাচাইটির মেয়াদ শেষ (২ ঘণ্টা)। নতুন করে শুরু করুন।'); setScreen('welcome') })
  }, [])

  useEffect(() => { window.scrollTo({ top: 0 }) }, [screen])

  async function start() {
    setError(null)
    setBusy(true)
    try {
      const c = await api.newCase()
      setCaseId(c.case_id)
      setItems([])
      setResult(null)
      setScreen('case')
    } catch {
      setError('সার্ভার চালু নেই। ল্যাপটপে ব্যাকএন্ড চালু করে আবার চেষ্টা করুন।')
    }
    setBusy(false)
  }

  async function check() {
    if (!caseId) return
    setBusy(true)
    try {
      setResult(await api.check(caseId))
      setScreen('results')
    } catch (e) {
      setError(`মিলিয়ে দেখা যায়নি (${(e as Error).message})। আবার চেষ্টা করুন।`)
    }
    setBusy(false)
  }

  const step = screen === 'case' ? (items.some((i) => i.needs_confirm) ? 1 : 0) : screen === 'results' ? 2 : null
  return (
    <MotionConfig reducedMotion="user">
      <TopBar step={step} onNew={screen === 'case' || screen === 'results' ? start : null} />
      <AnimatePresence>
        {error && (
          <motion.div role="alert" className="fixed inset-x-4 top-20 z-50 mx-auto flex max-w-lg items-start gap-3 rounded-2xl bg-danger p-4 text-white shadow-lg"
            initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }} transition={spring}>
            <p className="flex-1">{error}</p>
            <button onClick={() => setError(null)} aria-label="বন্ধ"><X size={20} /></button>
          </motion.div>
        )}
      </AnimatePresence>
      <AnimatePresence mode="wait">
        {screen === 'loading' && <div key="l" className="grid min-h-[70dvh] place-items-center"><Loader2 className="animate-spin text-rx" size={28} /></div>}
        {screen === 'welcome' && <Welcome key="w" stats={stats} onStart={start} starting={busy} />}
        {screen === 'case' && caseId && <CaseScreen key="c" caseId={caseId} items={items} setItems={setItems} onCheck={check} checking={busy} stats={stats} />}
        {screen === 'results' && result && <Results key="r" result={result} onBack={() => setScreen('case')} />}
      </AnimatePresence>
    </MotionConfig>
  )
}

import { useEffect, useState } from 'react'
import { AnimatePresence, MotionConfig } from 'motion/react'
import { Loader2 } from 'lucide-react'
import { api, type CheckResult, type ItemView } from './api'
import { Welcome } from './Welcome'
import { CaseScreen } from './CaseScreen'
import { Results } from './Results'

type Screen = 'loading' | 'welcome' | 'case' | 'results'

export default function App() {
  const [screen, setScreen] = useState<Screen>(() => (new URLSearchParams(window.location.search).get('case') ? 'loading' : 'welcome'))
  const [caseId, setCaseId] = useState<string | null>(null)
  const [items, setItems] = useState<ItemView[]>([])
  const [result, setResult] = useState<CheckResult | null>(null)
  const [error, setError] = useState<string | null>(null)

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

  async function start() {
    setError(null)
    try {
      const c = await api.newCase()
      setCaseId(c.case_id)
      setItems([])
      setScreen('case')
    } catch {
      setError('সার্ভারের সাথে সংযোগ হচ্ছে না। ইন্টারনেট দেখে আবার চেষ্টা করুন।')
    }
  }

  async function check() {
    if (!caseId) return
    try {
      setResult(await api.check(caseId))
      setScreen('results')
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <MotionConfig reducedMotion="user">
      {error && <p role="alert" className="fixed inset-x-4 top-4 z-50 rounded-xl bg-danger p-3 text-center text-white">{error}</p>}
      <AnimatePresence mode="wait">
        {screen === 'loading' && <div key="l" className="grid min-h-dvh place-items-center"><Loader2 className="animate-spin text-brand" size={28} /></div>}
        {screen === 'welcome' && <Welcome key="w" onStart={start} />}
        {screen === 'case' && caseId && <CaseScreen key="c" caseId={caseId} items={items} setItems={setItems} onCheck={check} />}
        {screen === 'results' && result && <Results key="r" result={result} onBack={() => setScreen('case')} />}
      </AnimatePresence>
    </MotionConfig>
  )
}

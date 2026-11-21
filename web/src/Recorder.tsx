import { useEffect, useRef, useState } from 'react'
import { motion } from 'motion/react'
import { Mic, Square, X } from 'lucide-react'
import { bn } from './api'

const MAX_SECONDS = 60

// Voice note sheet: records with the phone's microphone (webm/opus on Android, mp4 on iPhone) and hands the
// audio back. Recording starts on open and stops on the button, on close, or after 60 seconds.
export function Recorder({ onDone, onClose }: { onDone: (audio: Blob) => void; onClose: () => void }) {
  const [seconds, setSeconds] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const rec = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])
  const send = useRef(false)

  useEffect(() => {
    let stream: MediaStream | null = null
    let timer: number | undefined
    navigator.mediaDevices?.getUserMedia({ audio: true }).then((s) => {
      stream = s
      const type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find((m) => MediaRecorder.isTypeSupported(m))
      const r = new MediaRecorder(s, type ? { mimeType: type } : undefined)
      r.ondataavailable = (e) => e.data.size && chunks.current.push(e.data)
      r.onstop = () => {
        s.getTracks().forEach((tr) => tr.stop())
        if (send.current && chunks.current.length) onDone(new Blob(chunks.current, { type: r.mimeType }))
      }
      r.start(250)
      rec.current = r
      timer = window.setInterval(() => setSeconds((x) => {
        if (x + 1 >= MAX_SECONDS) { send.current = true; r.state === 'recording' && r.stop() }
        return x + 1
      }), 1000)
    }).catch(() => setError('মাইক্রোফোন চালু করা যায়নি। ব্রাউজারে মাইক্রোফোনের অনুমতি দিন।'))
    if (!navigator.mediaDevices) setError('এই ব্রাউজারে ভয়েস রেকর্ড করা যায় না। নাম লিখে দিন।')
    return () => {
      window.clearInterval(timer)
      if (rec.current?.state === 'recording') rec.current.stop()
      stream?.getTracks().forEach((tr) => tr.stop())
    }
  }, [onDone])

  function stop(sendIt: boolean) {
    send.current = sendIt
    if (rec.current?.state === 'recording') rec.current.stop()
    if (!sendIt) onClose()
  }

  return (
    <>
      <motion.div className="fixed inset-0 z-40 bg-ink/40" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => stop(false)} />
      <motion.div role="dialog" aria-label="ভয়েস নোট" className="fixed inset-x-0 bottom-0 z-50 mx-auto max-w-xl rounded-t-[28px] bg-white px-5 pb-[max(24px,env(safe-area-inset-bottom))] pt-4"
        initial={{ y: '100%' }} animate={{ y: 0 }} exit={{ y: '100%' }} transition={{ type: 'spring', bounce: 0, duration: 0.4 }}>
        <div className="flex items-center justify-between">
          <p className="text-lg font-bold">ওষুধের নাম বলুন</p>
          <button onClick={() => stop(false)} aria-label="বাতিল" className="grid h-9 w-9 place-items-center rounded-full bg-paper"><X size={18} /></button>
        </div>
        <p className="mt-1 text-muted">যেমন: “নাপা পাঁচশো, দিনে দুইবার; রাতে সেকলো বিশ”</p>
        {error ? <p className="mt-6 rounded-xl bg-danger-soft p-3 text-danger">{error}</p> : (
          <div className="mt-6 flex flex-col items-center">
            <div className="relative grid h-28 w-28 place-items-center">
              <motion.span className="absolute inset-0 rounded-full bg-danger/15" animate={{ scale: [1, 1.25, 1] }} transition={{ duration: 1.6, repeat: Infinity, ease: 'easeInOut' }} />
              <span className="relative grid h-20 w-20 place-items-center rounded-full bg-danger text-white"><Mic size={34} /></span>
            </div>
            <p className="mt-3 font-sans text-2xl font-semibold tabular-nums">০:{bn(String(seconds).padStart(2, '0'))}</p>
            <p className="text-sm text-muted">সর্বোচ্চ {bn(MAX_SECONDS)} সেকেন্ড</p>
          </div>
        )}
        <motion.button whileTap={{ scale: 0.97 }} disabled={!!error} onClick={() => stop(true)}
          className="mt-6 flex w-full items-center justify-center gap-2 rounded-2xl bg-ink py-4 text-lg font-semibold text-white disabled:opacity-40">
          <Square size={18} /> থামান ও পাঠান
        </motion.button>
      </motion.div>
    </>
  )
}

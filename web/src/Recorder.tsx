import { useEffect, useRef, useState } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { Mic, Square } from 'lucide-react'
import { bn } from './api'
import { t as tt, useCopy } from './copy'
import { Press, Sheet } from './Shell'

const MAX_SECONDS = 60

// Voice note sheet: records with the phone's microphone (webm/opus on Android, mp4 on iPhone) and hands the audio
// back. Recording starts when the person opens it (they tapped "বলুন") and stops on the button, on close, or at 60 s.
export function Recorder({ onDone, onClose }: { onDone: (audio: Blob) => void; onClose: () => void }) {
  const t = useCopy()
  const reduce = useReducedMotion()
  const [seconds, setSeconds] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const rec = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])
  const send = useRef(false)

  useEffect(() => {
    let stream: MediaStream | null = null
    let timer: number | undefined
    let cancelled = false
    // Phones allow the microphone only on https pages; on an http address the browser hides it before any prompt.
    if (!window.isSecureContext) { setError(tt('rec.needs_https')); return }
    if (!navigator.mediaDevices) { setError(tt('rec.unsupported')); return }
    navigator.mediaDevices.getUserMedia({ audio: true }).then((s) => {
      if (cancelled) { s.getTracks().forEach((tr) => tr.stop()); return }   // closed while the permission prompt was open
      stream = s
      const type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find((m) => MediaRecorder.isTypeSupported(m))
      const r = new MediaRecorder(s, type ? { mimeType: type } : undefined)
      r.ondataavailable = (e) => { if (e.data.size) chunks.current.push(e.data) }
      r.onstop = () => {
        s.getTracks().forEach((tr) => tr.stop())
        if (send.current && chunks.current.length) onDone(new Blob(chunks.current, { type: r.mimeType }))
      }
      r.start(250)
      rec.current = r
      timer = window.setInterval(() => setSeconds((x) => {
        if (x + 1 >= MAX_SECONDS) { send.current = true; if (r.state === 'recording') r.stop() }
        return x + 1
      }), 1000)
    }).catch(() => setError(tt('rec.no_mic')))
    return () => {
      cancelled = true
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
    <Sheet label={t('rec.title')} onClose={() => stop(false)}>
      <p className="mt-1 text-muted">{t('rec.example')}</p>
      {error ? <div role="alert" className="mt-6 rounded-xl bg-danger-soft p-3 text-danger">
          <p>{error}</p>
          {!window.isSecureContext && /^\d+\.\d+\.\d+\.\d+$/.test(location.hostname) && (
            <a href={`https://${location.hostname}:8443${location.pathname}`} className="mt-2 inline-block font-semibold underline">{`https://${location.hostname}:8443`}</a>
          )}
        </div> : (
        <div className="mt-6 flex flex-col items-center">
          <div className="relative grid h-28 w-28 place-items-center">
            {!reduce && <motion.span className="absolute inset-0 rounded-full bg-danger/15" animate={{ scale: [1, 1.2, 1] }} transition={{ duration: 1.6, repeat: Infinity, ease: 'easeInOut' }} />}
            <span className="relative grid h-20 w-20 place-items-center rounded-full bg-danger text-white"><Mic size={34} aria-hidden /></span>
          </div>
          <p className="print mt-3 text-[1.5rem] font-semibold tabular-nums" aria-live="off">০:{bn(String(seconds).padStart(2, '0'))}</p>
          <p className="text-[0.9rem] text-muted">{t('rec.max', { n: bn(MAX_SECONDS) })}</p>
        </div>
      )}
      <Press disabled={!!error} onClick={() => stop(true)}
        className="mt-6 flex min-h-14 w-full items-center justify-center gap-2 rounded-2xl bg-ink text-[1.1rem] font-semibold text-white disabled:opacity-40">
        <Square size={18} aria-hidden />{t('rec.stop')}
      </Press>
    </Sheet>
  )
}

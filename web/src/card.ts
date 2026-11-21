// Picture card: the result as one PNG an elderly parent can keep, or a family member can show the pharmacist.
// Drawn on a canvas in the browser. Height follows the content, every line wraps to the card width, nothing is cut.
// Same verdict as the screen; morning / noon / night pictograms for people who do not read.
import { bn, type CheckResult, type ItemView } from './api'
import { t } from './copy'

const W = 1080
const PAD = 64
const BN = '"Hind Siliguri", "Inter Variable", sans-serif'
const PRINT = '"Anek Bangla Variable", "Inter Variable", sans-serif'

type Block = { h: number; draw: (ctx: CanvasRenderingContext2D, y: number) => void }

function css(name: string, fallback: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

function wrap(ctx: CanvasRenderingContext2D, text: string, width: number): string[] {
  const lines: string[] = []
  let line = ''
  for (const word of text.split(/\s+/)) {
    const next = line ? `${line} ${word}` : word
    if (ctx.measureText(next).width > width && line) { lines.push(line); line = word } else line = next
  }
  if (line) lines.push(line)
  return lines
}

// Pictograms: rising sun on the horizon (morning), full sun (noon), crescent moon (night).
function icon(ctx: CanvasRenderingContext2D, kind: 'morning' | 'noon' | 'night', x: number, y: number, on: boolean, ink: string, off: string) {
  ctx.save()
  ctx.strokeStyle = on ? ink : off
  ctx.fillStyle = on ? ink : off
  ctx.lineWidth = 4
  ctx.lineCap = 'round'
  if (kind === 'night') {
    ctx.beginPath(); ctx.arc(x, y, 18, 0.35 * Math.PI, 1.65 * Math.PI); ctx.arc(x + 9, y - 3, 14, 1.55 * Math.PI, 0.45 * Math.PI, true); ctx.fill()
  } else {
    const cy = y + (kind === 'morning' ? 6 : 0)
    ctx.beginPath(); ctx.arc(x, cy, 12, 0, Math.PI * 2); ctx.fill()
    const rays = kind === 'morning' ? [-150, -120, -90, -60, -30] : [-180, -135, -90, -45, 0, 45, 90, 135]
    for (const a of rays) {
      const r = (a * Math.PI) / 180
      ctx.beginPath(); ctx.moveTo(x + Math.cos(r) * 17, cy + Math.sin(r) * 17); ctx.lineTo(x + Math.cos(r) * 25, cy + Math.sin(r) * 25); ctx.stroke()
    }
    if (kind === 'morning') { ctx.beginPath(); ctx.moveTo(x - 28, y + 22); ctx.lineTo(x + 28, y + 22); ctx.stroke() }
  }
  ctx.restore()
}

const dose = (v: number | null) => (v === null ? '' : v === 0.5 ? '½' : bn(v))

export async function drawCard(r: CheckResult, items: ItemView[]): Promise<Blob> {
  // load the Bangla subsets too (fontsource splits Bengali into its own unicode-range face)
  await Promise.all(['400', '600', '700'].map((w) => document.fonts.load(`${w} 40px "Hind Siliguri"`, 'অআক১')))
  await document.fonts.load('600 40px "Anek Bangla Variable"', 'Napa অ').catch(() => [])
  const C = { ink: css('--color-ink', '#17251f'), muted: css('--color-muted', '#5b6a65'), rx: css('--color-rx', '#0b5d4b'),
    danger: css('--color-danger', '#c8382a'), warn: css('--color-warn', '#8a5000'), foil: css('--color-foil', '#dce3e0'),
    soft: { red: css('--color-danger-soft', '#fcedeb'), amber: css('--color-warn-soft', '#fbf1e1'), info: css('--color-paper', '#f6f8f7') } }
  const sevColor = { red: C.danger, amber: C.warn, info: C.muted }
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')!
  if (typeof ctx.roundRect !== 'function') {   // older Safari: square corners instead of a crash
    (ctx as CanvasRenderingContext2D).roundRect = function (x: number, y: number, w: number, h: number) { this.rect(x, y, w, h) }
  }
  const inner = W - PAD * 2
  const blocks: Block[] = []
  const reds = r.findings.filter((f) => f.severity === 'red').length
  const ambers = r.findings.filter((f) => f.severity === 'amber').length
  const verdict = reds ? t('verdict.red', { n: bn(reds) }) : ambers ? t('verdict.amber', { n: bn(ambers) }) : t('card.ok')
  const verdictColor = reds ? C.danger : ambers ? C.warn : C.rx

  ctx.font = `700 54px ${BN}`
  const vLines = wrap(ctx, verdict, inner)
  blocks.push({ h: 70 + vLines.length * 66 + 20, draw: (c, y) => {
    c.fillStyle = C.rx; c.font = `600 32px ${BN}`; c.fillText(t('app.name'), PAD, y + 44)
    c.fillStyle = verdictColor; c.font = `700 54px ${BN}`
    vLines.forEach((l, i) => c.fillText(l, PAD, y + 70 + 52 + i * 66))
  } })

  for (const f of r.findings.filter((x) => x.severity !== 'info')) {
    ctx.font = `700 38px ${BN}`
    const title = wrap(ctx, `${t(`sev.${f.severity}`)}: ${f.title_bn}`, inner - 56)
    ctx.font = `400 36px ${BN}`
    const body = wrap(ctx, f.bn, inner - 56)
    const h = 40 + title.length * 50 + 10 + body.length * 52 + 30
    blocks.push({ h: h + 24, draw: (c, y) => {
      c.fillStyle = C.soft[f.severity]; c.beginPath(); c.roundRect(PAD, y, inner, h, 28); c.fill()
      c.fillStyle = sevColor[f.severity]; c.beginPath(); c.roundRect(PAD, y, 12, h, [28, 0, 0, 28]); c.fill()
      c.font = `700 38px ${BN}`
      title.forEach((l, i) => c.fillText(l, PAD + 40, y + 78 + i * 50))
      c.fillStyle = C.ink; c.font = `400 36px ${BN}`
      body.forEach((l, i) => c.fillText(l, PAD + 40, y + 40 + title.length * 50 + 46 + i * 52))
    } })
  }

  blocks.push({ h: 86, draw: (c, y) => { c.fillStyle = C.ink; c.font = `700 40px ${BN}`; c.fillText(t('card.meds'), PAD, y + 64) } })
  for (const m of r.medicines.filter((x) => x.taking !== 'stopped')) {
    const it = items.find((i) => m.items.includes(i.item_id) && i.schedule && [i.schedule.morning, i.schedule.noon, i.schedule.night].some((v) => v !== null))
    const s = it?.schedule
    ctx.font = `400 30px ${BN}`
    const sub = wrap(ctx, m.path.ingredients.map((x) => x.name).join(' + '), inner)
    const perDay = !s && m.per_day ? t('sched.per_day', { n: bn(m.per_day) }) : ''
    blocks.push({ h: 56 + sub.length * 42 + (s ? 96 : perDay ? 46 : 0) + 26, draw: (c, y) => {
      c.fillStyle = C.ink; c.font = `600 38px ${PRINT}`; c.fillText(`${m.brand} ${m.strength}`, PAD, y + 44)
      c.fillStyle = C.muted; c.font = `400 30px ${BN}`
      sub.forEach((l, i) => c.fillText(l, PAD, y + 44 + 46 + i * 42))
      const top = y + 44 + 46 + sub.length * 42
      if (s) {
        const slots: ['morning' | 'noon' | 'night', number | null][] = [['morning', s.morning], ['noon', s.noon], ['night', s.night]]
        slots.forEach(([k, v], i) => {
          const x = PAD + 40 + i * 300
          const on = !!v && v > 0
          icon(c, k, x, top + 34, on, C.rx, C.foil)
          c.fillStyle = on ? C.ink : C.muted; c.font = `${on ? 700 : 400} 32px ${BN}`
          c.fillText(`${t(`card.${k}`)} ${on ? dose(v) : '—'}`, x + 44, top + 46)
        })
      } else if (perDay) {
        c.fillStyle = C.ink; c.font = `600 30px ${BN}`; c.fillText(perDay, PAD, top + 30)
      }
    } })
  }

  const date = new Date().toLocaleDateString('bn-BD', { day: 'numeric', month: 'long', year: 'numeric' })
  ctx.font = `600 34px ${BN}`
  const ask = wrap(ctx, t('card.show'), inner)
  ctx.font = `400 26px ${BN}`
  const meta = [...wrap(ctx, t('card.not_advice'), inner), ...wrap(ctx, `${date} · ${t('card.check_no')} ${r.request_id} · ${t('app.team')}`, inner)]
  blocks.push({ h: 60 + ask.length * 48 + meta.length * 38 + 20, draw: (c, y) => {
    c.strokeStyle = C.foil; c.lineWidth = 2; c.beginPath(); c.moveTo(PAD, y + 24); c.lineTo(W - PAD, y + 24); c.stroke()
    c.fillStyle = C.ink; c.font = `600 34px ${BN}`
    ask.forEach((l, i) => c.fillText(l, PAD, y + 80 + i * 48))
    c.fillStyle = C.muted; c.font = `400 26px ${BN}`
    meta.forEach((l, i) => c.fillText(l, PAD, y + 80 + ask.length * 48 + i * 38))
  } })

  const height = PAD + blocks.reduce((s, b) => s + b.h, 0) + PAD
  canvas.width = W
  canvas.height = height
  ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, W, height)
  let y = PAD
  for (const b of blocks) { b.draw(ctx, y); y += b.h }
  return new Promise((resolve, reject) => canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('card could not be drawn'))), 'image/png'))
}

export function summaryText(r: CheckResult): string {
  const lines = r.findings.filter((f) => f.severity !== 'info').map((f) => `• ${t(`sev.${f.severity}`)}: ${f.bn}`)
  return [t('app.name'), ...lines, t('card.show'), t('card.not_advice')].join('\n')
}

// Phone: the share sheet (WhatsApp, Messenger and others appear there). Laptop: save the PNG.
// Returns null when the person closes the share sheet, so nothing is downloaded behind their back.
export async function shareCard(blob: Blob, r: CheckResult): Promise<'shared' | 'downloaded' | null> {
  const file = new File([blob], 'ek-oshudh-card.png', { type: 'image/png' })
  if (navigator.canShare?.({ files: [file] })) {
    try { await navigator.share({ files: [file], text: summaryText(r) }); return 'shared' } catch { return null }
  }
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'ek-oshudh-card.png'
  a.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 2000)
  return 'downloaded'
}

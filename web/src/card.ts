// Picture card: the result as one PNG an elderly parent can keep or forward on WhatsApp.
// Drawn on a canvas in the browser (no server, works offline). The canvas height is computed from the content,
// so nothing is ever cut off; long sentences wrap at word boundaries inside the card width.
import { bn, type CheckResult } from './api'

const W = 1080
const PAD = 64
const COLORS = { red: '#c8382a', amber: '#b8730c', info: '#5d6b66' } as const
const SOFT = { red: '#fdeeec', amber: '#fdf4e3', info: '#f5f7f4' } as const
const WORD = { red: 'সতর্কতা', amber: 'খেয়াল রাখুন', info: 'তথ্য' } as const
const BN = '"Hind Siliguri", "Inter Variable", sans-serif'

type Block = { h: number; draw: (ctx: CanvasRenderingContext2D, y: number) => void }

function wrap(ctx: CanvasRenderingContext2D, text: string, width: number): string[] {
  const lines: string[] = []
  let line = ''
  for (const word of text.split(/\s+/)) {
    const next = line ? `${line} ${word}` : word
    if (ctx.measureText(next).width > width && line) {
      lines.push(line)
      line = word
    } else line = next
  }
  if (line) lines.push(line)
  return lines
}

export async function drawCard(r: CheckResult): Promise<Blob> {
  await Promise.all(['400', '600', '700'].map((w) => document.fonts.load(`${w} 40px "Hind Siliguri"`)))
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')!
  const inner = W - PAD * 2
  const blocks: Block[] = []

  // Header
  blocks.push({ h: 150, draw: (c, y) => {
    c.fillStyle = '#0e6b5c'; c.font = `600 34px ${BN}`; c.fillText('এক ওষুধ, দুই নাম', PAD, y + 50)
    const reds = r.findings.filter((f) => f.severity === 'red').length
    c.fillStyle = '#14201c'; c.font = `700 56px ${BN}`
    c.fillText(reds ? `${bn(reds)}টি গুরুত্বপূর্ণ সতর্কতা` : 'বড় কোনো সমস্যা পাওয়া যায়নি', PAD, y + 120)
  } })

  // Findings
  for (const f of r.findings) {
    ctx.font = `700 38px ${BN}`
    const title = wrap(ctx, `${WORD[f.severity]}: ${f.title_bn}`, inner - 56)
    ctx.font = `400 36px ${BN}`
    const body = wrap(ctx, f.bn, inner - 56)
    const th = title.length * 50
    const h = 40 + th + 10 + body.length * 52 + 30
    blocks.push({ h: h + 24, draw: (c, y) => {
      c.fillStyle = SOFT[f.severity]; c.beginPath(); c.roundRect(PAD, y, inner, h, 28); c.fill()
      c.fillStyle = COLORS[f.severity]; c.beginPath(); c.roundRect(PAD, y, 12, h, [28, 0, 0, 28]); c.fill()
      c.font = `700 38px ${BN}`
      title.forEach((line, i) => c.fillText(line, PAD + 40, y + 40 + 38 + i * 50))
      c.fillStyle = '#14201c'; c.font = `400 36px ${BN}`
      body.forEach((line, i) => c.fillText(line, PAD + 40, y + 40 + th + 10 + 36 + i * 52))
    } })
  }

  // Medicines
  blocks.push({ h: 80, draw: (c, y) => { c.fillStyle = '#14201c'; c.font = `700 40px ${BN}`; c.fillText('ওষুধের তালিকা', PAD, y + 60) } })
  for (const m of r.medicines) {
    const ing = m.path.ingredients.map((x) => x.name).join(' + ')
    ctx.font = `400 30px ${BN}`
    const sub = wrap(ctx, `${ing} · ${m.from_rx ? `প্রেসক্রিপশন: ${m.doctors.join(', ')}` : 'প্রেসক্রিপশনে নেই'}`, inner)
    blocks.push({ h: 56 + sub.length * 42 + 20, draw: (c, y) => {
      c.fillStyle = '#14201c'; c.font = `700 36px ${BN}`; c.fillText(`${m.brand} ${m.strength}`, PAD, y + 44)
      c.fillStyle = '#5d6b66'; c.font = `400 30px ${BN}`
      sub.forEach((line, i) => c.fillText(line, PAD, y + 44 + 46 + i * 42))
    } })
  }

  // Footer: wrapped too, so a long date or id never runs off the card
  const date = new Date().toLocaleDateString('bn-BD', { day: 'numeric', month: 'long', year: 'numeric' })
  ctx.font = `600 34px ${BN}`
  const ask = wrap(ctx, 'এই কার্ডটি ডাক্তার বা ফার্মাসিস্টকে দেখান।', inner)
  ctx.font = `400 26px ${BN}`
  const meta = [...wrap(ctx, 'এটি ডাক্তারের পরামর্শের বিকল্প নয়।', inner), ...wrap(ctx, `${date} · যাচাই নং ${r.request_id}`, inner)]
  blocks.push({ h: 60 + ask.length * 48 + meta.length * 38 + 20, draw: (c, y) => {
    c.strokeStyle = '#e3e8e5'; c.lineWidth = 2; c.beginPath(); c.moveTo(PAD, y + 24); c.lineTo(W - PAD, y + 24); c.stroke()
    c.fillStyle = '#14201c'; c.font = `600 34px ${BN}`
    ask.forEach((line, i) => c.fillText(line, PAD, y + 80 + i * 48))
    c.fillStyle = '#5d6b66'; c.font = `400 26px ${BN}`
    meta.forEach((line, i) => c.fillText(line, PAD, y + 80 + ask.length * 48 + i * 38))
  } })

  const height = PAD + blocks.reduce((s, b) => s + b.h, 0) + PAD
  canvas.width = W
  canvas.height = height
  ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, W, height)
  ctx.textBaseline = 'alphabetic'
  let y = PAD
  for (const b of blocks) { b.draw(ctx, y); y += b.h }
  return new Promise((resolve) => canvas.toBlob((blob) => resolve(blob!), 'image/png'))
}

export function summaryText(r: CheckResult): string {
  const lines = r.findings.map((f) => `• ${WORD[f.severity]}: ${f.bn}`)
  return ['এক ওষুধ, দুই নাম: যাচাইয়ের ফল', ...lines, `ওষুধ: ${r.medicines.map((m) => `${m.brand} ${m.strength}`).join(', ')}`,
    'এটি ডাক্তারের পরামর্শের বিকল্প নয়। ডাক্তার বা ফার্মাসিস্টকে দেখান।'].join('\n')
}

// Share the PNG through the phone's share sheet (WhatsApp appears there); fall back to download + wa.me text link.
export async function shareCard(r: CheckResult): Promise<'shared' | 'downloaded'> {
  const blob = await drawCard(r)
  const file = new File([blob], 'ek-oshudh-card.png', { type: 'image/png' })
  const text = summaryText(r)
  if (navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file], text })
      return 'shared'
    } catch { /* user closed the sheet: fall through to download */ }
  }
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = 'ek-oshudh-card.png'
  a.click()
  window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, '_blank', 'noopener')
  return 'downloaded'
}

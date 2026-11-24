import { expect, test, type Page } from '@playwright/test'

// The judge's path, end to end, on the real server: sample case -> ask "taken now?" -> red reveal -> card -> details;
// plus the not-sure path (registry search) and remove/undo. No horizontal scrolling at any step, on laptop and phone.
const shots = (name: string) => `e2e/screens/${test.info().project.name}-${name}.png`

async function noSideScroll(page: Page) {
  const extra = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(extra, 'page scrolls sideways').toBe(0)
}

test('sample case: asks first, warns only when both are taken now', async ({ page }) => {
  await page.route('**/speech', (r) => r.fulfill({ status: 200, contentType: 'audio/wav', body: Buffer.alloc(64) }))
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await noSideScroll(page)
  await page.screenshot({ path: shots('1-welcome'), fullPage: true })

  await page.getByRole('button', { name: 'নমুনা দেখুন' }).click()
  await expect(page.getByRole('article')).toHaveCount(3)
  await noSideScroll(page)
  await page.screenshot({ path: shots('2-case'), fullPage: true })

  await page.getByRole('button', { name: /মিলিয়ে দেখুন/ }).click()
  await expect(page.getByText('দুটোই কি এখন খাচ্ছেন?').first()).toBeVisible()
  await expect(page.getByText('গুরুত্বপূর্ণ সতর্কতা')).toHaveCount(0)
  await page.screenshot({ path: shots('3-ask'), fullPage: true })

  for (const brand of ['Napa', 'Ace']) {
    await page.locator(`[role="radiogroup"][aria-label^="${brand}"]`).getByRole('radio', { name: 'এখন খাচ্ছেন' }).click()
    await page.waitForTimeout(600)
  }
  await expect(page.getByText('গুরুত্বপূর্ণ সতর্কতা')).toBeVisible()
  await expect(page.getByText('Paracetamol').first()).toBeVisible()
  await noSideScroll(page)
  await page.screenshot({ path: shots('4-reveal'), fullPage: true })

  await page.getByRole('button', { name: 'ফার্মাসিস্টকে দেখানোর কার্ড' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('img')).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'ফিরে যান' })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)

  await page.getByRole('button', { name: 'কীভাবে জানলাম' }).click()
  await expect(page.getByText('নাম মেলানোর পরীক্ষা')).toBeVisible()
  await noSideScroll(page)
  await page.screenshot({ path: shots('5-details'), fullPage: true })
})

test('not sure: search the registry, remove and undo', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'ওষুধের ব্যাগ পরীক্ষা করুন' }).click()
  await page.getByRole('button', { name: /লিখে দিন/ }).click()
  await page.locator('textarea').fill('Seclo 20\nNap 500')
  await page.getByRole('button', { name: 'তালিকায় যোগ করুন' }).click()
  await expect(page.getByText('নামটি নিশ্চিত নয়')).toBeVisible()
  await page.getByRole('button', { name: 'কোনোটিই নয়, নাম লিখুন' }).click()
  await page.getByLabel('ওষুধের নাম লিখে খুঁজুন').fill('napa extra')
  await page.getByRole('button', { name: /Napa Extra/ }).first().click()
  await expect(page.getByText('নামটি নিশ্চিত নয়')).toHaveCount(0)
  await expect(page.getByRole('article').filter({ hasText: 'Napa Extra' })).toBeVisible()
  await noSideScroll(page)
  await page.screenshot({ path: shots('6-chosen'), fullPage: true })

  await page.getByRole('button', { name: /বাদ দিন: Seclo/ }).click()
  await expect(page.getByRole('article')).toHaveCount(1)
  await page.getByRole('button', { name: 'ফিরিয়ে আনুন' }).click()
  await expect(page.getByRole('article')).toHaveCount(2)
})

test('an unchecked line is never shown as an all-clear', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'ওষুধের ব্যাগ পরীক্ষা করুন' }).click()
  await page.getByRole('button', { name: /লিখে দিন/ }).click()
  await page.locator('textarea').fill('Seclo 20\nNap 500')
  await page.getByRole('button', { name: 'তালিকায় যোগ করুন' }).click()
  await expect(page.getByText('নামটি নিশ্চিত নয়')).toBeVisible()
  await page.getByRole('button', { name: /মিলিয়ে দেখুন/ }).click()
  await expect(page.getByRole('heading', { name: '১টি ওষুধ যাচাই বাকি' })).toBeVisible()
  await expect(page.getByText('দুবার পাওয়া যায়নি')).toHaveCount(0)
  await expect(page.getByText('নাম নিশ্চিত হয়নি, তাই যাচাইয়ে ধরা হয়নি')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'ওষুধগুলো যোগ করুন' })).toHaveCount(0)   // the screen change has settled
  await noSideScroll(page)
  await page.screenshot({ path: shots('6-partial'), fullPage: true })
  await page.getByRole('button', { name: 'নামগুলো নিশ্চিত করুন' }).click()
  await expect(page.getByText('নামটি নিশ্চিত নয়')).toBeVisible()
})

test('every verdict heading fits on one line', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  const lines = await page.evaluate(async () => {
    const ui = (await (await fetch('/api/copy')).json()).ui as Record<string, string>
    const texts = ['verdict.red', 'verdict.amber', 'verdict.partial', 'verdict.ok'].map((k) => ui[k].replace('{n}', '১২'))
    const box = document.createElement('div'); box.className = 'mx-auto max-w-2xl px-4'; document.body.appendChild(box)
    return texts.map((text) => {
      const h = document.createElement('h2'); h.className = 'display text-[2rem] sm:text-[2.4rem]'; h.textContent = text
      h.style.lineHeight = '1.2'; box.appendChild(h)
      return { text, lines: Math.round(h.getBoundingClientRect().height / (parseFloat(getComputedStyle(h).fontSize) * 1.2)) }
    })
  })
  for (const l of lines) expect(l.lines, l.text).toBe(1)
})

// The welcome example plays by itself (the story's pairs first) so it draws the eye while the team talks; it can be
// paused, and it never moves for someone who asked the system to reduce motion.
test('welcome example: story pairs first, moves on by itself, can be paused', async ({ page }) => {
  await page.goto('/')
  const card = page.locator('section').first()
  await expect(card.getByText('Napa', { exact: true })).toBeVisible()
  await expect(card.getByText('Paracetamol', { exact: true })).toBeVisible()
  await expect(card.getByText('Alatrol', { exact: true })).toBeVisible({ timeout: 6000 })
  await expect(card.getByText('Cetirizine', { exact: true })).toBeVisible()
  await card.getByRole('button', { name: 'উদাহরণ থামান' }).click()
  const pair = async () => card.locator('.hand').allInnerTexts()
  const paused = await pair()
  await page.waitForTimeout(6000)
  expect(await pair()).toEqual(paused)
  await noSideScroll(page)
})

test('welcome example stays still when the system asks for reduced motion', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  const card = page.locator('section').first()
  await expect(card.getByText('Napa', { exact: true })).toBeVisible()
  await page.waitForTimeout(6500)
  await expect(card.getByText('Napa', { exact: true })).toBeVisible()
  await expect(card.getByRole('button', { name: 'উদাহরণ থামান' })).toHaveCount(0)
})

// A prescription can be photographed on the spot (camera) or picked from the gallery (one or several saved photos).
test('prescription: take a photo with the camera or pick from the gallery', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'ওষুধের ব্যাগ পরীক্ষা করুন' }).click()
  await page.getByRole('button', { name: /প্রেসক্রিপশন/ }).click()
  const camera = page.getByRole('button', { name: /ক্যামেরায় তুলুন/ })
  const gallery = page.getByRole('button', { name: /গ্যালারি থেকে বাছুন/ })
  await expect(camera).toBeVisible()
  await expect(gallery).toBeVisible()
  for (const b of [camera, gallery]) {
    const lines = await b.evaluate((el) => { const s = el.querySelector('.label') as HTMLElement; return Math.round(s.getBoundingClientRect().height / parseFloat(getComputedStyle(s).lineHeight)) })
    expect(lines, 'button label wraps').toBe(1)
  }
  await expect(page.locator('input[type=file][capture="environment"]')).toHaveCount(2)   // prescription camera + strip
  await expect(page.locator('input[type=file][multiple]')).toHaveCount(1)                // gallery
  await noSideScroll(page)
})

// Several photos are read at the same time, and more can be taken while they are read (onsite request). The server
// is faked here with a slow reply, so the test measures how many photos are in flight together.
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAEklEQVR4nGP4z8CAFWEXHbQSACj/P8Fu7N9hAAAAAElFTkSuQmCC', 'base64')
test('several photos are read at once, and the camera stays usable meanwhile', async ({ page }) => {
  let inFlight = 0, maxInFlight = 0, n = 0
  await page.route('**/images', async (route) => {
    inFlight++; maxInFlight = Math.max(maxInFlight, inFlight)
    const k = ++n
    await new Promise((r) => setTimeout(r, 2500))
    inFlight--
    const item = { item_id: `p${k}`, doc_id: `d${k}`, source: 'strip', reading: `Brand${k}`, alternatives: [], handwritten: false, agree: null,
      chosen: null, confidence: 0, method: 'R2 unsure', needs_confirm: true, options: [], schedule: {}, per_day: null, has_crop: false,
      agent: null, doctor: null, taking: 'unsure' }
    await route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ doc_id: `d${k}`, duplicate_of: null, kind: 'strip', items: [item], request_id: 'x', latency_ms: 1 }) })
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'ওষুধের ব্যাগ পরীক্ষা করুন' }).click()
  await page.getByRole('button', { name: /প্রেসক্রিপশন/ }).click()
  await page.locator('input[type=file][multiple]').setInputFiles(
    [1, 2, 3].map((i) => ({ name: `strip${i}.png`, mimeType: 'image/png', buffer: PNG })))
  await expect(page.getByText(/ছবি ৩: পড়া হচ্ছে/)).toBeVisible()
  await expect(page.getByRole('button', { name: /স্ট্রিপ বা বাক্স/ })).toBeEnabled()          // can take another photo now
  await expect(page.getByRole('button', { name: /মিলিয়ে দেখুন/ })).toBeDisabled()            // but not check yet
  await expect(page.getByText(/৩টি ছবি পড়া শেষ/)).toBeVisible({ timeout: 10000 })
  expect(maxInFlight, 'photos read one after another').toBeGreaterThanOrEqual(3)
  await expect(page.getByRole('article')).toHaveCount(3)
  await noSideScroll(page)
})

// Camera: one photo per opening (a phone limit), so after each photo one tap opens the camera again; earlier photos
// keep being read meanwhile.
test('camera: take photo after photo without waiting', async ({ page }) => {
  await page.route('**/images', async (route) => {
    await new Promise((r) => setTimeout(r, 3000))
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ doc_id: 'd', duplicate_of: null, kind: 'strip', items: [], request_id: 'x', latency_ms: 1 }) })
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'ওষুধের ব্যাগ পরীক্ষা করুন' }).click()
  await page.getByRole('button', { name: /প্রেসক্রিপশন/ }).click()
  let chooser = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: /ক্যামেরায় তুলুন/ }).click()
  await (await chooser).setFiles({ name: 'a.png', mimeType: 'image/png', buffer: PNG })
  const again = page.getByRole('button', { name: /আরেকটা ছবি তুলুন/ })
  await expect(again).toBeVisible()
  chooser = page.waitForEvent('filechooser')
  await again.click()
  const fc = await chooser
  expect(await fc.element().getAttribute('capture')).toBe('environment')
  await fc.setFiles({ name: 'b.png', mimeType: 'image/png', buffer: PNG })
  await expect(page.getByText(/ছবি ২: পড়া হচ্ছে/)).toBeVisible()
  await noSideScroll(page)
})

test('the result is one verdict for the whole bag', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'নমুনা দেখুন' }).click()
  await page.getByRole('button', { name: /মিলিয়ে দেখুন/ }).click()
  await expect(page.getByText('পুরো ব্যাগের ফল', { exact: true })).toBeVisible()
})

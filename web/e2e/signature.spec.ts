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

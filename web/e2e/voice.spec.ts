import { expect, test } from '@playwright/test'

// A fake microphone (Chrome's test device): the recorder runs for real, the server's answer is mocked.
test.use({ permissions: ['microphone'], launchOptions: { args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] } })

const fakeCard = (id: string, brand: string, source = 'rx', needs = false) => ({ item_id: id, doc_id: source === 'voice' ? null : id, source,
  reading: brand, alternatives: [], handwritten: source === 'rx', agree: null,
  chosen: { product_id: 1, brand, strength: '10 mg', form: 'Tablet', maker: 'X', applied: false, web: null }, confidence: 0.99, method: 'R2',
  needs_confirm: needs, options: needs ? [{ product_id: 1, brand, strength: '10 mg', form: 'Tablet', maker: 'X' }] : [], schedule: {}, per_day: null,
  has_crop: false, agent: null, doctor: 'Dr', taking: 'unsure' })

// 24 Nov: after speaking, the cards were added at the bottom of a long list; it looked as if they were simply accepted.
test('spoken medicines appear right under what was heard, asking to be confirmed', async ({ page }) => {
  await page.route('**/voice', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
    transcript: 'আমি এক্সিয়াম খাই', items: [fakeCard('V9', 'Exium', 'voice', true)], request_id: 'x', latency_ms: 1 }) }))
  await page.goto('/')
  await page.getByRole('button', { name: 'ওষুধের ব্যাগ পরীক্ষা করুন' }).click()
  await page.getByRole('button', { name: /লিখে দিন/ }).first().click()
  await page.locator('#typed').fill('Napa 500\nAce 500\nSeclo 20\nMaxpro 20\nAlatrol 10')
  await page.getByRole('button', { name: /যোগ করুন/ }).click()
  await expect(page.getByRole('article')).toHaveCount(5, { timeout: 15000 })
  await page.getByRole('button', { name: /বলুন/ }).first().click()
  await page.waitForTimeout(1200)
  await page.getByRole('button', { name: /থামান ও পাঠান/ }).click()
  const voiceCard = page.getByRole('article').filter({ hasText: 'Exium' })
  await expect(voiceCard).toHaveCount(1)
  await expect(page.getByRole('article').first()).toContainText('Exium')            // first, right under "শুনেছি"
  await expect(voiceCard).toContainText('নিশ্চিত করুন')
  await expect(voiceCard).toBeInViewport()
})

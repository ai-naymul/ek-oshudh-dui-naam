import { defineConfig } from '@playwright/test'

// End-to-end check of the signature flow against the real local server (backend serving the built app).
// Uses the installed Google Chrome, so no browser download is needed. Run: npm run build && npx playwright test
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  fullyParallel: false,
  reporter: [['list']],
  use: { baseURL: 'http://localhost:8000', channel: 'chrome', screenshot: 'only-on-failure' },
  projects: [
    { name: 'laptop', use: { viewport: { width: 1440, height: 900 } } },
    { name: 'phone', use: { viewport: { width: 390, height: 844 }, hasTouch: true } },
  ],
  webServer: {
    command: 'cd ../backend && uv run uvicorn app.main:app --port 8000',
    url: 'http://localhost:8000/health',
    reuseExistingServer: true,
    timeout: 60_000,
  },
})

import { defineConfig, devices } from '@playwright/test';
import { defineBddConfig } from 'playwright-bdd';

const isCI = !!process.env.CI;

const testDir = defineBddConfig({
  features: 'tests/UI_Test/feature/***.feature',
  steps: 'tests/UI_Test/steps/***.steps.ts',
});

/**
 * Read environment variables from file.
 * https://github.com/motdotla/dotenv
 */
// import dotenv from 'dotenv';
// import path from 'path';
// dotenv.config({ path: path.resolve(__dirname, '.env') });

/**
 * See https://playwright.dev/docs/test-configuration.
 */
export default defineConfig({
  testDir: testDir,
  timeout: 1000 * 60 * 2, // 2 min per test
  globalSetup: 'tests/config/global_setup.ts',
  fullyParallel: true,
  workers: isCI ? 1 : 1,
  retries: isCI ? 1 : 0,

  use: {
    baseURL: process.env.APP_URL,
    storageState: 'user.json',
    screenshot: isCI ? 'only-on-failure' : 'off',
    video: isCI ? 'retain-on-failure' : 'off',
    trace: isCI ? 'on-first-retry' : 'off',
  },

  projects: [
    {
      name: 'chromium',
      use: isCI
        ? {
          ...devices['Desktop Chrome'],
          headless: true,
          viewport: { width: 1920, height: 1080 },
        }
        : {
          headless: false,
          viewport: null,
          launchOptions: {
            args: ['--start-maximized']
          }
        },
    }
  ],

  reporter: isCI
    ? [['html'], ['list']]   // CI: keep reports
    : [['list']],            // Local: no report generated
});

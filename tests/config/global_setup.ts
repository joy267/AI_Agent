import { chromium, request } from '@playwright/test';
import type { FullConfig } from '@playwright/test';
import { expect } from '@playwright/test';
import { LoginPage } from '../UI_Test/fixture/login';
import { ENV_CONFIG } from 'env.config';
import { logger, logError } from "../utils/logger";
import promptSync from "prompt-sync";
import fs from 'fs';
import path from 'path'

const prompt = promptSync()
const isCI = process.env.CI === 'true'

const apiContext = await request.newContext()
const API_URL = process.env.API_URL;

// Storage state configuration
const STORAGE_FILE = path.resolve('user.json');
const STORAGE_EXPIRY_MS = 2 * 60 * 60 * 1000; // 2 hours

async function globalSetup(config: FullConfig) {

  // Skipping global setup if storage state file already exists
  if (fs.existsSync(STORAGE_FILE)) {
    const stats = fs.statSync(STORAGE_FILE)
    const age = Date.now() - stats.mtimeMs

    if (age < STORAGE_EXPIRY_MS) {

      logger.info("Storage state file 'user.json' already exists. Skipping global setup.");
      return;
    }
    logger.info("Storage state file 'user.json' is expired. Proceeding with global setup.");
    fs.unlinkSync(STORAGE_FILE)
  }

  const APP_URL = ENV_CONFIG.APP_URL || process.env.APP_URL;

  let Test_User: string;
  let Test_Pass: string;

  if (isCI) {  // Skip prompting for credentials in CI environment
    console.log(" CI environment detected, using default credentials from environment\n");
    Test_User = ENV_CONFIG.Test_User || process.env.Test_User!;
    Test_Pass = ENV_CONFIG.Test_Pass || process.env.Test_Pass!;
  }
  else {

    console.log(" === CREDENTIAL MODE === ");  // User can provide custom credentials for testing

    const choice = prompt("Do you want to use custom credentials for testing? (y/n): ");

    if (choice.toLowerCase() === 'y' || choice.toLowerCase() === 'yes') {
      const customUser = prompt("Enter Test_User: ");
      const customPass = prompt.hide("Enter Test_Pass: ");

      Test_User = customUser;
      Test_Pass = customPass;

      console.log("✓ Using custom credentials\n");

    } else {
      Test_User = ENV_CONFIG.Test_User || process.env.Test_User!;
      Test_Pass = ENV_CONFIG.Test_Pass || process.env.Test_Pass!;

      console.log("✓ Using default credentials from environment\n");
    }
  }

  // Validate credentials exist
  if (!APP_URL || !Test_User || !Test_Pass || !API_URL) {
    throw new Error(`
      ❌ Missing required configuration:
      APP_URL=${APP_URL ? '✓' : '✗'}
      Test_User=${Test_User ? '✓' : '✗'}
      Test_Pass=${Test_Pass ? '✓' : '✗'}
      API_URL=${API_URL ? '✓' : '✗'}
    `);
  }

  try {

    logger.info("Try to login in the application and save storage state ...");

    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    const page = await context.newPage();

    try {

      logger.info(`Navigating to URL: ${APP_URL}`);
      const login = new LoginPage(page);

      try {
        await page.goto(APP_URL!, { waitUntil: 'load', timeout: 60000 })

      } catch (err: any) {
        logError('Page not loaded within 60 seconds')
        throw err
      }

      logger.info("Entering username ...");
      await login.enter_email(Test_User!);

      logger.info("Entering password ...");
      await login.enter_password(Test_Pass!);

      logger.info("Entering username ...");
      await login.enter_email(Test_User!);

      logger.info("Entering password ...");
      await login.enter_password(Test_Pass!);

      logger.info("Clicking Login button ...");
      await login.click_Login_Button();

      logger.info("Check the Login API responce ...");
      const login_api_response = apiContext.get(`${API_URL}/aladdin_api/v1/auth/login/`);

      try {
        (await login_api_response).status() === 200;
        logger.info("Login API is reachable and returned status 200.");

      } catch (err: any) {
        logger.error(`Login API returned unexpected status: ${(await login_api_response).status()}`)
        throw new Error("Login API is not reachable or returned an error.")
      }

    } catch (err: any) {
      logError("Login failed");
      throw err;
    }

    try {
      logger.info("Login successfully to the application.");

      await page.waitForSelector('[class="textField-notification-account"]')
      const user_profile_icon = page.locator('[class="textField-notification-account"]').getByRole('button').nth(1)
      await user_profile_icon.click()
      const validate_username = page.locator('[class="account-details"]').locator('div').nth(1).locator('p').nth(1)
      logger.info("Verifying logged in user ...");
      validate_username.textContent()
      await expect(validate_username).toHaveText(Test_User!, { timeout: 60000 });

      if (isCI) {
        logger.info("Test user logged in successfully.");
      } else {
        logger.info(`${Test_User} is successfully logged in.`);
      }


    } catch (err: any) {
      logger.error("Dashboard not visible");
      throw err;
    }

    logger.info("Saving login storage state to user.json");
    await page.context().storageState({ path: 'user.json' });

    await browser.close();

  } catch (err: any) {
    logError("Error during global setup");
    throw err;
  }
}

export default globalSetup;

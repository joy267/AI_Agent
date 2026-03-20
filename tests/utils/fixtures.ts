import { test as base } from "@playwright/test";
import { setTestName, clearTestName } from "../utils/logger";

export const test = base.extend({
  page: async ({ page }, use, testInfo) => {
    // before each test → set name
    setTestName(testInfo.title);

    await use(page);

    // after each test → clear name
    clearTestName();
  }
});

export const expect = test.expect;

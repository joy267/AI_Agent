import { createBdd } from 'playwright-bdd';
import { test } from 'playwright-bdd'
import { expect, request } from '@playwright/test';
import { logger, logError } from '../fixture/logger'
import { LoginPage } from '../fixture/login';


const { Given, When, Then } = createBdd(test);

// ─────────────────────────────────────────────
// Environment
// ─────────────────────────────────────────────

const APP_URL = process.env.APP_URL ?? 'https://aladdin-ui-stage.etloptival.com';
const API_URL = process.env.API_URL ?? '';
const Test_User = process.env.TEST_USER;
const Test_Pass = process.env.TEST_PASS;
const isCI = Boolean(process.env.CI);

// ─────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────

const getFilterContainer = (page: any) =>
  page.locator('[data-tracker="39"]').filter({ hasText: 'type' });

const getTableRows = (page: any) =>
  page
    .locator('table tbody tr')
    .filter({ has: page.locator('td:not([colspan])') });

// Helper: Normalize URLs for comparison (used by TC_WA_06)
const normalizeUrl = (url: string): string => {
  try {
    const urlObj = new URL(url)
    return urlObj.href.replace(/\/$/, '')
  } catch {
    return url.replace(/\/$/, '')
  }
}

// ─────────────────────────────────────────────
// Shared State
// ─────────────────────────────────────────────

let selectedSiteName = '';

// TC_WA_06 shared state
let siteNameLink: any;
let siteUrl: string | null;
let newTab: import('@playwright/test').Page | null = null;
let wa06TableRows: any;
let wa06RowCount: number;

// ─────────────────────────────────────────────
// Background
// ─────────────────────────────────────────────

Given('the user navigates to {string}', async ({ page }, path: string) => {
  await page.goto(`${path}`);
});

Then('the URL should be {string}', async ({ page }, expectedUrl: string) => {
  const currentUrl = new URL(page.url());
  expect(currentUrl.pathname).toBe(expectedUrl);
});

// ─────────────────────────────────────────────
// TC_WA_01 – Breadcrumb Navigation
// ─────────────────────────────────────────────

Given('the breadcrumbs section is visible', async ({ page }) => {
  await page.waitForSelector("[class='bread-crumbs']", { state: 'attached', timeout: 10000 })
  await page.getByRole('heading', { name: 'Websites' }).waitFor({ state: 'visible' })
  const breadcrumbsContainer = page.locator("[class='bread-crumbs']");
  await breadcrumbsContainer.waitFor({ state: 'visible', timeout: 15000 })
  logger.info('Breadcrumbs container found')
});

Given('the {string} breadcrumb link is visible and enabled', async ({ page }, linkText: string) => {
  const homeLink = page.locator('[data-tracker="2"]')
  await expect(homeLink).toBeVisible()
  await expect(homeLink).toBeEnabled()
});

When('the user clicks on the {string} breadcrumb link', async ({ page }, linkText: string) => {
  const breadcrumbLink = page.locator('[data-tracker="2"]');
  const text = await breadcrumbLink.textContent();
  expect(text?.trim()).toBe(linkText);
  logger.info(`Found breadcrumb link with text: "${text?.trim()}"`);
  logger.info(`Clicking breadcrumb link: "${linkText}"`);
  await breadcrumbLink.click();
});

Then('the user should be redirected to {string}', async ({ page }, expectedPath: string) => {
  await page.waitForURL(`**${expectedPath}`);
  const currentUrl = new URL(page.url());
  expect(currentUrl.pathname).toBe(expectedPath);
  logger.info(`User redirected to Home page (${expectedPath})`)
});

// ─────────────────────────────────────────────
// TC_WA_02 – Site Name Search
// ─────────────────────────────────────────────

Given('the {string} search field is visible', async ({ page }, fieldName: string) => {
  const siteNameInput = page.getByRole('combobox').first();
  await expect(siteNameInput).toBeVisible({ timeout: 20000 });
});

When('the user selects a valid site name from the dropdown', async ({ page }) => {
  const siteNameInput = page.getByRole('combobox').first();
  await siteNameInput.click();

  const listbox = page.getByRole('listbox', { name: 'Site Name' });
  await expect(listbox).toBeVisible({ timeout: 5000 });

  const options = listbox.locator('li[role="option"]', { hasText: 'njgambling' });
  const optionCount = await options.count();
  expect(optionCount).toBeGreaterThan(0);

  selectedSiteName = (await options.textContent()) ?? '';
  logger.info(`Selected valid site name for search: "${selectedSiteName}"`);

  await siteNameInput.clear();
  await siteNameInput.fill(selectedSiteName);
  await page.waitForTimeout(500);
  await options.first().click();
});

Then('the selected site name should be displayed in the input field', async ({ page }) => {
  const siteNameInput = page.getByRole('combobox').first();
  await expect(siteNameInput).toHaveValue(selectedSiteName);
});

Then('the table should display relevant search results', async ({ page }) => {
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);

  const tableRows = page
    .locator('table tbody tr')
    .filter({ hasNotText: /^$/ });

  await expect(tableRows.first()).toBeVisible({ timeout: 10000 });
  const resultCount = await tableRows.count();
  logger.info(`Number of results displayed: ${resultCount}`);
  expect(resultCount).toBeGreaterThan(0);
});

Then('at least one result should match the selected site name', async ({ page }) => {
  const tableRows = page
    .locator('table tbody tr')
    .filter({ hasNotText: /^$/ });
  const resultCount = await tableRows.count();

  let matchedRows = 0;
  for (let i = 0; i < Math.min(resultCount, 10); i++) {
    const row = tableRows.nth(i);
    const rowText = await row.textContent();
    if (!rowText || rowText.trim() === '') continue;
    if (rowText.includes(selectedSiteName)) {
      matchedRows++;
      logger.info(`Row ${i + 1} matches search criteria`);
    }
  }

  expect(matchedRows).toBeGreaterThan(0);
  logger.info(
    `Search completed successfully. ${matchedRows} out of ${Math.min(resultCount, 10)} checked results contain "${selectedSiteName}"`,
  );
});

// ─────────────────────────────────────────────
// TC_WA_03 – Pagination
// ─────────────────────────────────────────────

// NOTE: 'the website actions table is visible' is defined once below under TC_WA_04
// and is shared across TC_WA_03 and TC_WA_04 scenarios.

Then(
  'the table should display up to {int} rows on the first page',
  async ({ page }, maxRows: number) => {
    try {
      const rows = page.locator('table tbody tr').filter({
        has: page.locator('td:not([colspan])'),
      })
      await page.waitForTimeout(2000)
      const count = await rows.count()
      logger.info(`Number of data rows displayed on page 1: ${count}`)
      expect(count).toBeLessThanOrEqual(maxRows)
      expect(count).toBeGreaterThan(0)
    } catch (err: any) {
      logError('Error verifying row count on first page', err)
      throw err
    }
  },
)

Then('pagination controls should be visible', async ({ page }) => {
  try {
    const pagination = page.locator('.MuiPagination-root')
    await expect(pagination).toBeVisible()
    logger.info('Pagination controls are visible')

    const paginationInfo = page.locator('.MuiTablePagination-displayedRows').first()
    if (await paginationInfo.isVisible()) {
      const displayText = await paginationInfo.textContent()
      logger.info(`Pagination display text: ${displayText}`)
    }
  } catch (err: any) {
    logError('Error verifying pagination controls visibility', err)
    throw err
  }
})

When('the user navigates to page 2', async ({ page }) => {
  try {
    const page2Button = page
      .locator('.MuiPagination-ul li button')
      .filter({ hasText: '2' })

    if (await page2Button.isVisible()) {
      await page2Button.click()
      logger.info('Clicked on page 2')
      await page.waitForTimeout(1500)
      await page.waitForLoadState('networkidle')
    } else {
      logger.info('Page 2 button is not visible — only one page of data available')
    }
  } catch (err: any) {
    logError('Error navigating to page 2', err)
    throw err
  }
})

Then('page 2 should become active', async ({ page }) => {
  try {
    const activePage = page.locator('.MuiPagination-ul li .Mui-selected')
    await expect(activePage).toHaveText('2')
    logger.info('Page 2 is now active')
  } catch (err: any) {
    logError('Error verifying page 2 is active', err)
    throw err
  }
})

Then('the table should display up to {int} rows', async ({ page }, maxRows: number) => {
  try {
    const rows = page.locator('table tbody tr').filter({
      has: page.locator('td:not([colspan])'),
    })
    const count = await rows.count()
    logger.info(`Number of data rows displayed: ${count}`)
    expect(count).toBeLessThanOrEqual(maxRows)
    expect(count).toBeGreaterThan(0)
  } catch (err: any) {
    logError('Error verifying row count', err)
    throw err
  }
})

When('the user navigates using First, Next, Previous, and Last buttons', async ({ page }) => {
  try {
    const firstPageButton = page.locator('.MuiPagination-ul').getByLabel('Go to first page')
    if (await firstPageButton.isVisible()) {
      await firstPageButton.click()
      logger.info('Clicked on "First Page" button')
      await page.waitForTimeout(1000)
      await page.waitForLoadState('networkidle')
      const activePageAfterFirst = page.locator('.MuiPagination-ul li .Mui-selected')
      await expect(activePageAfterFirst).toHaveText('1')
      logger.info('Successfully navigated back to page 1')
    }

    const nextButton = page.locator('.MuiPagination-ul').getByLabel('Go to next page')
    if ((await nextButton.isVisible()) && (await nextButton.isEnabled())) {
      await nextButton.click()
      logger.info('Clicked on "Next" button')
      await page.waitForTimeout(1000)
      await page.waitForLoadState('networkidle')
      const activePageAfterNext = page.locator('.MuiPagination-ul li .Mui-selected')
      await expect(activePageAfterNext).toHaveText('2')
      logger.info('Successfully navigated to page 2 using Next button')
    }

    const lastPageButton = page.locator('.MuiPagination-ul').getByLabel('Go to last page')
    if ((await lastPageButton.isVisible()) && (await lastPageButton.isEnabled())) {
      await lastPageButton.click()
      logger.info('Clicked on "Last Page" button')
      await page.waitForTimeout(1000)
      await page.waitForLoadState('networkidle')
      const lastPageRows = await page.locator('table tbody tr').filter({
        has: page.locator('td:not([colspan])'),
      }).count()
      logger.info(`Number of rows on last page: ${lastPageRows}`)
      expect(lastPageRows).toBeGreaterThan(0)
      expect(lastPageRows).toBeLessThanOrEqual(10)
    } else {
      logger.info('Last page button is disabled — already on last page')
    }

    const previousButton = page.locator('.MuiPagination-ul').getByLabel('Go to previous page')
    if ((await previousButton.isVisible()) && (await previousButton.isEnabled())) {
      await previousButton.click()
      logger.info('Clicked on "Previous" button')
      await page.waitForTimeout(1000)
      await page.waitForLoadState('networkidle')
      logger.info('Successfully navigated using Previous button')
    }

    const page1Button = page.locator('.MuiPagination-ul li button').filter({ hasText: '1' })
    if (await page1Button.isVisible()) {
      await page1Button.click()
      await page.waitForTimeout(1000)
      logger.info('Navigated back to page 1')
    }
  } catch (err: any) {
    logError('Error navigating using First, Next, Previous, and Last buttons', err)
    throw err
  }
})

Then('the corresponding page should become active', async ({ page }) => {
  try {
    const activePage = page.locator('.MuiPagination-ul li .Mui-selected')
    await expect(activePage).toBeVisible()
    logger.info('Active page indicator is visible')
  } catch (err: any) {
    logError('Error verifying active page', err)
    throw err
  }
})

When('the user changes rows per page to {int}', async ({ page }, rows: number) => {
  try {
    const rowsPerPageSelect = page.locator('.MuiTablePagination-select').first()

    if (await rowsPerPageSelect.isVisible()) {
      const currentValue = await rowsPerPageSelect.textContent()
      logger.info(`Current rows per page: ${currentValue}`)

      await rowsPerPageSelect.click()
      await page.waitForTimeout(500)

      const option = page.getByRole('option', { name: String(rows), exact: true })
      if (await option.isVisible()) {
        await option.click()
        logger.info(`Changed rows per page to ${rows}`)
        await page.waitForTimeout(1500)
        await page.waitForLoadState('networkidle')

        const newRowCount = await page.locator('table tbody tr').filter({
          has: page.locator('td:not([colspan])'),
        }).count()
        logger.info(`Number of rows after changing to ${rows} per page: ${newRowCount}`)
        expect(newRowCount).toBeLessThanOrEqual(rows)
      }
    }
  } catch (err: any) {
    logError(`Error changing rows per page to ${rows}`, err)
    throw err
  }
})

When('the user changes rows per page back to {int}', async ({ page }, rows: number) => {
  try {
    const rowsPerPageSelect = page.locator('.MuiTablePagination-select').first()

    if (await rowsPerPageSelect.isVisible()) {
      await rowsPerPageSelect.click()
      await page.waitForTimeout(500)

      const option = page.getByRole('option', { name: String(rows), exact: true })
      if (await option.isVisible()) {
        await option.click()
        logger.info(`Changed rows per page back to ${rows}`)
        await page.waitForTimeout(1500)
        await page.waitForLoadState('networkidle')

        const finalRowCount = await page.locator('table tbody tr').filter({
          has: page.locator('td:not([colspan])'),
        }).count()
        logger.info(`Final row count after changing back to ${rows}: ${finalRowCount}`)
        expect(finalRowCount).toBeLessThanOrEqual(rows)
      }
    }
  } catch (err: any) {
    logError(`Error changing rows per page back to ${rows}`, err)
    throw err
  }
})

// ─────────────────────────────────────────────
// TC_WA_04 – Filters
// ─────────────────────────────────────────────

// SINGLE definition of 'the website actions table is visible'
// shared by TC_WA_03 (Pagination), TC_WA_04 (Filters), TC_WA_05 (More Info), and TC_WA_06 (Site Name Link)
Given('the website actions table is visible', async ({ page }) => {
  try {
    logger.info('Verifying website actions table is visible');

    const table = page.locator('table')
    await expect(table).toBeVisible({ timeout: 20000 })

    const tableBody = page.locator('table tbody')
    await expect(tableBody).toBeVisible()

    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000)

    const tableRows = getTableRows(page);
    const initialRowCount = await tableRows.count();
    logger.info(`Initial row count: ${initialRowCount}`);
    expect(initialRowCount).toBeGreaterThan(0);

  } catch (err: any) {
    logError('Error verifying table visibility', err)
    throw err
  }
});

Given('filter options are available', async ({ page }) => {
  logger.info('Verifying filter options are available');

  const filterContainer = getFilterContainer(page);
  await expect(filterContainer).toBeVisible();

  logger.info('Filter container is visible');
});

When('the user applies the {string} filter', async ({ page }, filterName: string) => {
  logger.info(`Applying filter: ${filterName}`);

  const filterContainer = getFilterContainer(page);
  const filterButton = filterContainer.getByRole('button', { name: filterName });
  await expect(filterButton).toBeVisible({ timeout: 5000 });

  await filterButton.click();

  const filterMenu = page.locator('[role="tooltip"]').first();
  await expect(filterMenu).toBeVisible();

  // Handle checkbox filters: Type, Territory, Industry
  const checkboxOptions = filterMenu.locator('input[type="checkbox"]');
  const checkboxCount = await checkboxOptions.count();

  if (checkboxCount > 0) {
    const checkboxMap: Record<string, string> = {
      Type: 'PPC',
      Territory: 'UK',
      Industry: 'Casino',
    };

    const optionName = checkboxMap[filterName];
    if (optionName) {
      const checkbox = page.getByRole('checkbox', { name: optionName });
      await expect(checkbox).toBeVisible();
      await checkbox.check();
      logger.info(`Selected checkbox option "${optionName}" for ${filterName} filter`);
    }
  }

  // Handle radio filters: Status, Sync
  const radioOptions = filterMenu.locator('input[type="radio"]');
  const radioCount = await radioOptions.count();

  if (radioCount > 0) {
    const firstRadio = page.locator('input[type="radio"]').first();
    await expect(firstRadio).toBeVisible();
    await firstRadio.check();
    logger.info(`Selected first radio option for ${filterName} filter`);
  }

  await filterButton.click();
  await page.waitForTimeout(300);

  const filterMenu2 = page.locator('[role="tooltip"]').first();
  await expect(filterMenu2).toBeHidden({ timeout: 3000 });

  await page.waitForTimeout(500);
  await page.waitForLoadState('networkidle');

  logger.info(`Filter "${filterName}" applied and menu closed`);
});

When('the user clicks on {string}', async ({ page }, buttonText: string) => {
  logger.info(`Clicking button: ${buttonText}`);

  const filterContainer = getFilterContainer(page);
  const button = filterContainer.getByRole('button', {
    name: buttonText,
    exact: true,
  });

  await expect(button).toBeVisible();
  await button.click();

  logger.info(`Clicked on: ${buttonText}`);
  await page.waitForTimeout(1500);
  await page.waitForLoadState('networkidle');
});

Then(
  'the table should display filtered results based on {word}',
  async ({ page }, filterType: string) => {
    logger.info(`Verifying table results filtered by: ${filterType}`);

    await page.waitForLoadState('networkidle');

    const columnIndexMap: Record<string, number> = {
      Type: 1,
      Territory: 2,
      Industry: 3,
      Status: 4,
      Sync: 5,
    };

    const rows = getTableRows(page);
    const rowCount = await rows.count();
    logger.info(`Row count after applying ${filterType} filter: ${rowCount}`);
    expect(rowCount).toBeGreaterThan(0);

    const columnIndex = columnIndexMap[filterType];
    if (columnIndex !== undefined) {
      const cellText = await rows.first().locator('td').nth(columnIndex).textContent();
      logger.info(`${filterType} column value in first row: ${cellText}`);
      expect(cellText).toBeTruthy();
    }
  }
);

Then('all filters should be cleared', async ({ page }) => {
  logger.info('Verifying all filters are cleared');

  await page.waitForLoadState('networkidle');

  const filterSelects = page.locator(
    'select[aria-label*="filter" i], [class*="filter"] select'
  );
  const count = await filterSelects.count();
  logger.info(`Found ${count} filter select elements to verify`);

  for (let i = 0; i < count; i++) {
    const value = await filterSelects.nth(i).inputValue();
    expect(value).toBeFalsy();
  }

  logger.info('All filters are cleared successfully');
});

Then('the table should display all available records', async ({ page }) => {
  logger.info('Verifying table displays all available records');

  await page.waitForLoadState('networkidle');

  const rows = getTableRows(page);
  const rowCount = await rows.count();
  logger.info(`Total row count after clearing filters: ${rowCount}`);
  expect(rowCount).toBeGreaterThan(0);

  logger.info('Table is displaying all available records');
});

// ─────────────────────────────────────────────
// TC_WA_05 – More Info
// ─────────────────────────────────────────────

// Helper: locate More Info button within a given row
const getMoreInfoButton = (row: any, page: any) =>
  row
    .locator('button[aria-label="expand row"]')
    .or(
      row
        .locator('button')
        .filter({ has: page.locator('svg') })
        .last()
    );

// Helper: locate expanded content row (row with colspan td)
const getExpandedContent = (page: any) =>
  page
    .locator('table tbody tr')
    .filter({ has: page.locator('td[colspan]') })
    .first();

// NOTE: 'the website actions table is visible' is already defined in TC_WA_04 above.
// Do not redefine it here — it is shared across TC_WA_03, TC_WA_04, TC_WA_05, and TC_WA_06.

Given('at least one data row is present', async ({ page }) => {
  try {
    logger.info('Verifying at least one data row is present in the table');

    await page.waitForTimeout(2000);

    const tableRows = page
      .locator('table tbody tr')
      .filter({ has: page.locator('td:not([colspan])') });

    const rowCount = await tableRows.count();
    logger.info(`Found ${rowCount} data rows in the table`);
    expect(rowCount).toBeGreaterThan(0);

  } catch (err: any) {
    logError('Error verifying data rows presence', err);
    throw err;
  }
});

When('the user clicks on the "More Info" button of a row', async ({ page }) => {
  try {
    logger.info('Clicking More Info button on the first row');

    const tableRows = page
      .locator('table tbody tr')
      .filter({ has: page.locator('td:not([colspan])') });

    const firstRow = tableRows.first();
    await expect(firstRow).toBeVisible();

    const moreInfoButton = getMoreInfoButton(firstRow, page);
    await expect(moreInfoButton).toBeVisible({ timeout: 5000 });
    logger.info('More Info button found in first row');

    const downArrow = moreInfoButton.locator('svg[data-testid="KeyboardArrowDownIcon"]');
    const hasDownArrow = await downArrow.isVisible().catch(() => false);
    if (hasDownArrow) {
      logger.info('Down arrow icon visible - row is in collapsed state');
    }

    await moreInfoButton.click();
    await page.waitForTimeout(1000);
    logger.info('Clicked More Info button to expand row');

  } catch (err: any) {
    logError('Error clicking More Info button', err);
    throw err;
  }
});

When('the user clicks on the "More Info" button again', async ({ page }) => {
  try {
    logger.info('Clicking More Info button again to collapse row');

    const tableRows = page
      .locator('table tbody tr')
      .filter({ has: page.locator('td:not([colspan])') });

    const firstRow = tableRows.first();
    const moreInfoButton = getMoreInfoButton(firstRow, page);

    await moreInfoButton.click();
    await page.waitForTimeout(1000);
    logger.info('Clicked More Info button to collapse row');

  } catch (err: any) {
    logError('Error clicking More Info button to collapse', err);
    throw err;
  }
});

Then('the row should expand', async ({ page }) => {
  try {
    logger.info('Verifying row is expanded');

    const tableRows = page
      .locator('table tbody tr')
      .filter({ has: page.locator('td:not([colspan])') });

    const firstRow = tableRows.first();
    const moreInfoButton = getMoreInfoButton(firstRow, page);

    const upArrow = moreInfoButton.locator('svg[data-testid="KeyboardArrowUpIcon"]');
    await expect(upArrow).toBeVisible({ timeout: 5000 });
    logger.info('Up arrow icon visible - row is expanded');

  } catch (err: any) {
    logError('Error verifying row expanded state', err);
    throw err;
  }
});

Then('additional site information should be displayed', async ({ page }) => {
  try {
    logger.info('Verifying additional site information is displayed');

    const expandedContent = getExpandedContent(page);
    await expect(expandedContent).toBeVisible({ timeout: 5000 });
    logger.info('Expanded content section is visible');

    const expandedText = await expandedContent.textContent();
    expect(expandedText).toBeTruthy();
    expect(expandedText!.length).toBeGreaterThan(0);

    const hasAdditionalInfo = expandedText!.length > 50;
    expect(hasAdditionalInfo).toBe(true);
    logger.info('Expanded section contains additional site information');

  } catch (err: any) {
    logError('Error verifying additional site information', err);
    throw err;
  }
});

Then('the row should collapse', async ({ page }) => {
  try {
    logger.info('Verifying row is collapsed');

    const tableRows = page
      .locator('table tbody tr')
      .filter({ has: page.locator('td:not([colspan])') });

    const firstRow = tableRows.first();
    const moreInfoButton = getMoreInfoButton(firstRow, page);

    const downArrow = moreInfoButton.locator('svg[data-testid="KeyboardArrowDownIcon"]');
    await expect(downArrow).toBeVisible({ timeout: 5000 });
    logger.info('Down arrow icon visible - row is collapsed');

  } catch (err: any) {
    logError('Error verifying row collapsed state', err);
    throw err;
  }
});

Then('the additional information should be hidden', async ({ page }) => {
  try {
    logger.info('Verifying additional information is hidden after collapse');

    const expandedContent = getExpandedContent(page);
    const isHidden = await expandedContent.isHidden().catch(() => true);
    expect(isHidden).toBe(true);
    logger.info('Expanded content is hidden after collapsing');

  } catch (err: any) {
    logError('Error verifying additional information is hidden', err);
    throw err;
  }
});

// ─────────────────────────────────────────────
// TC_WA_06 – Site Name Link Opens New Tab
// ─────────────────────────────────────────────

// NOTE: 'the website actions table is visible' is shared — already defined under TC_WA_04.
// The shared definition now also covers the waitForTimeout(2000) needed by TC_WA_06.

Given('at least one site name link is available', async ({ page }) => {
  try {
    logger.info('Verifying at least one site name link is available')

    wa06TableRows = page
      .locator('table tbody tr')
      .filter({ has: page.locator('td:not([colspan])') })

    wa06RowCount = await wa06TableRows.count()
    logger.info(`Found ${wa06RowCount} data rows in the table`)
    expect(wa06RowCount).toBeGreaterThan(0)

    const firstRow = wa06TableRows.first()
    await expect(firstRow).toBeVisible()

    siteNameLink = firstRow
      .locator('a[data-tracker="40"]')
      .or(firstRow.locator('a[target="_blank"]').first())

    await expect(siteNameLink).toBeVisible({ timeout: 5000 })

    const siteName = await siteNameLink.textContent()
    siteUrl = await siteNameLink.getAttribute('href')
    logger.info(`Found site name link: "${siteName}" with URL: "${siteUrl}"`)

    expect(siteUrl).toBeTruthy()
    expect(siteUrl).not.toBe('')

    const targetAttr = await siteNameLink.getAttribute('target')
    expect(targetAttr).toBe('_blank')
    logger.info('Link has target="_blank" attribute')

  } catch (err: any) {
    logError('Error verifying site name link availability', err)
    throw err
  }
})

When('the user clicks on a site name link', async ({ page }) => {
  try {
    logger.info('Clicking on the site name link')

    const [openedPage] = await Promise.all([
      page.context().waitForEvent('page'),
      siteNameLink.click(),
    ])

    newTab = openedPage
    logger.info('Clicked on the site name link')

  } catch (err: any) {
    logError('Error clicking on site name link', err)
    throw err
  }
})

Then('a new tab should open', async () => {
  try {
    logger.info('Verifying a new tab was opened')

    expect(newTab).toBeTruthy()
    logger.info('New tab was opened successfully')

    await newTab!.waitForLoadState('domcontentloaded', { timeout: 15000 })

  } catch (err: any) {
    logError('Error verifying new tab opened', err)
    throw err
  }
})

Then('the new tab URL should match the site link URL', async ({ page }) => {
  try {
    logger.info('Verifying new tab URL matches the expected site URL')

    const newPageUrl = newTab!.url()
    logger.info(`New page URL: ${newPageUrl}`)

    expect(normalizeUrl(newPageUrl)).toContain(normalizeUrl(siteUrl || ''))
    logger.info('New page URL matches the expected site URL')

    await newTab!.close()
    logger.info('Closed the new tab')

    // Test second site name link if available
    if (wa06RowCount > 1) {
      logger.info('Testing second site name link...')

      const secondRow = wa06TableRows.nth(1)
      const secondSiteNameLink = secondRow
        .locator('a[data-tracker="40"]')
        .or(secondRow.locator('a[target="_blank"]').first())

      if (await secondSiteNameLink.isVisible()) {
        const secondSiteName = await secondSiteNameLink.textContent()
        const secondSiteUrl = await secondSiteNameLink.getAttribute('href')
        logger.info(`Testing second site: "${secondSiteName}" with URL: "${secondSiteUrl}"`)

        const [secondNewPage] = await Promise.all([
          page.context().waitForEvent('page'),
          secondSiteNameLink.click(),
        ])

        expect(secondNewPage).toBeTruthy()
        await secondNewPage.waitForLoadState('domcontentloaded', { timeout: 15000 })

        const secondNewPageUrl = secondNewPage.url()
        expect(normalizeUrl(secondNewPageUrl)).toContain(normalizeUrl(secondSiteUrl || ''))
        logger.info('Second site name link also opens correct URL in new tab')

        await secondNewPage.close()
        logger.info('Closed the second new tab')
      }
    }

    logger.info('Site name links open correct URLs in new tabs successfully')

  } catch (err: any) {
    logError('Error verifying new tab URL matches site link URL', err)
    throw err
  }
})

// ─────────────────────────────────────────────
// TC_WA_07 – Site Name Search (invalid input)
// ─────────────────────────────────────────────

When('the user enters invalid characters into the search field', async ({ page }) => {
  const input = page
    .locator('input[placeholder*="Site Name"], [aria-label*="Site Name"] input')
    .first();
  await input.fill('!@#$%^&*()_+INVALIDXYZ123');
  await page.waitForTimeout(500);
});

Then('a {string} message should be displayed', async ({ page }, message: string) => {
  await expect(
    page
      .locator(`text="${message}", [class*="noOptions"], [class*="no-options"]`)
      .first(),
  ).toBeVisible();
});

// ─────────────────────────────────────────────
// TC_WA_08 – Graceful Handling of Invalid Pages
// ─────────────────────────────────────────────

Given('the website actions table and pagination are visible', async ({ page }) => {
  await expect(page.locator('table, [role="table"]')).toBeVisible();
  await expect(
    page.locator('[class*="pagination"], nav[aria-label*="pagination"]'),
  ).toBeVisible();
});

When(
  'the user navigates to a page number greater than available pages via URL',
  async ({ page }) => {
    const currentUrl = new URL(page.url());
    currentUrl.searchParams.set('page', '99999');
    await page.goto(currentUrl.toString());
    await page.waitForLoadState('networkidle');
  },
);

Then(
  'the application should handle it gracefully without crashing',
  async ({ page }) => {
    const errorPage = page.locator(
      '[class*="error-page"], [class*="errorPage"], h1:has-text("500")',
    );
    expect(await errorPage.count()).toBe(0);
  },
);

Then(
  'the table should either show no data or redirect to a valid page',
  async ({ page }) => {
    await expect(page.locator('table, [role="table"]')).toBeVisible();
  },
);

When('the user navigates to a negative page number via URL', async ({ page }) => {
  const currentUrl = new URL(page.url());
  currentUrl.searchParams.set('page', '-1');
  await page.goto(currentUrl.toString());
  await page.waitForLoadState('networkidle');
});

Then('the application should default to the first valid page', async ({ page }) => {
  const activePage = page
    .locator('[aria-current="page"], .Mui-selected, .active-page')
    .first();
  await expect(activePage).toHaveText('1');
});

Then('the table should display valid records', async ({ page }) => {
  const rows = page.locator('table tbody tr, [role="rowgroup"] [role="row"]');
  expect(await rows.count()).toBeGreaterThan(0);
})
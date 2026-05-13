import { expect, type Page, type Locator } from '@playwright/test'
import { logger } from '../fixture/logger'

// ─────────────────────────────────────────────
// WebsiteActionsPage
// Page Object Model encapsulating all locators and actions
// for the /operations/website_actions page.
// ─────────────────────────────────────────────

export class WebsiteActionsPage {
    readonly page: Page

    constructor(page: Page) {
        this.page = page
    }

    // ─────────────────────────────────────────────
    // Locators
    // ─────────────────────────────────────────────

    get table() { return this.page.locator('table') }
    get tableBody() { return this.page.locator('table tbody') }
    get tableOrRole() { return this.page.locator('table, [role="table"]') }
    get breadcrumbsContainer() { return this.page.locator("[class='bread-crumbs']") }
    get websitesHeading() { return this.page.getByRole('heading', { name: 'Websites' }) }
    get breadcrumbHomeLink() { return this.page.locator('[data-tracker="2"]') }
    get filterContainer() { return this.page.locator('[data-tracker="39"]').filter({ hasText: 'type' }) }
    get paginationRoot() { return this.page.locator('.MuiPagination-root') }
    get paginationUl() { return this.page.locator('.MuiPagination-ul') }
    get paginationDisplayRows() { return this.page.locator('.MuiTablePagination-displayedRows').first() }
    get rowsPerPageSelect() { return this.page.locator('.MuiTablePagination-select').first() }
    get activePageIndicator() { return this.page.locator('.MuiPagination-ul li .Mui-selected') }
    get filterTooltip() { return this.page.locator('[role="tooltip"]').first() }
    get siteNameCombobox() { return this.page.getByRole('combobox').first() }
    get siteNameListbox() { return this.page.getByRole('listbox', { name: 'Site Name' }) }

    // ─────────────────────────────────────────────
    // Helpers
    // ─────────────────────────────────────────────

    /**
     * Returns all data rows (excludes colspan rows like empty/expanded states)
     */
    getTableRows(): Locator {
        return this.page
            .locator('table tbody tr')
            .filter({ has: this.page.locator('td:not([colspan])') })
    }

    /**
     * Returns the expanded content row (the colspan row shown after More Info click)
     */
    getExpandedContentRow(): Locator {
        return this.page
            .locator('table tbody tr')
            .filter({ has: this.page.locator('td[colspan]') })
            .first()
    }

    /**
     * Returns the More Info toggle button within a given row
     */
    getMoreInfoButton(row: Locator): Locator {
        return row
            .locator('button[aria-label="expand row"]')
            .or(
                row
                    .locator('button')
                    .filter({ has: this.page.locator('svg') })
                    .last()
            )
    }

    /**
     * Returns the site name link within a given row
     */
    getSiteNameLink(row: Locator): Locator {
        return row
            .locator('a[data-tracker="40"]')
            .or(row.locator('a[target="_blank"]').first())
    }

    /**
     * Normalizes a URL for comparison by removing trailing slashes
     */
    normalizeUrl(url: string): string {
        try {
            const urlObj = new URL(url)
            return urlObj.href.replace(/\/$/, '')
        } catch {
            return url.replace(/\/$/, '')
        }
    }

    // ─────────────────────────────────────────────
    // Navigation
    // ─────────────────────────────────────────────

    async navigateTo(path: string): Promise<void> {
        await this.page.goto(path)
    }

    async waitForTableToLoad(): Promise<void> {
        await expect(this.table).toBeVisible({ timeout: 20000 })
        await expect(this.tableBody).toBeVisible()
        await this.page.waitForLoadState('networkidle')
        await this.page.waitForTimeout(2000)
    }

    // ─────────────────────────────────────────────
    // TC_WA_01 – Breadcrumbs
    // ─────────────────────────────────────────────

    async waitForBreadcrumbs(): Promise<void> {
        await this.page.waitForSelector("[class='bread-crumbs']", { state: 'attached', timeout: 20000 })
        await this.websitesHeading.waitFor({ state: 'visible' })
        await this.breadcrumbsContainer.waitFor({ state: 'visible', timeout: 20000 })
        logger.info('Breadcrumbs container found')
    }

    async assertBreadcrumbLinkVisible(): Promise<void> {
        await expect(this.breadcrumbHomeLink).toBeVisible()
        await expect(this.breadcrumbHomeLink).toBeEnabled()
    }

    async clickBreadcrumbLink(expectedText: string): Promise<void> {
        const text = await this.breadcrumbHomeLink.textContent()
        expect(text?.trim()).toBe(expectedText)
        logger.info(`Found breadcrumb link with text: "${text?.trim()}"`)
        await this.breadcrumbHomeLink.click()
        logger.info(`Clicked breadcrumb link: "${expectedText}"`)
    }

    async assertRedirectedTo(expectedPath: string): Promise<void> {
        await this.page.waitForURL(`**${expectedPath}`)
        const currentUrl = new URL(this.page.url())
        expect(currentUrl.pathname).toBe(expectedPath)
        logger.info(`User redirected to: ${expectedPath}`)
    }

    // ─────────────────────────────────────────────
    // TC_WA_02 – Site Name Search (valid)
    // ─────────────────────────────────────────────

    async assertSiteNameFieldVisible(): Promise<void> {
        await expect(this.siteNameCombobox).toBeVisible({ timeout: 20000 })
    }

    async selectSiteNameFromDropdown(siteName: string): Promise<string> {
        await this.siteNameCombobox.click()

        await expect(this.siteNameListbox).toBeVisible({ timeout: 5000 })

        const options = this.siteNameListbox.locator('li[role="option"]', { hasText: siteName })
        const optionCount = await options.count()
        expect(optionCount).toBeGreaterThan(0)

        const selectedName = (await options.textContent()) ?? ''
        logger.info(`Selected valid site name for search: "${selectedName}"`)

        await this.siteNameCombobox.clear()
        await this.siteNameCombobox.fill(selectedName)
        await this.page.waitForTimeout(500)
        await options.first().click()

        return selectedName
    }

    async assertSiteNameInInputField(siteName: string): Promise<void> {
        await expect(this.siteNameCombobox).toHaveValue(siteName)
    }

    async assertSearchResultsVisible(): Promise<void> {
        await this.page.waitForLoadState('networkidle')
        await this.page.waitForTimeout(1500)

        const tableRows = this.page
            .locator('table tbody tr')
            .filter({ hasNotText: /^$/ })

        await expect(tableRows.first()).toBeVisible({ timeout: 10000 })
        const resultCount = await tableRows.count()
        logger.info(`Number of results displayed: ${resultCount}`)
        expect(resultCount).toBeGreaterThan(0)
    }

    async assertResultsMatchSiteName(siteName: string): Promise<void> {
        const tableRows = this.page
            .locator('table tbody tr')
            .filter({ hasNotText: /^$/ })
        const resultCount = await tableRows.count()

        let matchedRows = 0
        for (let i = 0; i < Math.min(resultCount, 10); i++) {
            const row = tableRows.nth(i)
            const rowText = await row.textContent()
            if (!rowText || rowText.trim() === '') continue
            if (rowText.includes(siteName)) {
                matchedRows++
                logger.info(`Row ${i + 1} matches search criteria`)
            }
        }

        expect(matchedRows).toBeGreaterThan(0)
        logger.info(
            `Search completed. ${matchedRows} of ${Math.min(resultCount, 10)} rows contain "${siteName}"`,
        )
    }

    // ─────────────────────────────────────────────
    // TC_WA_03 – Pagination
    // ─────────────────────────────────────────────

    async assertRowCountOnPage(maxRows: number): Promise<void> {
        const rows = this.getTableRows()
        await this.page.waitForTimeout(2000)
        const count = await rows.count()
        logger.info(`Data rows on current page: ${count}`)
        expect(count).toBeLessThanOrEqual(maxRows)
        expect(count).toBeGreaterThan(0)
    }

    async assertPaginationVisible(): Promise<void> {
        await expect(this.paginationRoot).toBeVisible()
        logger.info('Pagination controls are visible')

        if (await this.paginationDisplayRows.isVisible()) {
            const displayText = await this.paginationDisplayRows.textContent()
            logger.info(`Pagination display text: ${displayText}`)
        }
    }

    async navigateToPage(pageNumber: number): Promise<void> {
        const pageButton = this.paginationUl
            .locator('li button')
            .filter({ hasText: String(pageNumber) })

        if (await pageButton.isVisible()) {
            await pageButton.click()
            logger.info(`Clicked on page ${pageNumber}`)
            await this.page.waitForTimeout(1500)
            await this.page.waitForLoadState('networkidle')
        } else {
            logger.info(`Page ${pageNumber} button not visible — only one page of data available`)
        }
    }

    async assertActivePageIs(pageNumber: number): Promise<void> {
        await expect(this.activePageIndicator).toHaveText(String(pageNumber))
        logger.info(`Page ${pageNumber} is now active`)
    }

    async assertActivePageIndicatorVisible(): Promise<void> {
        await expect(this.activePageIndicator).toBeVisible()
        logger.info('Active page indicator is visible')
    }

    async navigateUsingPaginationButtons(): Promise<void> {
        const firstBtn = this.paginationUl.getByLabel('Go to first page')
        if (await firstBtn.isVisible()) {
            await firstBtn.click()
            logger.info('Clicked "First Page" button')
            await this.page.waitForTimeout(1000)
            await this.page.waitForLoadState('networkidle')
            await expect(this.activePageIndicator).toHaveText('1')
            logger.info('Navigated to page 1')
        }

        const nextBtn = this.paginationUl.getByLabel('Go to next page')
        if ((await nextBtn.isVisible()) && (await nextBtn.isEnabled())) {
            await nextBtn.click()
            logger.info('Clicked "Next" button')
            await this.page.waitForTimeout(1000)
            await this.page.waitForLoadState('networkidle')
            await expect(this.activePageIndicator).toHaveText('2')
            logger.info('Navigated to page 2 via Next')
        }

        const lastBtn = this.paginationUl.getByLabel('Go to last page')
        if ((await lastBtn.isVisible()) && (await lastBtn.isEnabled())) {
            await lastBtn.click()
            logger.info('Clicked "Last Page" button')
            await this.page.waitForTimeout(1000)
            await this.page.waitForLoadState('networkidle')
            const lastPageRows = await this.getTableRows().count()
            logger.info(`Rows on last page: ${lastPageRows}`)
            expect(lastPageRows).toBeGreaterThan(0)
            expect(lastPageRows).toBeLessThanOrEqual(10)
        } else {
            logger.info('Last page button disabled — already on last page')
        }

        const prevBtn = this.paginationUl.getByLabel('Go to previous page')
        if ((await prevBtn.isVisible()) && (await prevBtn.isEnabled())) {
            await prevBtn.click()
            logger.info('Clicked "Previous" button')
            await this.page.waitForTimeout(1000)
            await this.page.waitForLoadState('networkidle')
        }

        const page1Btn = this.paginationUl.locator('li button').filter({ hasText: '1' })
        if (await page1Btn.isVisible()) {
            await page1Btn.click()
            await this.page.waitForTimeout(1000)
            logger.info('Navigated back to page 1')
        }
    }

    async changeRowsPerPage(rows: number): Promise<void> {
        if (await this.rowsPerPageSelect.isVisible()) {
            const current = await this.rowsPerPageSelect.textContent()
            logger.info(`Current rows per page: ${current}`)

            await this.rowsPerPageSelect.click()
            await this.page.waitForTimeout(500)

            const option = this.page.getByRole('option', { name: String(rows), exact: true })
            if (await option.isVisible()) {
                await option.click()
                logger.info(`Changed rows per page to ${rows}`)
                await this.page.waitForTimeout(1500)
                await this.page.waitForLoadState('networkidle')

                const newCount = await this.getTableRows().count()
                logger.info(`Row count after change: ${newCount}`)
                expect(newCount).toBeLessThanOrEqual(rows)
            }
        }
    }

    // ─────────────────────────────────────────────
    // TC_WA_04 – Filters
    // ─────────────────────────────────────────────

    async assertFilterOptionsVisible(): Promise<void> {
        await expect(this.filterContainer).toBeVisible()
        logger.info('Filter container is visible')
    }

    async applyFilter(filterName: string): Promise<void> {
        logger.info(`Applying filter: ${filterName}`)

        const filterButton = this.filterContainer.getByRole('button', { name: filterName })
        await expect(filterButton).toBeVisible({ timeout: 5000 })
        await filterButton.click()

        await expect(this.filterTooltip).toBeVisible()

        // Handle checkbox filters: Type, Territory, Industry
        const checkboxCount = await this.filterTooltip.locator('input[type="checkbox"]').count()
        if (checkboxCount > 0) {
            const checkboxMap: Record<string, string> = {
                Type: 'PPC',
                Territory: 'UK',
                Industry: 'Casino',
            }
            const optionName = checkboxMap[filterName]
            if (optionName) {
                const checkbox = this.page.getByRole('checkbox', { name: optionName })
                await expect(checkbox).toBeVisible()
                await checkbox.check()
                logger.info(`Checked "${optionName}" for ${filterName} filter`)
            }
        }

        // Handle radio filters: Status, Sync
        const radioCount = await this.filterTooltip.locator('input[type="radio"]').count()
        if (radioCount > 0) {
            const firstRadio = this.page.locator('input[type="radio"]').first()
            await expect(firstRadio).toBeVisible()
            await firstRadio.check()
            logger.info(`Selected first radio option for ${filterName} filter`)
        }

        await filterButton.click()
        await this.page.waitForTimeout(300)
        await expect(this.filterTooltip).toBeHidden({ timeout: 3000 })
        await this.page.waitForTimeout(500)
        await this.page.waitForLoadState('networkidle')

        logger.info(`Filter "${filterName}" applied and menu closed`)
    }

    async clickFilterButton(buttonText: string): Promise<void> {
        logger.info(`Clicking button: ${buttonText}`)
        const button = this.filterContainer.getByRole('button', { name: buttonText, exact: true })
        await expect(button).toBeVisible()
        await button.click()
        logger.info(`Clicked: ${buttonText}`)
        await this.page.waitForTimeout(1500)
        await this.page.waitForLoadState('networkidle')
    }

    async assertFilteredResults(filterType: string): Promise<void> {
        await this.page.waitForLoadState('networkidle')

        const columnIndexMap: Record<string, number> = {
            Type: 1, Territory: 2, Industry: 3, Status: 4, Sync: 5,
        }

        const rows = this.getTableRows()
        const rowCount = await rows.count()
        logger.info(`Row count after applying ${filterType} filter: ${rowCount}`)
        expect(rowCount).toBeGreaterThan(0)

        const columnIndex = columnIndexMap[filterType]
        if (columnIndex !== undefined) {
            const cellText = await rows.first().locator('td').nth(columnIndex).textContent()
            logger.info(`${filterType} column value in first row: ${cellText}`)
            expect(cellText).toBeTruthy()
        }
    }

    async assertFiltersCleared(): Promise<void> {
        await this.page.waitForLoadState('networkidle')

        const filterSelects = this.page.locator(
            'select[aria-label*="filter" i], [class*="filter"] select',
        )
        const count = await filterSelects.count()
        logger.info(`Filter select elements found: ${count}`)

        for (let i = 0; i < count; i++) {
            const value = await filterSelects.nth(i).inputValue()
            expect(value).toBeFalsy()
        }
        logger.info('All filters cleared')
    }

    async assertAllRecordsVisible(): Promise<void> {
        await this.page.waitForLoadState('networkidle')
        const rows = this.getTableRows()
        const rowCount = await rows.count()
        logger.info(`Total rows after clearing filters: ${rowCount}`)
        expect(rowCount).toBeGreaterThan(0)
    }

    // ─────────────────────────────────────────────
    // TC_WA_05 – More Info
    // ─────────────────────────────────────────────

    async assertAtLeastOneDataRow(): Promise<void> {
        await this.page.waitForTimeout(2000)
        const rowCount = await this.getTableRows().count()
        logger.info(`Found ${rowCount} data rows`)
        expect(rowCount).toBeGreaterThan(0)
    }

    async clickMoreInfoButton(): Promise<void> {
        const firstRow = this.getTableRows().first()
        await expect(firstRow).toBeVisible()

        const moreInfoButton = this.getMoreInfoButton(firstRow)
        await expect(moreInfoButton).toBeVisible({ timeout: 5000 })

        const hasDownArrow = await moreInfoButton
            .locator('svg[data-testid="KeyboardArrowDownIcon"]')
            .isVisible()
            .catch(() => false)

        if (hasDownArrow) logger.info('Row is in collapsed state')

        await moreInfoButton.click()
        await this.page.waitForTimeout(1000)
        logger.info('Clicked More Info button to expand row')
    }

    async clickMoreInfoButtonAgain(): Promise<void> {
        const firstRow = this.getTableRows().first()
        await this.getMoreInfoButton(firstRow).click()
        await this.page.waitForTimeout(1000)
        logger.info('Clicked More Info button to collapse row')
    }

    async assertRowExpanded(): Promise<void> {
        const firstRow = this.getTableRows().first()
        const upArrow = this.getMoreInfoButton(firstRow)
            .locator('svg[data-testid="KeyboardArrowUpIcon"]')
        await expect(upArrow).toBeVisible({ timeout: 5000 })
        logger.info('Up arrow visible — row is expanded')
    }

    async assertRowCollapsed(): Promise<void> {
        const firstRow = this.getTableRows().first()
        const downArrow = this.getMoreInfoButton(firstRow)
            .locator('svg[data-testid="KeyboardArrowDownIcon"]')
        await expect(downArrow).toBeVisible({ timeout: 5000 })
        logger.info('Down arrow visible — row is collapsed')
    }

    async assertExpandedContentVisible(): Promise<void> {
        const expandedContent = this.getExpandedContentRow()
        await expect(expandedContent).toBeVisible({ timeout: 5000 })

        const expandedText = await expandedContent.textContent()
        expect(expandedText).toBeTruthy()
        expect(expandedText!.length).toBeGreaterThan(50)
        logger.info('Expanded content is visible with additional info')
    }

    async assertExpandedContentHidden(): Promise<void> {
        const expandedContent = this.getExpandedContentRow()
        const isHidden = await expandedContent.isHidden().catch(() => true)
        expect(isHidden).toBe(true)
        logger.info('Expanded content is hidden')
    }

    // ─────────────────────────────────────────────
    // TC_WA_06 – Site Name Link
    // ─────────────────────────────────────────────

    async assertSiteNameLinkAvailable(): Promise<{ link: Locator; url: string; rowCount: number }> {
        const rows = this.getTableRows()
        const rowCount = await rows.count()
        logger.info(`Found ${rowCount} data rows`)
        expect(rowCount).toBeGreaterThan(0)

        const firstRow = rows.first()
        await expect(firstRow).toBeVisible()

        const link = this.getSiteNameLink(firstRow)
        await expect(link).toBeVisible({ timeout: 5000 })

        const siteName = await link.textContent()
        const url = await link.getAttribute('href')
        logger.info(`Found site name link: "${siteName}" with URL: "${url}"`)

        expect(url).toBeTruthy()
        expect(url).not.toBe('')

        const targetAttr = await link.getAttribute('target')
        expect(targetAttr).toBe('_blank')
        logger.info('Link has target="_blank" attribute')

        return { link, url: url!, rowCount }
    }

    async clickSiteNameLinkAndGetNewTab(link: Locator): Promise<Page> {
        const [newPage] = await Promise.all([
            this.page.context().waitForEvent('page'),
            link.click(),
        ])
        logger.info('Clicked site name link — new tab opened')
        return newPage
    }

    async assertNewTabOpened(newTab: Page): Promise<void> {
        expect(newTab).toBeTruthy()
        await newTab.waitForLoadState('domcontentloaded', { timeout: 15000 })
        logger.info('New tab opened and loaded')
    }

    async assertNewTabUrlMatches(newTab: Page, expectedUrl: string): Promise<void> {
        const newPageUrl = newTab.url()
        logger.info(`New tab URL: ${newPageUrl}`)
        expect(this.normalizeUrl(newPageUrl)).toContain(this.normalizeUrl(expectedUrl))
        logger.info('New tab URL matches expected site URL')
    }

    async testSecondSiteNameLink(rows: Locator, rowCount: number, livePage: Page): Promise<void> {
        if (rowCount <= 1) return

        logger.info('Testing second site name link...')
        const secondRow = rows.nth(1)
        const secondLink = this.getSiteNameLink(secondRow)

        if (!(await secondLink.isVisible())) return

        const secondSiteName = await secondLink.textContent()
        const secondSiteUrl = await secondLink.getAttribute('href')
        logger.info(`Testing second site: "${secondSiteName}" with URL: "${secondSiteUrl}"`)

        const [secondNewPage] = await Promise.all([
            livePage.context().waitForEvent('page'),  // ✅ uses the step's live page
            secondLink.click(),
        ])

        expect(secondNewPage).toBeTruthy()
        await secondNewPage.waitForLoadState('domcontentloaded', { timeout: 15000 })

        expect(this.normalizeUrl(secondNewPage.url())).toContain(
            this.normalizeUrl(secondSiteUrl || ''),
        )
        logger.info('Second site name link opens correct URL in new tab')

        await secondNewPage.close()
        logger.info('Closed second new tab')
    }

    // ─────────────────────────────────────────────
    // TC_WA_07 – Site Name Search (invalid input)
    // ─────────────────────────────────────────────

    async assertSearchFieldVisible(fieldName: string): Promise<void> {
        const input = this.page.getByRole('combobox', { name: 'Site Name' })
        await expect(input).toBeVisible({ timeout: 20000 })
        logger.info(`"${fieldName}" input field is visible`)
    }

    async enterInvalidInputsAndAssertNoOptions(fieldName: string): Promise<void> {
        const siteNameInput = this.page.getByRole('combobox', { name: fieldName ?? 'Site Name' })
        await expect(siteNameInput).toBeVisible({ timeout: 20000 })

        const invalidInputs: string[] = [
            '!@#$%^&*()',
            '<<<>>>',
            '////\\\\\\',
            '12345678901234567890',
            'NonExistentSite!!!',
            '特殊字符测试',
            '   ',
        ]

        const lastInput = invalidInputs[invalidInputs.length - 1]!

        for (const invalidInput of invalidInputs) {
            const isLastInput = invalidInput === lastInput
            logger.info(`Testing with invalid input: "${invalidInput}"`)

            await siteNameInput.click()
            await this.page.waitForTimeout(300)
            await siteNameInput.fill(invalidInput)
            await this.page.waitForTimeout(500)

            const noOptionsMessage = this.page.getByText('No options', { exact: false })
            await expect(noOptionsMessage).toBeVisible({ timeout: 3000 })
            logger.info(`"No options" message displayed for input: "${invalidInput}"`)

            // Keep dropdown open on last iteration for the Then step to assert
            if (!isLastInput) {
                await this.page.locator('body').click()
                await this.page.waitForTimeout(500)
            }
        }

        logger.info('All invalid inputs tested successfully')
    }

    async assertMessageVisible(message: string): Promise<void> {
        const messageLocator = this.page.getByText(message, { exact: false })
        await expect(messageLocator).toBeVisible({ timeout: 3000 })
        logger.info(`"${message}" message is visible`)

        // Close dropdown after assertion
        await this.page.locator('body').click()
        await this.page.waitForTimeout(500)
    }

    // ─────────────────────────────────────────────
    // TC_WA_08 – Invalid Page Navigation
    // ─────────────────────────────────────────────

    async assertTableAndPaginationVisible(): Promise<void> {
        await expect(this.tableOrRole).toBeVisible({ timeout: 20000 })
        logger.info('Table is visible')

        await expect(
            this.page.locator('[class*="pagination"], nav[aria-label*="pagination"]'),
        ).toBeVisible({ timeout: 10000 })
        logger.info('Pagination controls are visible')
    }

    async navigateToPageViaUrl(pageParam: string): Promise<void> {
        const currentUrl = new URL(this.page.url())
        currentUrl.searchParams.set('page', pageParam)
        logger.info(`Navigating to URL: ${currentUrl.toString()}`)
        await this.page.goto(currentUrl.toString())
        await this.page.waitForLoadState('networkidle')
        logger.info('Navigation completed')
    }

    async assertNoErrorPage(): Promise<void> {
        const errorPage = this.page.locator(
            '[class*="error-page"], [class*="errorPage"], h1:has-text("500")',
        )
        expect(await errorPage.count()).toBe(0)
        logger.info('No error page detected — application handled gracefully')
    }

    async assertTableStillVisible(): Promise<void> {
        await expect(this.tableOrRole).toBeVisible({ timeout: 10000 })
        logger.info('Table is visible after out-of-range navigation')
    }

    async assertOrCorrectToFirstPage(): Promise<void> {
        await this.page.waitForTimeout(1500)

        const activePageLocator = this.page.locator(
            '[aria-current="page"], .Mui-selected, .active-page',
        )
        const activePageCount = await activePageLocator.count()

        if (activePageCount > 0) {
            await expect(activePageLocator.first()).toHaveText('1', { timeout: 5000 })
            logger.info('Pagination indicator confirms page 1 is active')
        } else {
            const currentUrl = new URL(this.page.url())
            const pageParam = currentUrl.searchParams.get('page')
            logger.info(`Pagination indicator not found — URL page param is "${pageParam}"`)

            currentUrl.searchParams.set('page', '1')
            logger.info(`Correcting URL to page 1: ${currentUrl.toString()}`)

            await this.page.goto(currentUrl.toString())
            await this.page.waitForLoadState('networkidle')
            await this.page.waitForTimeout(1000)

            logger.info('Navigated to page 1')
        }
    }

    async assertTableHasValidRecords(): Promise<void> {
        const rows = this.page.locator('table tbody tr, [role="rowgroup"] [role="row"]')
        await expect(rows.first()).toBeVisible({ timeout: 10000 })
        const rowCount = await rows.count()
        logger.info(`Row count: ${rowCount}`)
        expect(rowCount).toBeGreaterThan(0)
        logger.info('Table is displaying valid records')
    }
}
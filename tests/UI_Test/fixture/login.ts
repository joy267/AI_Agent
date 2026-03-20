import type { Page, Locator } from '@playwright/test';

export class LoginPage {

    readonly page: Page

    readonly locator_of_username_field: Locator
    readonly locator_of_password_field: Locator
    readonly locator_of_login_button: Locator
    readonly locator_of_dashboard: Locator

    constructor(page: Page) {

        this.page = page

        this.locator_of_username_field = page.getByPlaceholder('Enter Your Email')

        this.locator_of_password_field = page.locator('[type="password"]')

        this.locator_of_login_button = page.getByRole('button', { name: 'LOGIN NOW' })

        this.locator_of_dashboard = page.locator('[data-tracker="2"]')

    }

    async gotoURL(targetURL: string, options?: Parameters<Page['goto']>[1]) {

        await this.page.goto(targetURL, options)
    }

    async enter_email(email: string) {

        await this.locator_of_username_field.click()
        await this.locator_of_username_field.fill(email)
    }
    async enter_password(password: string) {

        await this.locator_of_password_field.click()
        await this.locator_of_password_field.fill(password)

    }
    async click_Login_Button() {

        await this.locator_of_login_button.click()
    }
}
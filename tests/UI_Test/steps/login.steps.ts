import { expect } from '@playwright/test';
import { createBdd } from 'playwright-bdd';

const { Given, When, Then } = createBdd();


Given('I navigate to {string}', async ({page}, url) => {
  // Step: Given I nativate to "https://ecommerce-playground.lambdatest.io/"
  // From: tests\UI_Test\feature\login.feature:11:5
  await page.goto(url)
});

Given('I click on My account', async ({page}) => {
  // Step: And I click on My account
  // From: tests\UI_Test\feature\login.feature:12:5
  await page.getByRole('button', {name: 'My account'}).click()
});

Given('I enter E-Mail Address {string}', async ({page}, emailAddress) => {
  // Step: And I enter E-Mail Address "redoyig302@faxzu.com"
  // From: tests\UI_Test\feature\login.feature:13:5
  await page.getByPlaceholder('E-Mail Address').fill(emailAddress)
});

Given('I enter password {string}', async ({page}, password) => {
  // Step: And I enter password "test@1234"
  // From: tests\UI_Test\feature\login.feature:14:5
  await page.getByPlaceholder('Password').fill(password)
});

When('I click on submit button', async ({page}) => {
  // Step: When I click on submit button
  // From: tests\UI_Test\feature\login.feature:15:5
  await page.locator("input[value='Login']").click()
});

Then('I should verify url contains {string}', async ({page}, looged_URL) => {
  // Step: Then I should verify url contains "route=account/account"
  // From: tests\UI_Test\feature\login.feature:16:5
  await expect(page).toHaveURL(new RegExp(looged_URL))
});

Then('I should see login error message {string}', async ({page}, unlooged_URL) => {
  // Step: Then I should see login error message "Warning: No match for E-Mail Address and/or Password."
  // From: tests\UI_Test\feature\login.feature:22:9
  await expect(page).toHaveURL(new RegExp(unlooged_URL))
});
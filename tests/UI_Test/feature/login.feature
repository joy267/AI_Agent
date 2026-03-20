@login
Feature: Verify login

    Verify user is able to login with valid and invalid credentials

    Background:
        Given I navigate to "https://ecommerce-playground.lambdatest.io/"
        And I click on My account

    Scenario: Verify user is able to login with valid credentials
        When I enter E-Mail Address "redoyig302@faxzu.com"
        And I enter password "test@1234"
        And I click on submit button
        Then I should verify url contains "route=account/account"

    Scenario Outline: Verify user is not able to login with following credentials
        When I enter E-Mail Address "<email>"
        And I enter password "<password>"
        And I click on submit button
        Then I should see login error message "<errorMessage>"

        Examples:
            | email                  | password  | errorMessage |
            | invalid@email.com     | test123   | Warning: No match for E-Mail Address and/or Password. |
            |                       | test123   | Warning: No match for E-Mail Address and/or Password. |
            | invalid@email.com     |           | Warning: No match for E-Mail Address and/or Password. |
            |                       |           | Warning: No match for E-Mail Address and/or Password. |
            | redoyig302@faxzu.com | wrongpass | Warning: No match for E-Mail Address and/or Password. |
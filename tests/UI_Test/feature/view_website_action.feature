Feature: View Website Actions

  Background:
    Given the user navigates to "/operations/website_actions"
    Then the URL should be "/operations/website_actions"

  # TC_WA_01
  Scenario: Verify navigation to Home page via breadcrumbs
    Given the breadcrumbs section is visible
    And the "Home" breadcrumb link is visible and enabled
    When the user clicks on the "Home" breadcrumb link
    Then the user should be redirected to "/"

  # TC_WA_02
  Scenario: Verify Site Name search accepts valid input and displays relevant results
    Given the "Site Name" search field is visible
    When the user selects a valid site name from the dropdown
    Then the selected site name should be displayed in the input field
    And the table should display relevant search results
    And at least one result should match the selected site name

  # TC_WA_03
  Scenario: Verify pagination displays correct rows per page and supports navigation
    Given the website actions table is visible
    Then the table should display up to 10 rows on the first page
    And pagination controls should be visible
    When the user navigates to page 2
    Then page 2 should become active
    And the table should display up to 10 rows
    When the user navigates using First, Next, Previous, and Last buttons
    Then the corresponding page should become active
    When the user changes rows per page to 25
    Then the table should display up to 25 rows
    When the user changes rows per page back to 10
    Then the table should display up to 10 rows

  # TC_WA_04
  Scenario: Verify all filters work correctly and display filtered records
    Given the website actions table is visible
    And filter options are available
    When the user applies the "Type" filter
    Then the table should display filtered results based on Type
    When the user applies the "Territory" filter
    Then the table should display filtered results based on Territory
    When the user applies the "Industry" filter
    Then the table should display filtered results based on Industry
    When the user applies the "Status" filter
    Then the table should display filtered results based on Status
    When the user applies the "Sync" filter
    Then the table should display filtered results based on Sync
    When the user clicks on "Clear Filter"
    Then all filters should be cleared
    And the table should display all available records

  # TC_WA_05
  Scenario: Verify More Info functionality displays additional site information
    Given the website actions table is visible
    And at least one data row is present
    When the user clicks on the "More Info" button of a row
    Then the row should expand
    And additional site information should be displayed
    When the user clicks on the "More Info" button again
    Then the row should collapse
    And the additional information should be hidden  // ----- Done -----

  # TC_WA_06
  Scenario: Verify clicking on site name opens correct URL in a new tab
    Given the website actions table is visible
    And at least one site name link is available
    When the user clicks on a site name link
    Then a new tab should open
    And the new tab URL should match the site link URL

  # TC_WA_07
  Scenario: Verify Site Name search with invalid input shows No options message
    Given the "Site Name" search field is visible
    When the user enters invalid characters into the search field
    Then a "No options" message should be displayed

  # TC_WA_08
  Scenario: Verify application handles navigation to non-existent page gracefully
    Given the website actions table and pagination are visible
    When the user navigates to a page number greater than available pages via URL
    Then the application should handle it gracefully without crashing
    And the table should either show no data or redirect to a valid page
    When the user navigates to a negative page number via URL
    Then the application should default to the first valid page
    And the table should display valid records
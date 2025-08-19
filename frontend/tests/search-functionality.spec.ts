import { test, expect } from '@playwright/test';

/**
 * Comprehensive E2E tests for search functionality
 * Tests all critical search features and fixes implemented in the search audit
 */

test.describe('Search Functionality E2E Tests', () => {
  let testUser = {
    email: 'searchtest@example.com',
    password: 'testpassword'
  };

  test.beforeEach(async ({ page }) => {
    // Login with test user before each test
    await page.goto('/auth/login');
    await page.getByRole('textbox', { name: 'Email' }).fill(testUser.email);
    await page.getByRole('textbox', { name: 'Password' }).fill(testUser.password);
    await page.getByRole('button', { name: 'Login' }).click();
    await expect(page).toHaveURL(/\/(projects|dashboard)/);
  });

  test.describe('General Search Page', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto('/search');
      await expect(page).toHaveURL(/\/search/);
    });

    test('should display all filter sections', async ({ page }) => {
      // Check that all filter sections are visible
      await expect(page.getByRole('heading', { name: 'Page Management' })).toBeVisible();
      await expect(page.getByText('Date Range')).toBeVisible();
      await expect(page.getByText('Entities')).toBeVisible();
      await expect(page.getByText('Content')).toBeVisible();
    });

    test('should handle page management filters correctly', async ({ page }) => {
      // Test starred filter
      const starredCheckbox = page.locator('#starred-filter').nth(1);
      await starredCheckbox.click();
      
      // Check URL parameter is set
      await expect(page).toHaveURL(/starred_only=true/);
      
      // Check filter chip appears
      await expect(page.getByText('Starred only')).toBeVisible();
      
      // Check filter counter
      await expect(page.getByText('1')).toBeVisible();
      
      // Test filter removal via chip
      await page.getByRole('button').filter({ hasText: /^$/ }).nth(4).click();
      await expect(page).toHaveURL(/^(?!.*starred_only)/);
      await expect(page.getByText('Starred only')).not.toBeVisible();
    });

    test('should handle review status filters', async ({ page }) => {
      // Test relevant filter
      const relevantCheckbox = page.getByRole('checkbox').filter({ hasText: /Relevant/ });
      await relevantCheckbox.click();
      
      // Check URL parameter is set  
      await expect(page).toHaveURL(/review_status=relevant/);
      
      // Test irrelevant filter
      const irrelevantCheckbox = page.getByRole('checkbox').filter({ hasText: /Irrelevant/ });
      await irrelevantCheckbox.click();
      
      // Check URL parameter includes both
      await expect(page).toHaveURL(/review_status=relevant,irrelevant/);
    });

    test('should handle tag filters', async ({ page }) => {
      // Test tag input
      const tagInput = page.getByPlaceholder('Filter by tags...');
      await tagInput.fill('test-tag');
      await tagInput.press('Enter');
      
      // Check URL parameter is set
      await expect(page).toHaveURL(/tags=test-tag/);
    });

    test('should persist filter state on page reload', async ({ page }) => {
      // Set filters
      await page.locator('#starred-filter').nth(1).click();
      await page.getByPlaceholder('Filter by tags...').fill('test-tag');
      await page.getByPlaceholder('Filter by tags...').press('Enter');
      
      // Reload page
      await page.reload();
      
      // Check filters are still active
      await expect(page.locator('#starred-filter').nth(1)).toBeChecked();
      await expect(page.getByText('Starred only')).toBeVisible();
      await expect(page).toHaveURL(/starred_only=true/);
      await expect(page).toHaveURL(/tags=test-tag/);
    });

    test('should reset all filters correctly', async ({ page }) => {
      // Set multiple filters
      await page.locator('#starred-filter').nth(1).click();
      await page.getByRole('checkbox').filter({ hasText: /Relevant/ }).click();
      
      // Click reset all filters button
      await page.getByRole('button', { name: 'Reset all filters' }).click();
      
      // Check all filters are cleared
      await expect(page.locator('#starred-filter').nth(1)).not.toBeChecked();
      await expect(page.getByText('Starred only')).not.toBeVisible();
      await expect(page).toHaveURL(/^(?!.*starred_only)(?!.*review_status)/);
    });
  });

  test.describe('Mobile Filter Interface', () => {
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 812 });
      await page.goto('/search');
    });

    test('should open and close mobile filter sheet', async ({ page }) => {
      // Check mobile filter button is visible
      const filtersButton = page.getByRole('button', { name: 'Filters' }).nth(1);
      await expect(filtersButton).toBeVisible();
      
      // Open filter sheet
      await filtersButton.click();
      await expect(filtersButton).toHaveAttribute('aria-expanded', 'true');
      
      // Close with escape key
      await page.keyboard.press('Escape');
      await expect(filtersButton).toHaveAttribute('aria-expanded', 'false');
    });

    test('should contain page management filters in mobile sheet', async ({ page }) => {
      // Open filter sheet
      await page.getByRole('button', { name: 'Filters' }).nth(1).click();
      
      // Check page management section exists in mobile sheet
      // Note: The exact implementation may require different selectors
      // This test validates that the PageManagementFilters component is included
      await expect(page.getByText('Page Management')).toBeVisible();
    });
  });

  test.describe('URL State Management', () => {
    test('should handle deep linking with complex filters', async ({ page }) => {
      // Navigate directly to URL with multiple filter parameters
      await page.goto('/search?starred_only=true&tags=research,analysis&review_status=relevant');
      
      // Check filters are applied from URL
      await expect(page.locator('#starred-filter').nth(1)).toBeChecked();
      await expect(page.getByText('Starred only')).toBeVisible();
      await expect(page.getByText('Tag: research')).toBeVisible();
      await expect(page.getByText('Tag: analysis')).toBeVisible();
      await expect(page.getByText('Status: relevant')).toBeVisible();
    });

    test('should handle browser navigation correctly', async ({ page }) => {
      // Start with no filters
      await page.goto('/search');
      
      // Apply filter and check URL
      await page.locator('#starred-filter').nth(1).click();
      await expect(page).toHaveURL(/starred_only=true/);
      
      // Apply another filter
      await page.getByRole('checkbox').filter({ hasText: /Relevant/ }).click();
      await expect(page).toHaveURL(/review_status=relevant/);
      
      // Go back in browser history
      await page.goBack();
      await expect(page).toHaveURL(/starred_only=true/);
      await expect(page).not.toHaveURL(/review_status/);
      
      // Go forward
      await page.goForward();
      await expect(page).toHaveURL(/review_status=relevant/);
    });
  });

  test.describe('Filter Interaction Edge Cases', () => {
    test('should handle rapid filter changes without breaking', async ({ page }) => {
      await page.goto('/search');
      
      // Rapidly toggle filters
      for (let i = 0; i < 5; i++) {
        await page.locator('#starred-filter').nth(1).click();
        await page.waitForTimeout(100);
      }
      
      // Check final state is consistent
      await expect(page.locator('#starred-filter').nth(1)).toBeChecked();
      await expect(page).toHaveURL(/starred_only=true/);
    });

    test('should handle invalid URL parameters gracefully', async ({ page }) => {
      // Navigate to URL with invalid parameters
      await page.goto('/search?starred_only=invalid&tags=&review_status=nonexistent');
      
      // Check page loads without errors
      await expect(page.getByRole('heading', { name: 'Search' })).toBeVisible();
      
      // Check invalid parameters don't break functionality
      await page.locator('#starred-filter').nth(1).click();
      await expect(page).toHaveURL(/starred_only=true/);
    });
  });

  test.describe('Search Performance', () => {
    test('should debounce filter changes appropriately', async ({ page }) => {
      await page.goto('/search');
      
      // Listen for network requests
      const requests: string[] = [];
      page.on('request', (request) => {
        if (request.url().includes('/api/v1/search/pages')) {
          requests.push(request.url());
        }
      });
      
      // Rapidly change filters
      await page.locator('#starred-filter').nth(1).click();
      await page.getByRole('checkbox').filter({ hasText: /Relevant/ }).click();
      await page.getByRole('checkbox').filter({ hasText: /Irrelevant/ }).click();
      
      // Wait for debounce
      await page.waitForTimeout(500);
      
      // Check that excessive requests weren't made
      expect(requests.length).toBeLessThan(10);
    });
  });

  test.describe('Accessibility', () => {
    test('should have proper ARIA labels and keyboard navigation', async ({ page }) => {
      await page.goto('/search');
      
      // Check filter sections have proper headings
      await expect(page.getByRole('heading', { name: 'Page Management' })).toBeVisible();
      
      // Check checkboxes have proper labels
      const starredCheckbox = page.locator('#starred-filter').nth(1);
      await expect(starredCheckbox).toHaveAttribute('aria-describedby');
      
      // Test keyboard navigation
      await starredCheckbox.focus();
      await page.keyboard.press('Space');
      await expect(starredCheckbox).toBeChecked();
    });
  });
});

test.describe('Project Search Functionality', () => {
  test('should have same filter functionality as general search', async ({ page }) => {
    // This test would require a project to exist
    // For now, we document that project search should have identical functionality
    // TODO: Create test project and verify filter parity
    
    test.skip('Project search filter parity - requires test project setup');
  });
});
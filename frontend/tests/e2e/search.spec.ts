/**
 * End-to-end tests for search functionality
 */
import { test, expect } from '@playwright/test';

// Helper to login as test user
async function loginTestUser(page: any) {
  await page.goto('/auth/login');
  await page.fill('input[type="email"]', 'playwright@test.com');
  await page.fill('input[type="password"]', 'TestPassword123!');
  await page.click('button:has-text("Sign In")');
  await page.waitForURL(/dashboard|projects/);
}

test.describe('Search Functionality', () => {
  test.beforeEach(async ({ page }) => {
    await loginTestUser(page);
  });
  
  test('should perform basic search', async ({ page }) => {
    // Navigate to search page
    await page.goto('/search');
    await expect(page).toHaveURL('/search');
    
    // Enter search query
    await page.fill('[placeholder*="Search"]', 'test query');
    await page.press('[placeholder*="Search"]', 'Enter');
    
    // Should show results or no results message
    await expect(page.locator('.search-results, .no-results')).toBeVisible({ timeout: 10000 });
  });
  
  test('should apply search filters', async ({ page }) => {
    await page.goto('/search');
    
    // Open filters panel
    await page.click('button:has-text("Filters")');
    
    // Apply date range filter
    await page.fill('[name="dateFrom"]', '2024-01-01');
    await page.fill('[name="dateTo"]', '2024-12-31');
    
    // Apply domain filter if available
    const domainFilter = page.locator('[name="domain"]');
    if (await domainFilter.isVisible()) {
      await domainFilter.fill('example.com');
    }
    
    // Apply filters
    await page.click('button:has-text("Apply")');
    
    // Should update search results
    await expect(page.locator('.search-results, .no-results')).toBeVisible({ timeout: 10000 });
  });
  
  test('should handle advanced search syntax', async ({ page }) => {
    await page.goto('/search');
    
    // Test phrase search
    await page.fill('[placeholder*="Search"]', '"exact phrase"');
    await page.press('[placeholder*="Search"]', 'Enter');
    await page.waitForTimeout(500);
    
    // Test boolean operators
    await page.fill('[placeholder*="Search"]', 'term1 AND term2');
    await page.press('[placeholder*="Search"]', 'Enter');
    await page.waitForTimeout(500);
    
    // Test exclusion
    await page.fill('[placeholder*="Search"]', 'include -exclude');
    await page.press('[placeholder*="Search"]', 'Enter');
    
    // Should handle all search types
    await expect(page.locator('.search-results, .no-results')).toBeVisible({ timeout: 10000 });
  });
  
  test('should paginate search results', async ({ page }) => {
    await page.goto('/search');
    
    // Perform a search that returns multiple pages
    await page.fill('[placeholder*="Search"]', 'test');
    await page.press('[placeholder*="Search"]', 'Enter');
    
    // Wait for results
    await page.waitForSelector('.search-results, .no-results');
    
    // Check if pagination exists
    const pagination = page.locator('.pagination, [aria-label="pagination"]');
    if (await pagination.isVisible()) {
      // Click next page
      await page.click('button:has-text("Next"), [aria-label="Next page"]');
      
      // Should load new results
      await expect(page.locator('.search-results')).toBeVisible();
    }
  });
  
  test('should save search queries', async ({ page }) => {
    await page.goto('/search');
    
    // Perform a search
    await page.fill('[placeholder*="Search"]', 'important query');
    await page.press('[placeholder*="Search"]', 'Enter');
    
    // Wait for results
    await page.waitForSelector('.search-results, .no-results');
    
    // Save search if button exists
    const saveButton = page.locator('button:has-text("Save Search")');
    if (await saveButton.isVisible()) {
      await saveButton.click();
      
      // Should show success message
      await expect(page.locator('.alert-success, .toast-success')).toBeVisible();
    }
  });
});
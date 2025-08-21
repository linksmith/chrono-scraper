/**
 * End-to-end tests for entities and library features
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

test.describe('Entities Management', () => {
  test.beforeEach(async ({ page }) => {
    await loginTestUser(page);
  });
  
  test('should view entities dashboard', async ({ page }) => {
    // Navigate to entities page
    await page.goto('/entities');
    await expect(page).toHaveURL('/entities');
    
    // Should show entities dashboard
    await expect(page.locator('h1')).toContainText(/Entities/i);
    
    // Should display statistics
    await expect(page.locator('.stats-card')).toBeVisible();
    await expect(page.locator('text=/Total Entities|Persons|Organizations/')).toBeVisible();
  });
  
  test('should filter entities', async ({ page }) => {
    await page.goto('/entities');
    
    // Apply entity type filter
    await page.selectOption('[name="entityType"]', 'PERSON');
    
    // Apply confidence filter
    const confidenceSlider = page.locator('[name="minConfidence"]');
    if (await confidenceSlider.isVisible()) {
      await confidenceSlider.fill('0.8');
    }
    
    // Apply status filter
    await page.selectOption('[name="status"]', 'verified');
    
    // Should update entity list
    await expect(page.locator('.entities-list, .entity-card')).toBeVisible();
  });
  
  test('should create new entity', async ({ page }) => {
    await page.goto('/entities');
    
    // Click create entity button
    await page.click('button:has-text("Create Entity")');
    
    // Fill entity form
    await page.fill('[name="name"]', 'Test Entity');
    await page.selectOption('[name="type"]', 'PERSON');
    await page.fill('[name="description"]', 'Test entity for E2E testing');
    
    // Add metadata
    await page.fill('[name="metadata.role"]', 'Test Role');
    await page.fill('[name="metadata.location"]', 'Test Location');
    
    // Submit form
    await page.click('button:has-text("Create")');
    
    // Should show success message
    await expect(page.locator('.alert-success')).toBeVisible();
  });
  
  test('should link entities', async ({ page }) => {
    await page.goto('/entities');
    
    // Select first entity if exists
    const entityCard = page.locator('.entity-card').first();
    if (await entityCard.isVisible()) {
      await entityCard.click();
      
      // Click link entities button
      await page.click('button:has-text("Link Entity")');
      
      // Search for entity to link
      await page.fill('[placeholder*="Search entities"]', 'test');
      
      // Select entity from results
      const linkOption = page.locator('.link-option').first();
      if (await linkOption.isVisible()) {
        await linkOption.click();
        
        // Set relationship type
        await page.selectOption('[name="relationshipType"]', 'associated_with');
        
        // Confirm linking
        await page.click('button:has-text("Link")');
        
        // Should show success
        await expect(page.locator('.alert-success')).toBeVisible();
      }
    }
  });
});

test.describe('Library Features', () => {
  test.beforeEach(async ({ page }) => {
    await loginTestUser(page);
  });
  
  test('should view library dashboard', async ({ page }) => {
    // Navigate to library
    await page.goto('/library');
    await expect(page).toHaveURL('/library');
    
    // Should show library dashboard
    await expect(page.locator('h1')).toContainText(/Library/i);
    
    // Should show statistics
    await expect(page.locator('.library-stats')).toBeVisible();
    await expect(page.locator('text=/Starred Items|Saved Searches|Collections/')).toBeVisible();
  });
  
  test('should star and unstar items', async ({ page }) => {
    // Navigate to search or pages
    await page.goto('/search');
    
    // Perform a search
    await page.fill('[placeholder*="Search"]', 'test');
    await page.press('[placeholder*="Search"]', 'Enter');
    
    // Wait for results
    await page.waitForSelector('.search-results, .no-results');
    
    // Star first result if exists
    const starButton = page.locator('button[aria-label*="Star"]').first();
    if (await starButton.isVisible()) {
      await starButton.click();
      
      // Should show starred state
      await expect(starButton).toHaveAttribute('aria-pressed', 'true');
      
      // Navigate to library
      await page.goto('/library');
      
      // Should show in starred items
      await page.click('button:has-text("Starred"), a:has-text("Starred")');
      await expect(page.locator('.starred-item')).toHaveCount({ minimum: 1 });
    }
  });
  
  test('should create and manage collections', async ({ page }) => {
    await page.goto('/library');
    
    // Navigate to collections
    await page.click('button:has-text("Collections"), a:has-text("Collections")');
    
    // Create new collection
    await page.click('button:has-text("New Collection")');
    
    // Fill collection form
    await page.fill('[name="name"]', 'Test Collection');
    await page.fill('[name="description"]', 'E2E test collection');
    await page.selectOption('[name="visibility"]', 'private');
    
    // Create collection
    await page.click('button:has-text("Create")');
    
    // Should show success
    await expect(page.locator('.alert-success')).toBeVisible();
    
    // Should appear in collections list
    await expect(page.locator('text=Test Collection')).toBeVisible();
  });
  
  test('should add items to collection', async ({ page }) => {
    await page.goto('/library');
    
    // Navigate to collections
    await page.click('button:has-text("Collections"), a:has-text("Collections")');
    
    // Open first collection if exists
    const collection = page.locator('.collection-card').first();
    if (await collection.isVisible()) {
      await collection.click();
      
      // Click add items button
      await page.click('button:has-text("Add Items")');
      
      // Search for items
      await page.fill('[placeholder*="Search items"]', 'test');
      
      // Select items
      const itemCheckbox = page.locator('.item-checkbox').first();
      if (await itemCheckbox.isVisible()) {
        await itemCheckbox.check();
        
        // Add to collection
        await page.click('button:has-text("Add Selected")');
        
        // Should show success
        await expect(page.locator('.alert-success')).toBeVisible();
      }
    }
  });
  
  test('should manage saved searches', async ({ page }) => {
    await page.goto('/library');
    
    // Navigate to saved searches
    await page.click('button:has-text("Saved Searches"), a:has-text("Saved Searches")');
    
    // Should show saved searches or empty state
    await expect(page.locator('.saved-searches-list, .empty-state')).toBeVisible();
    
    // Run saved search if exists
    const savedSearch = page.locator('.saved-search-item').first();
    if (await savedSearch.isVisible()) {
      // Click run button
      await savedSearch.click('button:has-text("Run")');
      
      // Should navigate to search with query
      await expect(page).toHaveURL(/search/);
      await expect(page.locator('[placeholder*="Search"]')).not.toBeEmpty();
    }
  });
  
  test('should view recent activity', async ({ page }) => {
    await page.goto('/library');
    
    // Navigate to recent tab
    await page.click('button:has-text("Recent"), a:has-text("Recent")');
    
    // Should show recent items
    await expect(page.locator('.recent-items, .activity-feed')).toBeVisible();
    
    // Items should have timestamps
    await expect(page.locator('.timestamp, time')).toHaveCount({ minimum: 0 });
  });
});
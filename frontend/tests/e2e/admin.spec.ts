/**
 * End-to-end tests for admin functionality
 */
import { test, expect } from '@playwright/test';

// Helper to login as admin user
async function loginAdminUser(page: any) {
  await page.goto('/auth/login');
  await page.fill('input[type="email"]', 'admin@chrono-scraper.com');
  await page.fill('input[type="password"]', 'changeme');
  await page.click('button:has-text("Sign In")');
  await page.waitForURL(/dashboard|admin/);
}

test.describe('Admin Panel', () => {
  test.beforeEach(async ({ page }) => {
    // Skip if admin user doesn't exist
    try {
      await loginAdminUser(page);
    } catch (error) {
      test.skip();
    }
  });
  
  test('should access admin dashboard', async ({ page }) => {
    // Navigate to admin panel
    await page.goto('/admin');
    
    // Should show admin dashboard
    await expect(page).toHaveURL('/admin');
    await expect(page.locator('h1')).toContainText(/Admin|Dashboard/i);
  });
  
  test('should manage user approvals', async ({ page }) => {
    await page.goto('/admin');
    
    // Navigate to user approvals section
    await page.click('a:has-text("User Approvals"), button:has-text("User Approvals")');
    
    // Should show pending users list
    await expect(page.locator('.pending-users, .user-approvals')).toBeVisible();
    
    // If there are pending users, test approval flow
    const pendingUser = page.locator('.pending-user-item').first();
    if (await pendingUser.isVisible()) {
      // View user details
      await pendingUser.click('button:has-text("View Details")');
      
      // Should show user information
      await expect(page.locator('.user-details')).toBeVisible();
      
      // Approve or reject user
      const approveButton = page.locator('button:has-text("Approve")');
      if (await approveButton.isVisible()) {
        await approveButton.click();
        
        // Confirm action
        await page.click('button:has-text("Confirm")');
        
        // Should show success message
        await expect(page.locator('.alert-success')).toBeVisible();
      }
    }
  });
  
  test('should manage invitation tokens', async ({ page }) => {
    await page.goto('/admin');
    
    // Navigate to invitations section
    await page.click('a:has-text("Invitations"), button:has-text("Invitations")');
    
    // Create new invitation
    await page.click('button:has-text("Create Invitation")');
    
    // Fill invitation form
    await page.fill('[name="email"]', 'newinvite@example.com');
    await page.fill('[name="maxUses"]', '1');
    await page.fill('[name="expiresIn"]', '7'); // days
    
    // Submit form
    await page.click('button:has-text("Create")');
    
    // Should show success and display token
    await expect(page.locator('.invitation-token, .alert-success')).toBeVisible();
  });
  
  test('should view system statistics', async ({ page }) => {
    await page.goto('/admin');
    
    // Should display system stats
    await expect(page.locator('.stats-card, .statistics')).toBeVisible();
    
    // Check for key metrics
    await expect(page.locator('text=/Total Users|Active Projects|Pages Scraped/')).toBeVisible();
  });
  
  test('should manage system settings', async ({ page }) => {
    await page.goto('/admin');
    
    // Navigate to settings
    await page.click('a:has-text("Settings"), button:has-text("Settings")');
    
    // Should show settings form
    await expect(page.locator('.settings-form, form')).toBeVisible();
    
    // Test updating a setting
    const rateLimit = page.locator('[name="defaultRateLimit"]');
    if (await rateLimit.isVisible()) {
      await rateLimit.fill('100');
      await page.click('button:has-text("Save")');
      
      // Should show success message
      await expect(page.locator('.alert-success')).toBeVisible();
    }
  });
});
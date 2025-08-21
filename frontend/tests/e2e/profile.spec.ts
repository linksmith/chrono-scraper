/**
 * End-to-end tests for user profile management
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

test.describe('Profile Management', () => {
  test.beforeEach(async ({ page }) => {
    await loginTestUser(page);
  });
  
  test('should view user profile', async ({ page }) => {
    // Navigate to profile page
    await page.goto('/profile');
    await expect(page).toHaveURL('/profile');
    
    // Should display user information
    await expect(page.locator('h1')).toContainText(/Profile|Account/i);
    await expect(page.locator('text=playwright@test.com')).toBeVisible();
  });
  
  test('should update profile information', async ({ page }) => {
    await page.goto('/profile');
    
    // Click edit button
    await page.click('button:has-text("Edit Profile")');
    
    // Update profile fields
    await page.fill('[name="fullName"]', 'Updated Test User');
    await page.fill('[name="organization"]', 'Test Organization');
    await page.fill('[name="professionalTitle"]', 'Senior Researcher');
    await page.fill('[name="researchInterests"]', 'Updated OSINT Research, Data Analysis');
    
    // Save changes
    await page.click('button:has-text("Save")');
    
    // Should show success message
    await expect(page.locator('.alert-success')).toBeVisible();
    await expect(page.locator('.alert-success')).toContainText(/updated|saved/i);
  });
  
  test('should update password', async ({ page }) => {
    await page.goto('/profile');
    
    // Navigate to security settings
    await page.click('button:has-text("Security"), a:has-text("Security")');
    
    // Click change password
    await page.click('button:has-text("Change Password")');
    
    // Fill password change form
    await page.fill('[name="currentPassword"]', 'TestPassword123!');
    await page.fill('[name="newPassword"]', 'NewTestPassword123!');
    await page.fill('[name="confirmPassword"]', 'NewTestPassword123!');
    
    // Submit form
    await page.click('button:has-text("Update Password")');
    
    // Should show success message
    await expect(page.locator('.alert-success')).toBeVisible();
  });
  
  test('should manage API keys', async ({ page }) => {
    await page.goto('/profile');
    
    // Navigate to API keys section
    await page.click('button:has-text("API Keys"), a:has-text("API Keys")');
    
    // Create new API key
    await page.click('button:has-text("Generate New Key")');
    
    // Fill API key form
    await page.fill('[name="keyName"]', 'Test API Key');
    await page.selectOption('[name="permissions"]', 'read');
    
    // Generate key
    await page.click('button:has-text("Generate")');
    
    // Should show the generated key
    await expect(page.locator('.api-key-display')).toBeVisible();
    
    // Copy key button should work
    await page.click('button:has-text("Copy")');
    await expect(page.locator('.copied-message')).toBeVisible();
  });
  
  test('should manage notification preferences', async ({ page }) => {
    await page.goto('/profile');
    
    // Navigate to notifications
    await page.click('button:has-text("Notifications"), a:has-text("Notifications")');
    
    // Toggle notification settings
    const emailNotifications = page.locator('[name="emailNotifications"]');
    if (await emailNotifications.isVisible()) {
      await emailNotifications.click();
    }
    
    const webNotifications = page.locator('[name="webNotifications"]');
    if (await webNotifications.isVisible()) {
      await webNotifications.click();
    }
    
    // Save preferences
    await page.click('button:has-text("Save Preferences")');
    
    // Should show success message
    await expect(page.locator('.alert-success')).toBeVisible();
  });
  
  test('should view activity history', async ({ page }) => {
    await page.goto('/profile');
    
    // Navigate to activity tab
    await page.click('button:has-text("Activity"), a:has-text("Activity")');
    
    // Should show activity history
    await expect(page.locator('.activity-list, .activity-history')).toBeVisible();
    
    // Should show recent activities
    await expect(page.locator('.activity-item, .activity-entry')).toHaveCount({ minimum: 0 });
  });
});
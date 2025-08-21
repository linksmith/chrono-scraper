/**
 * End-to-end tests for invitation system
 */
import { test, expect } from '@playwright/test';

test.describe('Invitation System', () => {
  test('should handle invitation registration flow', async ({ page }) => {
    // Navigate to register-invite page with token
    const inviteToken = 'test-invite-token-123';
    await page.goto(`/auth/register-invite?token=${inviteToken}`);
    
    // Page should load with invitation form
    await expect(page).toHaveURL(new RegExp('/auth/register-invite'));
    await expect(page.locator('h1')).toContainText('Complete Registration');
    
    // Fill registration form
    await page.fill('[name="email"]', 'invited@example.com');
    await page.fill('[name="password"]', 'SecurePass123!');
    await page.fill('[name="confirmPassword"]', 'SecurePass123!');
    await page.fill('[name="fullName"]', 'Invited User');
    await page.fill('[name="researchInterests"]', 'OSINT Research');
    await page.fill('[name="researchPurpose"]', 'Historical analysis');
    await page.fill('[name="expectedUsage"]', 'Academic research');
    
    // Accept agreements
    await page.check('[name="dataHandlingAgreement"]');
    await page.check('[name="ethicsAgreement"]');
    
    // Submit form
    await page.click('button[type="submit"]');
    
    // Should show success or redirect to login
    await expect(page.locator('.alert-success, .redirect-message')).toBeVisible({ timeout: 10000 });
  });
  
  test('should reject invalid invitation token', async ({ page }) => {
    await page.goto('/auth/register-invite?token=invalid-token');
    
    // Should show error message
    await expect(page.locator('.alert-error')).toBeVisible();
    await expect(page.locator('.alert-error')).toContainText(/invalid|expired/i);
  });
  
  test('should require all mandatory fields', async ({ page }) => {
    await page.goto('/auth/register-invite?token=test-token');
    
    // Try to submit without filling required fields
    await page.click('button[type="submit"]');
    
    // Should show validation errors
    await expect(page.locator('.field-error')).toHaveCount({ minimum: 1 });
  });
});
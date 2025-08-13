/**
 * End-to-end tests for authentication flows
 */
import { test, expect } from '@playwright/test';

test.describe('Authentication Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Start from the index page
    await page.goto('/');
  });

  test.describe('User Registration', () => {
    test('should allow user to register with valid information', async ({ page }) => {
      // Navigate to registration page
      await page.click('text=Sign Up');
      await expect(page).toHaveURL('/auth/register');

      // Fill registration form
      await page.fill('[data-testid="email-input"]', 'newuser@example.com');
      await page.fill('[data-testid="password-input"]', 'strongpassword123');
      await page.fill('[data-testid="confirm-password-input"]', 'strongpassword123');
      await page.fill('[data-testid="full-name-input"]', 'New Test User');

      // Submit form
      await page.click('[data-testid="register-button"]');

      // Should show success message
      await expect(page.locator('[data-testid="success-message"]')).toBeVisible();
      await expect(page.locator('[data-testid="success-message"]')).toContainText('Registration successful');
    });

    test('should show validation errors for invalid email', async ({ page }) => {
      await page.click('text=Sign Up');
      
      await page.fill('[data-testid="email-input"]', 'invalid-email');
      await page.fill('[data-testid="password-input"]', 'password123');
      await page.fill('[data-testid="full-name-input"]', 'Test User');
      
      await page.click('[data-testid="register-button"]');

      await expect(page.locator('[data-testid="email-error"]')).toBeVisible();
      await expect(page.locator('[data-testid="email-error"]')).toContainText('valid email');
    });

    test('should show validation errors for weak password', async ({ page }) => {
      await page.click('text=Sign Up');
      
      await page.fill('[data-testid="email-input"]', 'test@example.com');
      await page.fill('[data-testid="password-input"]', 'weak');
      await page.fill('[data-testid="full-name-input"]', 'Test User');
      
      await page.click('[data-testid="register-button"]');

      await expect(page.locator('[data-testid="password-error"]')).toBeVisible();
      await expect(page.locator('[data-testid="password-error"]')).toContainText('at least 8 characters');
    });

    test('should show error for mismatched password confirmation', async ({ page }) => {
      await page.click('text=Sign Up');
      
      await page.fill('[data-testid="email-input"]', 'test@example.com');
      await page.fill('[data-testid="password-input"]', 'password123');
      await page.fill('[data-testid="confirm-password-input"]', 'different123');
      await page.fill('[data-testid="full-name-input"]', 'Test User');
      
      await page.click('[data-testid="register-button"]');

      await expect(page.locator('[data-testid="confirm-password-error"]')).toBeVisible();
      await expect(page.locator('[data-testid="confirm-password-error"]')).toContainText('Passwords do not match');
    });
  });

  test.describe('User Login', () => {
    test('should allow user to login with valid credentials', async ({ page }) => {
      // Navigate to login page
      await page.click('text=Sign In');
      await expect(page).toHaveURL('/auth/login');

      // Fill login form
      await page.fill('[data-testid="email-input"]', 'test@example.com');
      await page.fill('[data-testid="password-input"]', 'testpassword123');

      // Submit form
      await page.click('[data-testid="login-button"]');

      // Should redirect to dashboard
      await expect(page).toHaveURL('/dashboard');
      
      // Should show user info in header
      await expect(page.locator('[data-testid="user-menu"]')).toBeVisible();
    });

    test('should show error for invalid credentials', async ({ page }) => {
      await page.click('text=Sign In');
      
      await page.fill('[data-testid="email-input"]', 'wrong@example.com');
      await page.fill('[data-testid="password-input"]', 'wrongpassword');
      
      await page.click('[data-testid="login-button"]');

      await expect(page.locator('[data-testid="error-message"]')).toBeVisible();
      await expect(page.locator('[data-testid="error-message"]')).toContainText('Invalid credentials');
    });

    test('should show loading state during login', async ({ page }) => {
      await page.click('text=Sign In');
      
      await page.fill('[data-testid="email-input"]', 'test@example.com');
      await page.fill('[data-testid="password-input"]', 'testpassword123');
      
      await page.click('[data-testid="login-button"]');

      // Button should show loading state
      await expect(page.locator('[data-testid="login-button"]')).toContainText('Signing in...');
      await expect(page.locator('[data-testid="login-button"]')).toBeDisabled();
    });

    test('should toggle password visibility', async ({ page }) => {
      await page.click('text=Sign In');
      
      const passwordInput = page.locator('[data-testid="password-input"]');
      const toggleButton = page.locator('[data-testid="password-toggle"]');
      
      // Initially password should be hidden
      await expect(passwordInput).toHaveAttribute('type', 'password');
      
      // Click toggle to show password
      await toggleButton.click();
      await expect(passwordInput).toHaveAttribute('type', 'text');
      
      // Click toggle again to hide password
      await toggleButton.click();
      await expect(passwordInput).toHaveAttribute('type', 'password');
    });
  });

  test.describe('Password Reset', () => {
    test('should allow user to request password reset', async ({ page }) => {
      await page.click('text=Sign In');
      await page.click('text=Forgot Password?');
      
      await expect(page).toHaveURL('/auth/password-reset');
      
      await page.fill('[data-testid="email-input"]', 'test@example.com');
      await page.click('[data-testid="reset-button"]');
      
      await expect(page.locator('[data-testid="success-message"]')).toBeVisible();
      await expect(page.locator('[data-testid="success-message"]')).toContainText('Password reset email sent');
    });

    test('should handle password reset with invalid email', async ({ page }) => {
      await page.goto('/auth/password-reset');
      
      await page.fill('[data-testid="email-input"]', 'invalid-email');
      await page.click('[data-testid="reset-button"]');
      
      await expect(page.locator('[data-testid="email-error"]')).toBeVisible();
    });
  });

  test.describe('Logout', () => {
    test('should allow user to logout', async ({ page }) => {
      // First login
      await page.goto('/auth/login');
      await page.fill('[data-testid="email-input"]', 'test@example.com');
      await page.fill('[data-testid="password-input"]', 'testpassword123');
      await page.click('[data-testid="login-button"]');
      
      await expect(page).toHaveURL('/dashboard');
      
      // Open user menu and logout
      await page.click('[data-testid="user-menu"]');
      await page.click('[data-testid="logout-button"]');
      
      // Should redirect to home page
      await expect(page).toHaveURL('/');
      
      // User menu should not be visible
      await expect(page.locator('[data-testid="user-menu"]')).not.toBeVisible();
    });
  });

  test.describe('Navigation Protection', () => {
    test('should redirect unauthenticated users to login', async ({ page }) => {
      // Try to access protected dashboard
      await page.goto('/dashboard');
      
      // Should redirect to login
      await expect(page).toHaveURL('/auth/login');
    });

    test('should redirect authenticated users away from auth pages', async ({ page }) => {
      // First login
      await page.goto('/auth/login');
      await page.fill('[data-testid="email-input"]', 'test@example.com');
      await page.fill('[data-testid="password-input"]', 'testpassword123');
      await page.click('[data-testid="login-button"]');
      
      await expect(page).toHaveURL('/dashboard');
      
      // Try to access login page while authenticated
      await page.goto('/auth/login');
      
      // Should redirect to dashboard
      await expect(page).toHaveURL('/dashboard');
    });
  });

  test.describe('Session Persistence', () => {
    test('should maintain session across page refreshes', async ({ page }) => {
      // Login
      await page.goto('/auth/login');
      await page.fill('[data-testid="email-input"]', 'test@example.com');
      await page.fill('[data-testid="password-input"]', 'testpassword123');
      await page.click('[data-testid="login-button"]');
      
      await expect(page).toHaveURL('/dashboard');
      
      // Refresh page
      await page.reload();
      
      // Should still be on dashboard and authenticated
      await expect(page).toHaveURL('/dashboard');
      await expect(page.locator('[data-testid="user-menu"]')).toBeVisible();
    });

    test('should handle expired tokens gracefully', async ({ page, context }) => {
      // Login first
      await page.goto('/auth/login');
      await page.fill('[data-testid="email-input"]', 'test@example.com');
      await page.fill('[data-testid="password-input"]', 'testpassword123');
      await page.click('[data-testid="login-button"]');
      
      // Simulate expired token by clearing storage
      await context.clearCookies();
      await page.evaluate(() => localStorage.clear());
      
      // Try to access protected route
      await page.goto('/dashboard');
      
      // Should redirect to login
      await expect(page).toHaveURL('/auth/login');
    });
  });

  test.describe('Error Handling', () => {
    test('should handle network errors gracefully', async ({ page }) => {
      // Intercept network requests and simulate failure
      await page.route('**/api/v1/auth/login', route => {
        route.abort('failed');
      });
      
      await page.goto('/auth/login');
      await page.fill('[data-testid="email-input"]', 'test@example.com');
      await page.fill('[data-testid="password-input"]', 'testpassword123');
      await page.click('[data-testid="login-button"]');
      
      await expect(page.locator('[data-testid="error-message"]')).toBeVisible();
      await expect(page.locator('[data-testid="error-message"]')).toContainText('Network error');
    });

    test('should clear errors when user starts typing', async ({ page }) => {
      await page.goto('/auth/login');
      
      // Trigger an error first
      await page.fill('[data-testid="email-input"]', 'wrong@example.com');
      await page.fill('[data-testid="password-input"]', 'wrongpassword');
      await page.click('[data-testid="login-button"]');
      
      await expect(page.locator('[data-testid="error-message"]')).toBeVisible();
      
      // Start typing in email field
      await page.fill('[data-testid="email-input"]', 'correct@example.com');
      
      // Error should be cleared
      await expect(page.locator('[data-testid="error-message"]')).not.toBeVisible();
    });
  });

  test.describe('Accessibility', () => {
    test('should have proper form labels and ARIA attributes', async ({ page }) => {
      await page.goto('/auth/login');
      
      // Check form has proper labels
      await expect(page.locator('label[for="email"]')).toBeVisible();
      await expect(page.locator('label[for="password"]')).toBeVisible();
      
      // Check ARIA attributes
      const emailInput = page.locator('[data-testid="email-input"]');
      await expect(emailInput).toHaveAttribute('aria-required', 'true');
      
      const passwordInput = page.locator('[data-testid="password-input"]');
      await expect(passwordInput).toHaveAttribute('aria-required', 'true');
    });

    test('should be keyboard navigable', async ({ page }) => {
      await page.goto('/auth/login');
      
      // Tab through form elements
      await page.keyboard.press('Tab');
      await expect(page.locator('[data-testid="email-input"]')).toBeFocused();
      
      await page.keyboard.press('Tab');
      await expect(page.locator('[data-testid="password-input"]')).toBeFocused();
      
      await page.keyboard.press('Tab');
      await expect(page.locator('[data-testid="password-toggle"]')).toBeFocused();
      
      await page.keyboard.press('Tab');
      await expect(page.locator('[data-testid="login-button"]')).toBeFocused();
    });
  });
});
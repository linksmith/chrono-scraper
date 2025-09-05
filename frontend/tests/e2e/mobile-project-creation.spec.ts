/**
 * Mobile-specific end-to-end tests for project creation flow
 * Tests responsive design, touch interactions, and usability across different viewport sizes
 */
import { test, expect, type Page } from '@playwright/test';

// Helper function to login before each test
async function loginUser(page: Page) {
  await page.goto('/auth/login');
  await page.fill('[data-testid="email-input"]', 'playwright@test.com');
  await page.fill('[data-testid="password-input"]', 'TestPassword123!');
  await page.click('[data-testid="login-button"]');
  await expect(page).toHaveURL('/dashboard');
}

// Helper function to check if content overflows container
async function checkForOverflow(page: Page, selector: string) {
  const element = page.locator(selector);
  const overflow = await element.evaluate((el) => {
    const style = window.getComputedStyle(el);
    return {
      overflowX: style.overflowX,
      overflowY: style.overflowY,
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth,
      scrollHeight: el.scrollHeight,
      clientHeight: el.clientHeight
    };
  });
  
  const hasHorizontalOverflow = overflow.scrollWidth > overflow.clientWidth && overflow.overflowX === 'visible';
  const hasVerticalOverflow = overflow.scrollHeight > overflow.clientHeight && overflow.overflowY === 'visible';
  
  return { hasHorizontalOverflow, hasVerticalOverflow };
}

// Helper function to verify touch target sizes
async function verifyTouchTargetSize(page: Page, selector: string, minSize = 44) {
  const element = page.locator(selector);
  const boundingBox = await element.boundingBox();
  
  expect(boundingBox?.width || 0).toBeGreaterThanOrEqual(minSize);
  expect(boundingBox?.height || 0).toBeGreaterThanOrEqual(minSize);
}

test.describe('Mobile Project Creation Flow', () => {
  // Define viewport sizes to test
  const viewports = [
    { name: 'iPhone SE', width: 320, height: 568 },
    { name: 'iPhone 8', width: 375, height: 667 },
    { name: 'iPhone 12 Pro', width: 414, height: 896 },
    { name: 'iPad Mini', width: 768, height: 1024 }
  ];

  viewports.forEach(({ name, width, height }) => {
    test.describe(`${name} (${width}x${height})`, () => {
      test.beforeEach(async ({ page }) => {
        await page.setViewportSize({ width, height });
        await loginUser(page);
      });

      test('should display responsive layout without horizontal overflow', async ({ page }) => {
        // Navigate to project creation page
        await page.goto('/projects/create');

        // Check main container doesn't cause horizontal overflow
        const { hasHorizontalOverflow } = await checkForOverflow(page, 'body');
        expect(hasHorizontalOverflow).toBeFalsy();

        // Check form container doesn't overflow
        const formContainer = page.locator('.max-w-4xl');
        const formOverflow = await checkForOverflow(page, '.max-w-4xl');
        expect(formOverflow.hasHorizontalOverflow).toBeFalsy();

        // Verify form is properly centered and has appropriate margins
        const formBox = await formContainer.boundingBox();
        expect(formBox?.x || 0).toBeGreaterThanOrEqual(8); // At least 8px margin on each side
        expect((formBox?.x || 0) + (formBox?.width || 0)).toBeLessThanOrEqual(width - 8);
      });

      test('should have properly sized touch targets', async ({ page }) => {
        await page.goto('/projects/create');

        // Wait for form to load
        await page.waitForSelector('h2:has-text("Basic Information")');

        // Test navigation buttons have proper touch target sizes
        const nextButton = page.locator('button:has-text("Next")');
        if (await nextButton.isVisible()) {
          await verifyTouchTargetSize(page, 'button:has-text("Next")', 44);
        }

        const cancelButton = page.locator('button:has-text("Cancel")');
        if (await cancelButton.isVisible()) {
          await verifyTouchTargetSize(page, 'button:has-text("Cancel")', 44);
        }

        // Test radio buttons and checkboxes have adequate touch targets
        const radioButtons = page.locator('input[type="radio"]');
        const radioCount = await radioButtons.count();
        for (let i = 0; i < radioCount; i++) {
          const radioParent = radioButtons.nth(i).locator('..');
          const parentBox = await radioParent.boundingBox();
          expect(parentBox?.height || 0).toBeGreaterThanOrEqual(44);
        }
      });

      test('should complete full project creation flow', async ({ page }) => {
        await page.goto('/projects/create');

        // Step 1: Basic Information
        await page.waitForSelector('h2:has-text("Basic Information")');
        await page.fill('input[placeholder*="project name"]', `Mobile Test Project ${width}px`);
        await page.fill('textarea[placeholder*="description"]', 'A test project created on mobile viewport');
        
        // Check if Next button is enabled and click it
        const nextButton = page.locator('button:has-text("Next")');
        await expect(nextButton).toBeEnabled();
        await nextButton.click();

        // Step 2: Configure Your Targets
        await page.waitForSelector('h2:has-text("Configure Your Targets")');
        
        // Fill in the target input
        const targetInput = page.locator('input[placeholder="example.com"]').first();
        await targetInput.fill('example.com');
        
        // Add another target
        await page.click('button:has-text("Add Another Target")');
        const secondTargetInput = page.locator('input[placeholder="example.com"]').nth(1);
        await secondTargetInput.fill('test.com');

        // Proceed to next step
        await nextButton.click();

        // Step 3: Processing Options
        await page.waitForSelector('h2:has-text("Processing Options")');
        
        // Verify auto-start option is visible and can be toggled
        const autoStartCheckbox = page.locator('input[type="checkbox"]').first();
        await autoStartCheckbox.click(); // Toggle it
        await autoStartCheckbox.click(); // Toggle back
        
        await nextButton.click();

        // Step 4: Review & Confirm
        await page.waitForSelector('h2:has-text("Review & Confirm")');
        
        // Verify project details are shown
        await expect(page.locator('text=Mobile Test Project')).toBeVisible();
        await expect(page.locator('text=example.com')).toBeVisible();
        
        // Create the project
        const createButton = page.locator('button:has-text("Create Project")');
        await expect(createButton).toBeEnabled();
        await createButton.click();

        // Should redirect to project page
        await expect(page).toHaveURL(/\/projects\/[a-f0-9-]+$/);
        
        // Verify we can see the created project
        await expect(page.locator(`text=Mobile Test Project ${width}px`)).toBeVisible();
      });

      test('should handle form validation properly on mobile', async ({ page }) => {
        await page.goto('/projects/create');

        // Try to proceed without filling required fields
        const nextButton = page.locator('button:has-text("Next")');
        await expect(nextButton).toBeDisabled();

        // Fill project name but leave description empty
        await page.fill('input[placeholder*="project name"]', 'Test Project');
        await expect(nextButton).toBeEnabled();
        await nextButton.click();

        // On targets step, try to proceed without targets
        await page.waitForSelector('h2:has-text("Configure Your Targets")');
        
        // Clear the default target
        const targetInput = page.locator('input[placeholder="example.com"]').first();
        await targetInput.fill('');
        
        // Next button should be disabled
        await expect(nextButton).toBeDisabled();

        // Add a valid target
        await targetInput.fill('valid-domain.com');
        await expect(nextButton).toBeEnabled();
      });

      test('should handle multi-step navigation correctly', async ({ page }) => {
        await page.goto('/projects/create');

        // Progress through steps
        await page.fill('input[placeholder*="project name"]', 'Navigation Test');
        await page.click('button:has-text("Next")');
        
        await page.waitForSelector('h2:has-text("Configure Your Targets")');
        await page.fill('input[placeholder="example.com"]', 'example.com');
        await page.click('button:has-text("Next")');

        await page.waitForSelector('h2:has-text("Processing Options")');
        
        // Test Previous button
        const previousButton = page.locator('button:has-text("Previous")');
        await previousButton.click();
        
        // Should go back to targets step
        await expect(page.locator('h2:has-text("Configure Your Targets")')).toBeVisible();
        
        // Values should be preserved
        const targetValue = await page.locator('input[placeholder="example.com"]').inputValue();
        expect(targetValue).toBe('example.com');
        
        // Go back to processing options
        await page.click('button:has-text("Next")');
        await page.waitForSelector('h2:has-text("Processing Options")');
      });

      test('should display progress indicator correctly', async ({ page }) => {
        await page.goto('/projects/create');

        // Check progress indicator is visible
        const progressIndicator = page.locator('[role="progressbar"], .progress');
        if (await progressIndicator.count() > 0) {
          await expect(progressIndicator.first()).toBeVisible();
        }

        // Check step counter
        const stepInfo = page.locator('text=Step 1 of 4');
        if (await stepInfo.count() > 0) {
          await expect(stepInfo).toBeVisible();
        }

        // Progress through steps and verify step counter updates
        await page.fill('input[placeholder*="project name"]', 'Progress Test');
        await page.click('button:has-text("Next")');

        if (await page.locator('text=Step 2 of 4').count() > 0) {
          await expect(page.locator('text=Step 2 of 4')).toBeVisible();
        }
      });

      test('should handle archive source selection on mobile', async ({ page }) => {
        await page.goto('/projects/create');

        // Complete basic info
        await page.fill('input[placeholder*="project name"]', 'Archive Source Test');
        await page.click('button:has-text("Next")');

        // Navigate to targets step and fill required data
        await page.waitForSelector('h2:has-text("Configure Your Targets")');
        await page.fill('input[placeholder="example.com"]', 'example.com');

        // Test archive source radio buttons
        const waybackRadio = page.locator('input[value="wayback"]');
        const commonCrawlRadio = page.locator('input[value="commoncrawl"]');
        const hybridRadio = page.locator('input[value="hybrid"]');

        // These should be clickable with proper touch targets
        await waybackRadio.click();
        await expect(waybackRadio).toBeChecked();

        await commonCrawlRadio.click();
        await expect(commonCrawlRadio).toBeChecked();

        await hybridRadio.click();
        await expect(hybridRadio).toBeChecked();

        // Verify hybrid options become visible
        const fallbackCheckbox = page.locator('input[type="checkbox"]:near(text="Enable automatic fallback")');
        if (await fallbackCheckbox.count() > 0) {
          await expect(fallbackCheckbox).toBeVisible();
        }
      });

      test('should handle date range inputs correctly', async ({ page }) => {
        await page.goto('/projects/create');

        // Navigate to targets configuration
        await page.fill('input[placeholder*="project name"]', 'Date Range Test');
        await page.click('button:has-text("Next")');
        
        await page.waitForSelector('h2:has-text("Configure Your Targets")');
        await page.fill('input[placeholder="example.com"]', 'example.com');

        // Test date inputs
        const fromDateInput = page.locator('input[type="date"]').first();
        const toDateInput = page.locator('input[type="date"]').last();

        // These should be properly sized for mobile interaction
        await verifyTouchTargetSize(page, 'input[type="date"]', 40);

        // Set date values
        await fromDateInput.fill('2024-01-01');
        await toDateInput.fill('2024-12-31');

        // Values should be set correctly
        await expect(fromDateInput).toHaveValue('2024-01-01');
        await expect(toDateInput).toHaveValue('2024-12-31');
      });
    });
  });

  test.describe('Portrait vs Landscape Orientation', () => {
    test('should work in both portrait and landscape on mobile devices', async ({ page }) => {
      await loginUser(page);

      // Test in portrait mode (414x896 - iPhone 12 Pro)
      await page.setViewportSize({ width: 414, height: 896 });
      await page.goto('/projects/create');
      
      await page.fill('input[placeholder*="project name"]', 'Orientation Test Portrait');
      await page.click('button:has-text("Next")');
      
      // Form should be usable in portrait
      await page.waitForSelector('h2:has-text("Configure Your Targets")');
      await page.fill('input[placeholder="example.com"]', 'portrait.com');

      // Switch to landscape mode (896x414)
      await page.setViewportSize({ width: 896, height: 414 });
      
      // Content should still be accessible
      await expect(page.locator('h2:has-text("Configure Your Targets")')).toBeVisible();
      
      // Form inputs should still work
      const targetValue = await page.locator('input[placeholder="example.com"]').inputValue();
      expect(targetValue).toBe('portrait.com');
      
      // Should be able to continue the flow
      await page.click('button:has-text("Next")');
      await page.waitForSelector('h2:has-text("Processing Options")');
    });
  });

  test.describe('Desktop Compatibility Verification', () => {
    test('should maintain desktop experience integrity', async ({ page }) => {
      // Test on desktop viewport to ensure mobile optimizations don't break desktop
      await page.setViewportSize({ width: 1280, height: 720 });
      await loginUser(page);
      await page.goto('/projects/create');

      // Desktop layout should use full width appropriately
      const formContainer = page.locator('.max-w-4xl');
      const formBox = await formContainer.boundingBox();
      
      // Form should be centered with appropriate max width
      expect(formBox?.width || 0).toBeLessThanOrEqual(896); // max-w-4xl = 896px
      expect(formBox?.x || 0).toBeGreaterThanOrEqual(100); // Should have significant margins

      // Complete the flow to ensure functionality is preserved
      await page.fill('input[placeholder*="project name"]', 'Desktop Test Project');
      await page.click('button:has-text("Next")');
      
      await page.waitForSelector('h2:has-text("Configure Your Targets")');
      await page.fill('input[placeholder="example.com"]', 'desktop-test.com');
      await page.click('button:has-text("Next")');
      
      await page.waitForSelector('h2:has-text("Processing Options")');
      await page.click('button:has-text("Next")');
      
      await page.waitForSelector('h2:has-text("Review & Confirm")');
      
      // All elements should be properly displayed on desktop
      await expect(page.locator('text=Desktop Test Project')).toBeVisible();
      await expect(page.locator('text=desktop-test.com')).toBeVisible();
    });
  });

  test.describe('Content and Layout Overflow Checks', () => {
    test('should prevent content overflow on small screens', async ({ page }) => {
      // Test on the smallest viewport (320px width)
      await page.setViewportSize({ width: 320, height: 568 });
      await loginUser(page);
      await page.goto('/projects/create');

      // Check that no elements cause horizontal scrolling
      const bodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
      const bodyClientWidth = await page.evaluate(() => document.body.clientWidth);
      
      expect(bodyScrollWidth).toBeLessThanOrEqual(bodyClientWidth + 1); // Allow 1px tolerance

      // Check specific containers
      const containers = [
        '.max-w-4xl',
        '[class*="card"]',
        '[class*="form"]'
      ];

      for (const selector of containers) {
        const elements = page.locator(selector);
        const count = await elements.count();
        
        for (let i = 0; i < count; i++) {
          const element = elements.nth(i);
          if (await element.isVisible()) {
            const box = await element.boundingBox();
            expect((box?.x || 0) + (box?.width || 0)).toBeLessThanOrEqual(320);
          }
        }
      }
    });

    test('should handle long text content properly', async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 667 });
      await loginUser(page);
      await page.goto('/projects/create');

      // Fill with very long text
      const longProjectName = 'This is a very long project name that should wrap properly and not cause horizontal overflow issues on mobile devices with small screens';
      const longDescription = 'This is an extremely long project description that contains multiple sentences and should demonstrate how the text wraps and handles line breaks properly on mobile devices. It should not cause any horizontal scrolling or layout issues when displayed in the project creation form interface.';

      await page.fill('input[placeholder*="project name"]', longProjectName);
      await page.fill('textarea[placeholder*="description"]', longDescription);

      // Text should wrap properly without causing overflow
      const { hasHorizontalOverflow } = await checkForOverflow(page, 'body');
      expect(hasHorizontalOverflow).toBeFalsy();

      // Continue through the flow
      await page.click('button:has-text("Next")');
      await page.waitForSelector('h2:has-text("Configure Your Targets")');
      
      // Add a very long domain name
      await page.fill('input[placeholder="example.com"]', 'this-is-a-very-long-domain-name-that-might-cause-layout-issues.example.com');
      
      // Should still not overflow
      const targetOverflow = await checkForOverflow(page, 'body');
      expect(targetOverflow.hasHorizontalOverflow).toBeFalsy();
    });
  });
});
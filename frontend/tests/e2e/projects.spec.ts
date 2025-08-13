/**
 * End-to-end tests for project management flows
 */
import { test, expect } from '@playwright/test';

// Helper function to login before each test
async function loginUser(page: any) {
  await page.goto('/auth/login');
  await page.fill('[data-testid="email-input"]', 'test@example.com');
  await page.fill('[data-testid="password-input"]', 'testpassword123');
  await page.click('[data-testid="login-button"]');
  await expect(page).toHaveURL('/dashboard');
}

test.describe('Project Management', () => {
  test.beforeEach(async ({ page }) => {
    await loginUser(page);
  });

  test.describe('Project Creation', () => {
    test('should allow user to create a new project', async ({ page }) => {
      // Navigate to projects page
      await page.click('[data-testid="nav-projects"]');
      await expect(page).toHaveURL('/projects');

      // Click create project button
      await page.click('[data-testid="create-project-button"]');
      
      // Fill project creation form
      await page.fill('[data-testid="project-name-input"]', 'Test Project');
      await page.fill('[data-testid="project-description-input"]', 'A test project for automation');
      
      // Add URLs
      await page.fill('[data-testid="url-input-0"]', 'https://example.com');
      await page.click('[data-testid="add-url-button"]');
      await page.fill('[data-testid="url-input-1"]', 'https://test.com');
      
      // Set schedule
      await page.selectOption('[data-testid="schedule-select"]', '0 */6 * * *');
      
      // Configure filters
      await page.fill('[data-testid="include-filters"]', 'article, blog');
      await page.fill('[data-testid="exclude-filters"]', 'advertisement, popup');
      
      // Submit form
      await page.click('[data-testid="create-project-submit"]');
      
      // Should show success message and redirect
      await expect(page.locator('[data-testid="success-message"]')).toBeVisible();
      await expect(page.locator('[data-testid="success-message"]')).toContainText('Project created successfully');
      
      // Should see the new project in the list
      await expect(page.locator('[data-testid="project-card"]')).toContainText('Test Project');
    });

    test('should validate required fields', async ({ page }) => {
      await page.click('[data-testid="nav-projects"]');
      await page.click('[data-testid="create-project-button"]');
      
      // Try to submit empty form
      await page.click('[data-testid="create-project-submit"]');
      
      // Should show validation errors
      await expect(page.locator('[data-testid="name-error"]')).toBeVisible();
      await expect(page.locator('[data-testid="name-error"]')).toContainText('Project name is required');
    });

    test('should validate URL format', async ({ page }) => {
      await page.click('[data-testid="nav-projects"]');
      await page.click('[data-testid="create-project-button"]');
      
      await page.fill('[data-testid="project-name-input"]', 'Invalid URL Project');
      await page.fill('[data-testid="url-input-0"]', 'not-a-valid-url');
      
      await page.click('[data-testid="create-project-submit"]');
      
      await expect(page.locator('[data-testid="url-error-0"]')).toBeVisible();
      await expect(page.locator('[data-testid="url-error-0"]')).toContainText('Invalid URL format');
    });
  });

  test.describe('Project List and Navigation', () => {
    test('should display list of user projects', async ({ page }) => {
      await page.click('[data-testid="nav-projects"]');
      
      // Should see projects list
      await expect(page.locator('[data-testid="projects-container"]')).toBeVisible();
      
      // Should have at least one project (from setup)
      await expect(page.locator('[data-testid="project-card"]')).toHaveCount.greaterThan(0);
    });

    test('should allow filtering projects by name', async ({ page }) => {
      await page.click('[data-testid="nav-projects"]');
      
      // Use search filter
      await page.fill('[data-testid="project-search"]', 'Test');
      
      // Should filter projects
      const projectCards = page.locator('[data-testid="project-card"]');
      await expect(projectCards).toHaveCount.greaterThanOrEqual(0);
      
      // Each visible project should contain "Test"
      const count = await projectCards.count();
      for (let i = 0; i < count; i++) {
        await expect(projectCards.nth(i)).toContainText('Test');
      }
    });

    test('should allow sorting projects', async ({ page }) => {
      await page.click('[data-testid="nav-projects"]');
      
      // Change sort order
      await page.selectOption('[data-testid="sort-select"]', 'name-asc');
      
      // Verify projects are sorted alphabetically
      const projectNames = await page.locator('[data-testid="project-name"]').allTextContents();
      const sortedNames = [...projectNames].sort();
      expect(projectNames).toEqual(sortedNames);
    });
  });

  test.describe('Project Details and Configuration', () => {
    test('should display project details', async ({ page }) => {
      await page.click('[data-testid="nav-projects"]');
      
      // Click on first project
      await page.click('[data-testid="project-card"]').first();
      
      // Should navigate to project details
      await expect(page).toHaveURL(/\/projects\/\d+/);
      
      // Should display project information
      await expect(page.locator('[data-testid="project-title"]')).toBeVisible();
      await expect(page.locator('[data-testid="project-description"]')).toBeVisible();
      await expect(page.locator('[data-testid="project-status"]')).toBeVisible();
    });

    test('should allow editing project configuration', async ({ page }) => {
      await page.click('[data-testid="nav-projects"]');
      await page.click('[data-testid="project-card"]').first();
      
      // Click edit button
      await page.click('[data-testid="edit-project-button"]');
      
      // Should show edit form
      await expect(page.locator('[data-testid="edit-project-form"]')).toBeVisible();
      
      // Modify project name
      await page.fill('[data-testid="project-name-input"]', 'Updated Project Name');
      
      // Add new URL
      await page.click('[data-testid="add-url-button"]');
      const urlInputs = page.locator('[data-testid*="url-input"]');
      const newUrlIndex = await urlInputs.count() - 1;
      await page.fill(`[data-testid="url-input-${newUrlIndex}"]`, 'https://newsite.com');
      
      // Update schedule
      await page.selectOption('[data-testid="schedule-select"]', '0 */12 * * *');
      
      // Save changes
      await page.click('[data-testid="save-project-button"]');
      
      // Should show success message
      await expect(page.locator('[data-testid="success-message"]')).toBeVisible();
      
      // Should display updated information
      await expect(page.locator('[data-testid="project-title"]')).toContainText('Updated Project Name');
    });

    test('should allow deleting URLs from project', async ({ page }) => {
      await page.click('[data-testid="nav-projects"]');
      await page.click('[data-testid="project-card"]').first();
      await page.click('[data-testid="edit-project-button"]');
      
      // Count initial URLs
      const initialUrlCount = await page.locator('[data-testid*="url-input"]').count();
      
      // Delete first URL
      await page.click('[data-testid="delete-url-0"]');
      
      // Should have one less URL
      const newUrlCount = await page.locator('[data-testid*="url-input"]').count();
      expect(newUrlCount).toBe(initialUrlCount - 1);
    });
  });

  test.describe('Project Execution', () => {
    test('should allow starting project execution', async ({ page }) => {
      await page.click('[data-testid="nav-projects"]');
      await page.click('[data-testid="project-card"]').first();
      
      // Start execution
      await page.click('[data-testid="start-execution-button"]');
      
      // Should show confirmation dialog
      await expect(page.locator('[data-testid="confirm-dialog"]')).toBeVisible();
      await page.click('[data-testid="confirm-start-button"]');
      
      // Should show execution started message
      await expect(page.locator('[data-testid="execution-status"]')).toContainText('Running');
      
      // Start button should be disabled, stop button should be visible
      await expect(page.locator('[data-testid="start-execution-button"]')).toBeDisabled();
      await expect(page.locator('[data-testid="stop-execution-button"]')).toBeVisible();
    });

    test('should display execution progress', async ({ page }) => {
      await page.click('[data-testid="nav-projects"]');
      await page.click('[data-testid="project-card"]').first();
      
      // Start execution
      await page.click('[data-testid="start-execution-button"]');
      await page.click('[data-testid="confirm-start-button"]');
      
      // Should display progress information
      await expect(page.locator('[data-testid="progress-bar"]')).toBeVisible();
      await expect(page.locator('[data-testid="progress-text"]')).toBeVisible();
      
      // Should show current step
      await expect(page.locator('[data-testid="current-step"]')).toBeVisible();
    });

    test('should allow stopping project execution', async ({ page }) => {
      await page.click('[data-testid="nav-projects"]');
      await page.click('[data-testid="project-card"]').first();
      
      // Start execution first
      await page.click('[data-testid="start-execution-button"]');
      await page.click('[data-testid="confirm-start-button"]');
      
      // Wait for execution to start
      await expect(page.locator('[data-testid="execution-status"]')).toContainText('Running');
      
      // Stop execution
      await page.click('[data-testid="stop-execution-button"]');
      await page.click('[data-testid="confirm-stop-button"]');
      
      // Should show stopped status
      await expect(page.locator('[data-testid="execution-status"]')).toContainText('Stopped');
    });
  });

  test.describe('Project Results', () => {
    test('should display execution results', async ({ page }) => {
      await page.click('[data-testid="nav-projects"]');
      await page.click('[data-testid="project-card"]').first();
      
      // Navigate to results tab
      await page.click('[data-testid="results-tab"]');
      
      // Should display results container
      await expect(page.locator('[data-testid="results-container"]')).toBeVisible();
      
      // Should show summary statistics
      await expect(page.locator('[data-testid="total-pages"]')).toBeVisible();
      await expect(page.locator('[data-testid="successful-extractions"]')).toBeVisible();
      await expect(page.locator('[data-testid="failed-extractions"]')).toBeVisible();
    });

    test('should allow filtering results', async ({ page }) => {
      await page.click('[data-testid="nav-projects"]');
      await page.click('[data-testid="project-card"]').first();
      await page.click('[data-testid="results-tab"]');
      
      // Apply date filter
      await page.fill('[data-testid="date-from"]', '2024-01-01');
      await page.fill('[data-testid="date-to"]', '2024-12-31');
      
      // Apply status filter
      await page.selectOption('[data-testid="status-filter"]', 'success');
      
      // Apply filters
      await page.click('[data-testid="apply-filters-button"]');
      
      // Should update results display
      await expect(page.locator('[data-testid="results-list"]')).toBeVisible();
    });

    test('should allow exporting results', async ({ page }) => {
      await page.click('[data-testid="nav-projects"]');
      await page.click('[data-testid="project-card"]').first();
      await page.click('[data-testid="results-tab"]');
      
      // Set up download promise
      const downloadPromise = page.waitForEvent('download');
      
      // Click export button
      await page.click('[data-testid="export-results-button"]');
      
      // Select export format
      await page.selectOption('[data-testid="export-format"]', 'json');
      await page.click('[data-testid="confirm-export-button"]');
      
      // Should trigger download
      const download = await downloadPromise;
      expect(download.suggestedFilename()).toMatch(/results.*\.json$/);
    });
  });

  test.describe('Project Deletion', () => {
    test('should allow deleting a project', async ({ page }) => {
      await page.click('[data-testid="nav-projects"]');
      
      // Count initial projects
      const initialCount = await page.locator('[data-testid="project-card"]').count();
      
      // Click on first project
      await page.click('[data-testid="project-card"]').first();
      
      // Delete project
      await page.click('[data-testid="delete-project-button"]');
      
      // Should show confirmation dialog
      await expect(page.locator('[data-testid="delete-confirm-dialog"]')).toBeVisible();
      
      // Type project name to confirm
      const projectName = await page.locator('[data-testid="project-title"]').textContent();
      await page.fill('[data-testid="delete-confirm-input"]', projectName || '');
      
      // Confirm deletion
      await page.click('[data-testid="confirm-delete-button"]');
      
      // Should redirect to projects list
      await expect(page).toHaveURL('/projects');
      
      // Should show success message
      await expect(page.locator('[data-testid="success-message"]')).toContainText('Project deleted');
      
      // Should have one less project
      const newCount = await page.locator('[data-testid="project-card"]').count();
      expect(newCount).toBe(initialCount - 1);
    });

    test('should prevent deletion without confirmation', async ({ page }) => {
      await page.click('[data-testid="nav-projects"]');
      await page.click('[data-testid="project-card"]').first();
      
      await page.click('[data-testid="delete-project-button"]');
      
      // Try to confirm without typing project name
      await page.click('[data-testid="confirm-delete-button"]');
      
      // Should show error message
      await expect(page.locator('[data-testid="delete-error"]')).toBeVisible();
      await expect(page.locator('[data-testid="delete-error"]')).toContainText('Please type the project name');
      
      // Dialog should still be open
      await expect(page.locator('[data-testid="delete-confirm-dialog"]')).toBeVisible();
    });
  });

  test.describe('Responsive Design', () => {
    test('should work on mobile devices', async ({ page }) => {
      // Set mobile viewport
      await page.setViewportSize({ width: 375, height: 667 });
      
      await page.click('[data-testid="nav-projects"]');
      
      // Should show mobile navigation
      await expect(page.locator('[data-testid="mobile-nav"]')).toBeVisible();
      
      // Projects should stack vertically
      const projectCards = page.locator('[data-testid="project-card"]');
      const count = await projectCards.count();
      
      if (count > 1) {
        const firstCard = projectCards.first();
        const secondCard = projectCards.nth(1);
        
        const firstBox = await firstCard.boundingBox();
        const secondBox = await secondCard.boundingBox();
        
        // Second card should be below first card (not side by side)
        expect(secondBox?.y || 0).toBeGreaterThan((firstBox?.y || 0) + (firstBox?.height || 0));
      }
    });

    test('should adapt create project form for mobile', async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 667 });
      
      await page.click('[data-testid="nav-projects"]');
      await page.click('[data-testid="create-project-button"]');
      
      // Form should be full width on mobile
      const form = page.locator('[data-testid="create-project-form"]');
      const formBox = await form.boundingBox();
      
      expect(formBox?.width || 0).toBeGreaterThan(300); // Most of the screen width
    });
  });
});
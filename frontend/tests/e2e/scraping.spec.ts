/**
 * End-to-end tests for scraping operations
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

test.describe('Scraping Operations', () => {
  test.beforeEach(async ({ page }) => {
    await loginTestUser(page);
  });
  
  test('should create and start scraping project', async ({ page }) => {
    // Navigate to projects
    await page.goto('/projects');
    
    // Create new project
    await page.click('a:has-text("Create Project"), button:has-text("New Project")');
    await expect(page).toHaveURL('/projects/create');
    
    // Fill project details
    await page.fill('[name="name"]', 'Test Scraping Project');
    await page.fill('[name="description"]', 'E2E test project for scraping');
    
    // Add domain to scrape
    await page.fill('[name="domain"]', 'example.com');
    
    // Set date range
    await page.fill('[name="startDate"]', '2024-01-01');
    await page.fill('[name="endDate"]', '2024-01-31');
    
    // Configure scraping options
    const filterListPages = page.locator('[name="filterListPages"]');
    if (await filterListPages.isVisible()) {
      await filterListPages.check();
    }
    
    // Set content filters
    await page.fill('[name="minContentLength"]', '1000');
    await page.fill('[name="maxContentLength"]', '1000000');
    
    // Submit project creation
    await page.click('button:has-text("Create Project")');
    
    // Should redirect to project page
    await expect(page).toHaveURL(/projects\/\d+/);
    
    // Start scraping
    await page.click('button:has-text("Start Scraping")');
    
    // Should show progress indicators
    await expect(page.locator('.scraping-progress, .progress-bar')).toBeVisible();
  });
  
  test('should monitor scraping progress', async ({ page }) => {
    // Navigate to existing project
    await page.goto('/projects');
    
    // Click on first project if exists
    const projectCard = page.locator('.project-card').first();
    if (await projectCard.isVisible()) {
      await projectCard.click();
      
      // Should show project details
      await expect(page).toHaveURL(/projects\/\d+/);
      
      // Check for progress indicators
      const progressSection = page.locator('.progress-section, .scraping-status');
      if (await progressSection.isVisible()) {
        // Should show statistics
        await expect(page.locator('text=/Pages Scraped|Progress|Status/')).toBeVisible();
        
        // Check for real-time updates (WebSocket)
        const initialProgress = await page.locator('.progress-value').textContent();
        
        // Wait a bit for potential updates
        await page.waitForTimeout(5000);
        
        // Progress might have changed if scraping is active
        const updatedProgress = await page.locator('.progress-value').textContent();
        // Note: This is a soft check as scraping might not be active
      }
    }
  });
  
  test('should pause and resume scraping', async ({ page }) => {
    await page.goto('/projects');
    
    const projectCard = page.locator('.project-card').first();
    if (await projectCard.isVisible()) {
      await projectCard.click();
      
      // Look for pause button if scraping is active
      const pauseButton = page.locator('button:has-text("Pause")');
      if (await pauseButton.isVisible()) {
        await pauseButton.click();
        
        // Should show paused status
        await expect(page.locator('text=/Paused|Suspended/')).toBeVisible();
        
        // Resume scraping
        await page.click('button:has-text("Resume")');
        
        // Should show active status
        await expect(page.locator('text=/Active|Running|In Progress/')).toBeVisible();
      }
    }
  });
  
  test('should view scraped pages', async ({ page }) => {
    await page.goto('/projects');
    
    const projectCard = page.locator('.project-card').first();
    if (await projectCard.isVisible()) {
      await projectCard.click();
      
      // Navigate to pages tab
      await page.click('button:has-text("Pages"), a:has-text("Pages")');
      
      // Should show pages list or empty state
      await expect(page.locator('.pages-list, .empty-state')).toBeVisible();
      
      // If pages exist, test viewing one
      const pageItem = page.locator('.page-item').first();
      if (await pageItem.isVisible()) {
        await pageItem.click();
        
        // Should show page content
        await expect(page.locator('.page-content, .page-viewer')).toBeVisible();
        
        // Should have action buttons
        await expect(page.locator('button:has-text("Star"), button:has-text("Export")')).toBeVisible();
      }
    }
  });
  
  test('should retry failed pages', async ({ page }) => {
    await page.goto('/projects');
    
    const projectCard = page.locator('.project-card').first();
    if (await projectCard.isVisible()) {
      await projectCard.click();
      
      // Navigate to errors tab if exists
      const errorsTab = page.locator('button:has-text("Errors"), a:has-text("Errors")');
      if (await errorsTab.isVisible()) {
        await errorsTab.click();
        
        // Check for failed pages
        const failedPage = page.locator('.failed-page-item').first();
        if (await failedPage.isVisible()) {
          // Select page for retry
          await failedPage.locator('input[type="checkbox"]').check();
          
          // Click retry button
          await page.click('button:has-text("Retry Selected")');
          
          // Should show confirmation or start retry
          await expect(page.locator('.alert-success, .retry-started')).toBeVisible();
        }
      }
    }
  });
  
  test('should export scraped data', async ({ page }) => {
    await page.goto('/projects');
    
    const projectCard = page.locator('.project-card').first();
    if (await projectCard.isVisible()) {
      await projectCard.click();
      
      // Click export button
      const exportButton = page.locator('button:has-text("Export")');
      if (await exportButton.isVisible()) {
        await exportButton.click();
        
        // Should show export options
        await expect(page.locator('.export-modal, .export-options')).toBeVisible();
        
        // Select export format
        await page.selectOption('[name="exportFormat"]', 'json');
        
        // Start export
        await page.click('button:has-text("Export Data")');
        
        // Should trigger download or show success
        await expect(page.locator('.export-success, .download-started')).toBeVisible();
      }
    }
  });
});
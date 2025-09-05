/**
 * E2E tests for archive source fix - complete user flow testing
 * 
 * Tests the entire project creation flow with different archive sources
 * to ensure the enum mismatch has been resolved and proper display works.
 */
import { test, expect } from '@playwright/test';

// Test configuration
const TEST_PROJECT_PREFIX = 'Archive Test';
const BACKEND_URL = 'http://localhost:8000';

// Helper functions
async function loginUser(page: any) {
  await page.goto('http://localhost:5173/auth/login');
  await page.fill('input[name="email"]', 'playwright@test.com');
  await page.fill('input[name="password"]', 'TestPassword123!');
  await page.click('button[type="submit"]');
  await page.waitForURL('http://localhost:5173/dashboard');
}

async function cleanupTestProjects(page: any) {
  // Navigate to projects page
  await page.goto('http://localhost:5173/projects');
  await page.waitForLoadState('networkidle');
  
  // Delete any existing test projects
  const testProjectItems = await page.locator(`[data-testid="project-item"]:has-text("${TEST_PROJECT_PREFIX}")`).all();
  
  for (const item of testProjectItems) {
    try {
      // Click the project menu button (three dots)
      const menuButton = item.locator('[data-testid="project-menu-button"]');
      await menuButton.click();
      
      // Click delete option
      const deleteButton = page.locator('[data-testid="delete-project"]');
      await deleteButton.click();
      
      // Confirm deletion
      const confirmButton = page.locator('button:has-text("Delete")').last();
      await confirmButton.click();
      
      // Wait for deletion to complete
      await page.waitForTimeout(1000);
    } catch (error) {
      console.log('Could not delete test project:', error);
    }
  }
}

test.describe('Archive Source Fix Tests', () => {
  test.beforeEach(async ({ page }) => {
    await loginUser(page);
    await cleanupTestProjects(page);
  });

  test.afterEach(async ({ page }) => {
    await cleanupTestProjects(page);
  });

  test('Create project with Common Crawl archive source', async ({ page }) => {
    // Navigate to project creation
    await page.goto('http://localhost:5173/projects/create');
    await page.waitForLoadState('networkidle');

    // Fill in basic project details
    await page.fill('input[name="projectName"]', `${TEST_PROJECT_PREFIX} Common Crawl`);
    await page.fill('textarea[name="description"]', 'Testing Common Crawl archive source');
    
    // Add a target domain
    await page.fill('input[placeholder*="example.com"]', 'example.com');
    await page.click('button:has-text("Add Target")');
    
    // Navigate to archive configuration step
    await page.click('button:has-text("Next")');
    await page.waitForTimeout(500);
    
    // Select Common Crawl as archive source
    const commonCrawlOption = page.locator('[data-testid="archive-source-commoncrawl"]');
    await expect(commonCrawlOption).toBeVisible();
    await commonCrawlOption.click();
    
    // Verify Common Crawl is selected
    await expect(commonCrawlOption).toHaveClass(/selected|active/);
    
    // Continue to review step
    await page.click('button:has-text("Next")');
    await page.waitForTimeout(500);
    
    // Verify archive source is shown correctly in review
    const reviewArchiveSource = page.locator('[data-testid="review-archive-source"]');
    await expect(reviewArchiveSource).toContainText('Common Crawl');
    
    // Create the project
    await page.click('button:has-text("Create Project")');
    await page.waitForURL(/\/projects\/\d+/);
    
    // Verify project was created successfully
    await expect(page.locator('h1')).toContainText(`${TEST_PROJECT_PREFIX} Common Crawl`);
    
    // Verify archive source badge displays correctly
    const archiveSourceBadge = page.locator('[data-testid="archive-source-badge"]');
    await expect(archiveSourceBadge).toBeVisible();
    await expect(archiveSourceBadge).toContainText('Common Crawl');
    
    // Verify badge has correct styling for Common Crawl
    await expect(archiveSourceBadge).toHaveClass(/green|emerald/);
  });

  test('Create project with Wayback Machine archive source', async ({ page }) => {
    // Navigate to project creation
    await page.goto('http://localhost:5173/projects/create');
    await page.waitForLoadState('networkidle');

    // Fill in basic project details
    await page.fill('input[name="projectName"]', `${TEST_PROJECT_PREFIX} Wayback Machine`);
    await page.fill('textarea[name="description"]', 'Testing Wayback Machine archive source');
    
    // Add a target domain
    await page.fill('input[placeholder*="example.com"]', 'test.com');
    await page.click('button:has-text("Add Target")');
    
    // Navigate to archive configuration step
    await page.click('button:has-text("Next")');
    await page.waitForTimeout(500);
    
    // Select Wayback Machine as archive source (should be default)
    const waybackOption = page.locator('[data-testid="archive-source-wayback"]');
    await expect(waybackOption).toBeVisible();
    await waybackOption.click();
    
    // Verify Wayback Machine is selected
    await expect(waybackOption).toHaveClass(/selected|active/);
    
    // Continue to review step
    await page.click('button:has-text("Next")');
    await page.waitForTimeout(500);
    
    // Verify archive source is shown correctly in review
    const reviewArchiveSource = page.locator('[data-testid="review-archive-source"]');
    await expect(reviewArchiveSource).toContainText('Wayback Machine');
    
    // Create the project
    await page.click('button:has-text("Create Project")');
    await page.waitForURL(/\/projects\/\d+/);
    
    // Verify project was created successfully
    await expect(page.locator('h1')).toContainText(`${TEST_PROJECT_PREFIX} Wayback Machine`);
    
    // Verify archive source badge displays correctly
    const archiveSourceBadge = page.locator('[data-testid="archive-source-badge"]');
    await expect(archiveSourceBadge).toBeVisible();
    await expect(archiveSourceBadge).toContainText('Wayback');
    
    // Verify badge has correct styling for Wayback Machine
    await expect(archiveSourceBadge).toHaveClass(/blue/);
  });

  test('Create project with Hybrid archive source', async ({ page }) => {
    // Navigate to project creation
    await page.goto('http://localhost:5173/projects/create');
    await page.waitForLoadState('networkidle');

    // Fill in basic project details
    await page.fill('input[name="projectName"]', `${TEST_PROJECT_PREFIX} Hybrid Mode`);
    await page.fill('textarea[name="description"]', 'Testing Hybrid archive source');
    
    // Add a target domain
    await page.fill('input[placeholder*="example.com"]', 'hybrid-test.com');
    await page.click('button:has-text("Add Target")');
    
    // Navigate to archive configuration step
    await page.click('button:has-text("Next")');
    await page.waitForTimeout(500);
    
    // Select Hybrid as archive source
    const hybridOption = page.locator('[data-testid="archive-source-hybrid"]');
    await expect(hybridOption).toBeVisible();
    await hybridOption.click();
    
    // Verify Hybrid is selected
    await expect(hybridOption).toHaveClass(/selected|active/);
    
    // Enable fallback and configure advanced settings
    const fallbackToggle = page.locator('input[name="fallback_enabled"]');
    if (!(await fallbackToggle.isChecked())) {
      await fallbackToggle.click();
    }
    
    // Continue to review step
    await page.click('button:has-text("Next")');
    await page.waitForTimeout(500);
    
    // Verify archive source is shown correctly in review
    const reviewArchiveSource = page.locator('[data-testid="review-archive-source"]');
    await expect(reviewArchiveSource).toContainText('Hybrid');
    
    // Create the project
    await page.click('button:has-text("Create Project")');
    await page.waitForURL(/\/projects\/\d+/);
    
    // Verify project was created successfully
    await expect(page.locator('h1')).toContainText(`${TEST_PROJECT_PREFIX} Hybrid Mode`);
    
    // Verify archive source badge displays correctly
    const archiveSourceBadge = page.locator('[data-testid="archive-source-badge"]');
    await expect(archiveSourceBadge).toBeVisible();
    await expect(archiveSourceBadge).toContainText('Hybrid');
    
    // Verify badge has correct styling for Hybrid mode
    await expect(archiveSourceBadge).toHaveClass(/purple/);
    
    // Verify fallback indicator is shown
    const fallbackIndicator = page.locator('[data-testid="fallback-indicator"]');
    await expect(fallbackIndicator).toBeVisible();
  });

  test('Verify database persistence of archive source', async ({ page, request }) => {
    // Create a project with Common Crawl
    await page.goto('http://localhost:5173/projects/create');
    await page.waitForLoadState('networkidle');

    await page.fill('input[name="projectName"]', `${TEST_PROJECT_PREFIX} DB Test`);
    await page.fill('textarea[name="description"]', 'Testing database persistence');
    
    await page.fill('input[placeholder*="example.com"]', 'dbtest.com');
    await page.click('button:has-text("Add Target")');
    
    await page.click('button:has-text("Next")');
    await page.waitForTimeout(500);
    
    // Select Common Crawl
    await page.click('[data-testid="archive-source-commoncrawl"]');
    
    await page.click('button:has-text("Next")');
    await page.waitForTimeout(500);
    
    await page.click('button:has-text("Create Project")');
    await page.waitForURL(/\/projects\/(\d+)/);
    
    // Extract project ID from URL
    const url = page.url();
    const projectId = url.match(/\/projects\/(\d+)/)?.[1];
    expect(projectId).toBeTruthy();

    // Verify via API that archive_source is stored correctly
    const authCookie = await page.context().cookies();
    const response = await request.get(`${BACKEND_URL}/api/v1/projects/${projectId}`, {
      headers: {
        'Cookie': authCookie.map(c => `${c.name}=${c.value}`).join('; ')
      }
    });
    
    expect(response.ok()).toBeTruthy();
    const projectData = await response.json();
    
    // Verify archive_source is "commoncrawl" in the database
    expect(projectData.archive_source).toBe('commoncrawl');
    expect(projectData.name).toBe(`${TEST_PROJECT_PREFIX} DB Test`);
  });

  test('Test archive source display on projects list', async ({ page }) => {
    // Create projects with different archive sources
    const archiveSources = [
      { testId: 'archive-source-wayback', name: 'Wayback Test', expectedBadge: 'Wayback' },
      { testId: 'archive-source-commoncrawl', name: 'Common Crawl Test', expectedBadge: 'Common Crawl' },
      { testId: 'archive-source-hybrid', name: 'Hybrid Test', expectedBadge: 'Hybrid' }
    ];

    // Create each project
    for (const source of archiveSources) {
      await page.goto('http://localhost:5173/projects/create');
      await page.waitForLoadState('networkidle');

      await page.fill('input[name="projectName"]', `${TEST_PROJECT_PREFIX} ${source.name}`);
      await page.fill('textarea[name="description"]', `Testing ${source.name}`);
      
      await page.fill('input[placeholder*="example.com"]', `${source.name.toLowerCase().replace(/\s+/g, '')}.com`);
      await page.click('button:has-text("Add Target")');
      
      await page.click('button:has-text("Next")');
      await page.waitForTimeout(500);
      
      await page.click(`[data-testid="${source.testId}"]`);
      
      await page.click('button:has-text("Next")');
      await page.waitForTimeout(500);
      
      await page.click('button:has-text("Create Project")');
      await page.waitForURL(/\/projects\/\d+/);
    }

    // Navigate to projects list
    await page.goto('http://localhost:5173/projects');
    await page.waitForLoadState('networkidle');

    // Verify each project displays the correct archive source badge
    for (const source of archiveSources) {
      const projectCard = page.locator(`[data-testid="project-item"]:has-text("${TEST_PROJECT_PREFIX} ${source.name}")`);
      await expect(projectCard).toBeVisible();
      
      const badgeInCard = projectCard.locator('[data-testid="archive-source-badge"]');
      await expect(badgeInCard).toBeVisible();
      await expect(badgeInCard).toContainText(source.expectedBadge);
    }
  });

  test('Verify archive source configuration persistence after project update', async ({ page, request }) => {
    // Create project with Wayback Machine
    await page.goto('http://localhost:5173/projects/create');
    await page.waitForLoadState('networkidle');

    await page.fill('input[name="projectName"]', `${TEST_PROJECT_PREFIX} Update Test`);
    await page.fill('textarea[name="description"]', 'Testing update persistence');
    
    await page.fill('input[placeholder*="example.com"]', 'updatetest.com');
    await page.click('button:has-text("Add Target")');
    
    await page.click('button:has-text("Next")');
    await page.waitForTimeout(500);
    
    await page.click('[data-testid="archive-source-wayback"]');
    
    await page.click('button:has-text("Next")');
    await page.waitForTimeout(500);
    
    await page.click('button:has-text("Create Project")');
    await page.waitForURL(/\/projects\/(\d+)/);
    
    // Extract project ID
    const projectId = page.url().match(/\/projects\/(\d+)/)?.[1];
    
    // Navigate to project settings/edit page
    await page.click('[data-testid="project-settings-button"]');
    await page.waitForTimeout(500);
    
    // Verify current archive source is displayed correctly
    const currentArchiveSource = page.locator('[data-testid="current-archive-source"]');
    await expect(currentArchiveSource).toContainText('Wayback Machine');
    
    // Change to Common Crawl
    await page.click('[data-testid="edit-archive-source-button"]');
    await page.waitForTimeout(500);
    await page.click('[data-testid="archive-source-commoncrawl"]');
    await page.click('button:has-text("Save Changes")');
    await page.waitForTimeout(1000);
    
    // Verify the change is reflected in the UI
    await expect(currentArchiveSource).toContainText('Common Crawl');
    
    // Verify via API that the change persisted
    const authCookie = await page.context().cookies();
    const response = await request.get(`${BACKEND_URL}/api/v1/projects/${projectId}`, {
      headers: {
        'Cookie': authCookie.map(c => `${c.name}=${c.value}`).join('; ')
      }
    });
    
    const projectData = await response.json();
    expect(projectData.archive_source).toBe('commoncrawl');
  });
});
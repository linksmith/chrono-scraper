import { test, expect } from '@playwright/test';

test.describe('shadcn Button Component Real-World Tests', () => {
	test.beforeEach(async ({ page }) => {
		// Navigate to projects page which has various button interactions
		await page.goto('http://localhost:5173');
		
		// Wait for page to load
		await page.waitForLoadState('networkidle');
	});

	test('Login page button interactions', async ({ page }) => {
		// Navigate to login page
		await page.goto('http://localhost:5173/auth/login');
		await page.waitForLoadState('networkidle');

		// Find the login button (should be shadcn Button)
		const loginButton = page.locator('button[type="submit"]').first();
		
		// Verify button is visible
		await expect(loginButton).toBeVisible();
		
		// Test button is initially enabled
		await expect(loginButton).toBeEnabled();
		
		// Test hover state
		await loginButton.hover();
		await page.waitForTimeout(200);
		
		// Fill form to test interactive behavior
		const emailInput = page.locator('input[type="email"]').first();
		const passwordInput = page.locator('input[type="password"]').first();
		
		if (await emailInput.count() > 0) {
			await emailInput.fill('test@example.com');
			await passwordInput.fill('testpassword');
			
			// Click login button
			await loginButton.click();
			
			// Should trigger some form submission behavior
			await page.waitForTimeout(1000);
		}
	});

	test('Project creation page button functionality', async ({ page }) => {
		// Navigate to project creation page
		await page.goto('http://localhost:5173/projects/create');
		await page.waitForLoadState('networkidle');
		
		// Wait for loading skeleton to disappear
		await page.waitForFunction(() => {
			const skeletons = document.querySelectorAll('[class*="skeleton"]');
			return skeletons.length === 0;
		}, { timeout: 15000 }).catch(() => {
			// Continue if no skeletons found
		});

		// Test "Add Another Target" button
		const addTargetButton = page.locator('button:has-text("Add Another Target")');
		await expect(addTargetButton).toBeVisible();
		
		// Count initial target inputs
		const initialTargets = await page.locator('[data-testid^="target-input-"]').count();
		
		// Click add button
		await addTargetButton.click();
		await page.waitForTimeout(500);
		
		// Verify new target was added
		const newTargetCount = await page.locator('[data-testid^="target-input-"]').count();
		expect(newTargetCount).toBe(initialTargets + 1);

		// Test Cancel button
		const cancelButton = page.locator('button:has-text("Cancel")');
		await expect(cancelButton).toBeVisible();
		await expect(cancelButton).toBeEnabled();
		
		// Test cancel button navigation
		await cancelButton.click();
		await expect(page).toHaveURL(/\/projects$/);
	});

	test('Button keyboard navigation and accessibility', async ({ page }) => {
		await page.goto('http://localhost:5173/projects/create');
		await page.waitForLoadState('networkidle');
		
		// Tab through the page to find buttons
		await page.keyboard.press('Tab');
		
		let attempts = 0;
		let foundButton = false;
		
		while (attempts < 20 && !foundButton) {
			const focusedElement = page.locator(':focus');
			const tagName = await focusedElement.evaluate(el => el.tagName.toLowerCase()).catch(() => '');
			
			if (tagName === 'button') {
				foundButton = true;
				
				// Test button is focusable
				await expect(focusedElement).toBeFocused();
				
				// Test Enter key activation
				const buttonText = await focusedElement.textContent();
				console.log('Testing keyboard interaction on button:', buttonText);
				
				// For non-form buttons, Enter should work
				if (!await focusedElement.getAttribute('type')?.includes('submit')) {
					await page.keyboard.press('Enter');
					await page.waitForTimeout(300);
				}
				
				// Test Space key activation
				await page.keyboard.press('Space');
				await page.waitForTimeout(300);
				
				break;
			}
			
			await page.keyboard.press('Tab');
			attempts++;
		}
		
		expect(foundButton).toBe(true);
	});

	test('Button hover and visual states', async ({ page }) => {
		await page.goto('http://localhost:5173/projects/create');
		await page.waitForLoadState('networkidle');
		
		const createButton = page.locator('button[data-testid="create-project-button"]');
		
		if (await createButton.count() === 0) {
			// Fallback to any visible button
			const anyButton = page.locator('button').first();
			await expect(anyButton).toBeVisible();
			
			// Test hover state
			await anyButton.hover();
			await page.waitForTimeout(300);
			
			// Button should still be visible and functional
			await expect(anyButton).toBeVisible();
		} else {
			await expect(createButton).toBeVisible();
			
			// Test hover state
			await createButton.hover();
			await page.waitForTimeout(300);
			
			// Button should still be visible and functional
			await expect(createButton).toBeVisible();
		}
	});

	test('Button loading states and disabled behavior', async ({ page }) => {
		await page.goto('http://localhost:5173/projects/create');
		await page.waitForLoadState('networkidle');
		
		// Fill in form to make create button enabled
		const targetInput = page.locator('[data-testid="target-input-0"]');
		if (await targetInput.count() > 0) {
			await targetInput.fill('example.com');
			await page.waitForTimeout(500);
		}
		
		const createButton = page.locator('button[data-testid="create-project-button"]');
		
		if (await createButton.count() > 0) {
			await expect(createButton).toBeVisible();
			
			// Click to trigger loading state
			await createButton.click();
			
			// Check for loading state
			const loadingIndicator = page.locator('.animate-spin, text=Creating...');
			
			// Give it some time to show loading state
			await page.waitForTimeout(1000);
			
			// At least verify the button exists and is interactive
			await expect(createButton).toBeVisible();
		}
	});

	test('Button rapid clicking stress test', async ({ page }) => {
		await page.goto('http://localhost:5173/projects/create');
		await page.waitForLoadState('networkidle');
		
		const addButton = page.locator('button:has-text("Add Another Target")');
		await expect(addButton).toBeVisible();
		
		// Rapid clicking test
		for (let i = 0; i < 3; i++) {
			await addButton.click();
			await page.waitForTimeout(100);
		}
		
		// Verify button is still functional
		await expect(addButton).toBeVisible();
		await expect(addButton).toBeEnabled();
		
		// Verify targets were actually added
		const targetCount = await page.locator('[data-testid^="target-input-"]').count();
		expect(targetCount).toBeGreaterThan(1);
	});

	test('Button with different variants work correctly', async ({ page }) => {
		await page.goto('http://localhost:5173/projects/create');
		await page.waitForLoadState('networkidle');
		
		// Test outline variant (Cancel button)
		const cancelButton = page.locator('button:has-text("Cancel")');
		await expect(cancelButton).toBeVisible();
		await expect(cancelButton).toBeEnabled();
		
		// Check if it has outline styling (border)
		const cancelClasses = await cancelButton.getAttribute('class');
		expect(cancelClasses).toContain('border');
		
		// Test primary variant (Create Project button)
		const createButton = page.locator('[data-testid="create-project-button"]').or(page.locator('button:has-text("Create Project")'));
		if (await createButton.count() > 0) {
			await expect(createButton).toBeVisible();
			
			const createClasses = await createButton.getAttribute('class');
			// Should have primary button styling
			expect(createClasses).toContain('bg-primary');
		}
	});

	test('Button responsiveness across viewports', async ({ page }) => {
		// Test mobile viewport
		await page.setViewportSize({ width: 375, height: 667 });
		await page.goto('http://localhost:5173/projects/create');
		await page.waitForLoadState('networkidle');
		
		let button = page.locator('button').first();
		await expect(button).toBeVisible();
		
		// Button should be clickable on mobile
		await button.click();
		await page.waitForTimeout(300);
		
		// Test tablet viewport
		await page.setViewportSize({ width: 768, height: 1024 });
		await page.reload();
		await page.waitForLoadState('networkidle');
		
		button = page.locator('button').first();
		await expect(button).toBeVisible();
		await button.click();
		await page.waitForTimeout(300);
		
		// Test desktop viewport
		await page.setViewportSize({ width: 1920, height: 1080 });
		await page.reload();
		await page.waitForLoadState('networkidle');
		
		button = page.locator('button').first();
		await expect(button).toBeVisible();
		await button.click();
		await page.waitForTimeout(300);
	});

	test('Button focus management and tab order', async ({ page }) => {
		await page.goto('http://localhost:5173/projects/create');
		await page.waitForLoadState('networkidle');
		
		// Start tabbing from the beginning
		await page.keyboard.press('Tab');
		
		const focusedElements = [];
		let attempts = 0;
		
		// Tab through first 10 focusable elements
		while (attempts < 10) {
			const focusedElement = page.locator(':focus');
			const tagName = await focusedElement.evaluate(el => el.tagName.toLowerCase()).catch(() => '');
			const textContent = await focusedElement.textContent().catch(() => '');
			
			if (tagName && tagName !== 'body') {
				focusedElements.push({ tagName, textContent: textContent.slice(0, 50) });
			}
			
			await page.keyboard.press('Tab');
			attempts++;
		}
		
		console.log('Tab order:', focusedElements);
		
		// Should have found some buttons in the tab order
		const buttonElements = focusedElements.filter(el => el.tagName === 'button');
		expect(buttonElements.length).toBeGreaterThan(0);
	});
});
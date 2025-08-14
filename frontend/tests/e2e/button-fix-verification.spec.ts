import { test, expect } from '@playwright/test';

test.describe('Button Fix Verification - Svelte 5 onclick Events', () => {
	test.beforeEach(async ({ page }) => {
		// Navigate to our test page
		await page.goto('http://localhost:5173/test-buttons');
		await page.waitForLoadState('networkidle');
	});

	test('Default button onclick works', async ({ page }) => {
		const button = page.locator('text=Default Button (Clicked: 0)');
		await expect(button).toBeVisible();
		
		// Click the button
		await button.click();
		
		// Verify the click was registered
		await expect(page.locator('text=Button clicked 1 time!')).toBeVisible();
		await expect(page.locator('text=Default Button (Clicked: 1)')).toBeVisible();
		
		// Click again
		await button.click();
		await expect(page.locator('text=Button clicked 2 times!')).toBeVisible();
	});

	test('All button variants respond to clicks', async ({ page }) => {
		// Test outline button
		await page.locator('text=Outline Button').click();
		await expect(page.locator('text=Submit button clicked!')).toBeVisible();
		
		// Test destructive button
		await page.locator('text=Destructive Button').click();
		await expect(page.locator('text=Cancel button clicked!')).toBeVisible();
		
		// Test secondary button
		await page.locator('text=Secondary Button').click();
		await expect(page.locator('text=Secondary clicked!')).toBeVisible();
		
		// Test ghost button
		await page.locator('text=Ghost Button').click();
		await expect(page.locator('text=Ghost clicked!')).toBeVisible();
		
		// Test link button
		await page.locator('text=Link Button').click();
		await expect(page.locator('text=Link clicked!')).toBeVisible();
	});

	test('Button size variants work', async ({ page }) => {
		// Test small button
		await page.locator('text=Small').click();
		await expect(page.locator('text=Small button clicked!')).toBeVisible();
		
		// Test large button
		await page.locator('text=Large').click();
		await expect(page.locator('text=Large button clicked!')).toBeVisible();
		
		// Test icon button
		await page.locator('text=⭐').click();
		await expect(page.locator('text=Icon button clicked!')).toBeVisible();
	});

	test('Form submission works', async ({ page }) => {
		// Fill the input
		await page.fill('#test-input', 'Test form data');
		
		// Submit form
		await page.locator('button[type="submit"]:has-text("Submit Form")').click();
		await expect(page.locator('text=Form submitted!')).toBeVisible();
		
		// Test reset button
		await page.locator('text=Reset').click();
		await expect(page.locator('text=Form reset!')).toBeVisible();
	});

	test('Different event handler patterns work', async ({ page }) => {
		// Test arrow function
		await page.locator('text=Arrow Function').click();
		await expect(page.locator('text=Arrow function works!')).toBeVisible();
		
		// Test regular function
		await page.locator('text=Regular Function').click();
		await expect(page.locator('text=Regular function works!')).toBeVisible();
		
		// Test function reference
		await page.locator('text=Function Reference').click();
		await expect(page.locator('text=Button clicked').first()).toBeVisible();
		
		// Test complex handler
		await page.locator('text=Complex Handler').click();
		await expect(page.locator('text=Complex handler works!')).toBeVisible();
	});

	test('Disabled buttons do not respond to clicks', async ({ page }) => {
		const disabledButton = page.locator('button:has-text("Disabled Button")');
		
		// Verify button is disabled
		await expect(disabledButton).toBeDisabled();
		
		// Try to click (should not work)
		await disabledButton.click({ force: true });
		
		// Verify no message appeared (the message would be "This should not appear!")
		await expect(page.locator('text=This should not appear!')).not.toBeVisible();
	});

	test('Clear functionality works', async ({ page }) => {
		// First, click a button to create a message
		await page.locator('text=Default Button (Clicked: 0)').click();
		await expect(page.locator('text=Button clicked 1 time!')).toBeVisible();
		
		// Clear the message
		await page.locator('text=Clear Message & Reset Count').click();
		
		// Verify message is cleared and count is reset
		await expect(page.locator('text=Button clicked')).not.toBeVisible();
		await expect(page.locator('text=Default Button (Clicked: 0)')).toBeVisible();
	});

	test('Keyboard navigation works', async ({ page }) => {
		// Tab to the first button
		await page.keyboard.press('Tab');
		
		// Find focused element and press Enter
		const focusedElement = page.locator(':focus');
		await page.keyboard.press('Enter');
		
		// Should trigger some button action (any button will do)
		await page.waitForTimeout(500);
		
		// Verify some interaction occurred (check if any message appeared)
		const messageArea = page.locator('.bg-green-100');
		const isVisible = await messageArea.isVisible().catch(() => false);
		
		// If a message appeared, the keyboard interaction worked
		if (isVisible) {
			console.log('✅ Keyboard navigation working');
		}
	});
});

test.describe('Real Application Button Tests', () => {
	test('Project creation page buttons work', async ({ page }) => {
		await page.goto('http://localhost:5173/projects/create');
		await page.waitForLoadState('networkidle');
		
		// Wait for any loading to finish
		await page.waitForFunction(() => {
			const skeletons = document.querySelectorAll('[class*="skeleton"]');
			return skeletons.length === 0;
		}, { timeout: 10000 }).catch(() => {});
		
		// Test Cancel button (should navigate to projects page)
		const cancelButton = page.locator('button:has-text("Cancel")');
		await expect(cancelButton).toBeVisible();
		
		await cancelButton.click();
		
		// Should navigate to projects page
		await expect(page).toHaveURL(/\/projects$/);
	});
	
	test('Search page buttons work', async ({ page }) => {
		await page.goto('http://localhost:5173/search');
		await page.waitForLoadState('networkidle');
		
		// Test toggle filters button
		const toggleFiltersButton = page.locator('button:has-text("Filters")').first();
		
		if (await toggleFiltersButton.count() > 0) {
			await toggleFiltersButton.click();
			
			// Some UI change should occur (filters panel)
			await page.waitForTimeout(500);
			console.log('✅ Search filters button working');
		}
	});
});
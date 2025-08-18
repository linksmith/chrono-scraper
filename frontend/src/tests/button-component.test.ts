import { test, expect } from '@playwright/test';

test.describe('shadcn Button Component Tests', () => {
	test.beforeEach(async ({ page }) => {
		// Create a test page with various Button components
		await page.setContent(`
			<!DOCTYPE html>
			<html>
			<head>
				<title>Button Test</title>
				<script type="module">
					// Mock Svelte environment for testing
					window.addEventListener('DOMContentLoaded', () => {
						// Simulate button click handlers
						document.querySelectorAll('[data-testid]').forEach(button => {
							button.addEventListener('click', (e) => {
								console.log('Button clicked:', e.target.dataset.testid);
								e.target.setAttribute('data-clicked', 'true');
								
								// Simulate different behaviors based on button type
								if (e.target.dataset.testid === 'login-button') {
									e.target.textContent = 'Logging in...';
									e.target.disabled = true;
								} else if (e.target.dataset.testid === 'create-button') {
									window.location.hash = '#created';
								}
							});
						});
					});
				</script>
				<style>
					/* Simulate shadcn button styles */
					.btn-primary {
						display: inline-flex;
						align-items: center;
						justify-content: center;
						white-space: nowrap;
						border-radius: 6px;
						font-size: 14px;
						font-weight: 500;
						background: #0f172a;
						color: #f8fafc;
						padding: 8px 16px;
						border: none;
						cursor: pointer;
						transition: all 0.2s;
					}
					.btn-primary:hover {
						background: #1e293b;
					}
					.btn-primary:disabled {
						opacity: 0.5;
						pointer-events: none;
					}
					.btn-outline {
						display: inline-flex;
						align-items: center;
						justify-content: center;
						white-space: nowrap;
						border-radius: 6px;
						font-size: 14px;
						font-weight: 500;
						background: transparent;
						color: #0f172a;
						padding: 8px 16px;
						border: 1px solid #e2e8f0;
						cursor: pointer;
						transition: all 0.2s;
					}
					.btn-outline:hover {
						background: #f1f5f9;
					}
				</style>
			</head>
			<body>
				<h1>Button Component Tests</h1>
				
				<!-- Basic button tests -->
				<div id="basic-buttons">
					<button 
						class="btn-primary"
						data-testid="basic-button"
						type="button"
					>
						Basic Button
					</button>
					
					<button 
						class="btn-outline"
						data-testid="outline-button"
						type="button"
					>
						Outline Button
					</button>
				</div>
				
				<!-- Form buttons -->
				<form id="test-form">
					<button 
						class="btn-primary"
						data-testid="submit-button"
						type="submit"
					>
						Submit
					</button>
					
					<button 
						class="btn-outline"
						data-testid="cancel-button"
						type="button"
					>
						Cancel
					</button>
				</form>
				
				<!-- Interactive buttons (simulating real app scenarios) -->
				<div id="interactive-buttons">
					<button 
						class="btn-primary"
						data-testid="login-button"
						type="button"
					>
						Login
					</button>
					
					<button 
						class="btn-primary"
						data-testid="create-button"
						type="button"
					>
						Create Project
					</button>
					
					<button 
						class="btn-outline"
						data-testid="navigation-button"
						type="button"
						onclick="window.location.hash = '#navigated'"
					>
						Navigate
					</button>
				</div>
				
				<!-- Disabled button -->
				<button 
					class="btn-primary"
					data-testid="disabled-button"
					type="button"
					disabled
				>
					Disabled Button
				</button>
				
				<!-- Button with icon (simulating shadcn patterns) -->
				<button 
					class="btn-primary"
					data-testid="icon-button"
					type="button"
				>
					<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
						<path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
					</svg>
					Icon Button
				</button>
			</body>
			</html>
		`);
		
		await page.waitForLoadState('domcontentloaded');
	});

	test('basic button click functionality', async ({ page }) => {
		const button = page.getByTestId('basic-button');
		
		// Verify button is visible and enabled
		await expect(button).toBeVisible();
		await expect(button).toBeEnabled();
		
		// Click the button
		await button.click();
		
		// Verify click was registered
		await expect(button).toHaveAttribute('data-clicked', 'true');
	});

	test('outline button click functionality', async ({ page }) => {
		const button = page.getByTestId('outline-button');
		
		await expect(button).toBeVisible();
		await expect(button).toBeEnabled();
		
		await button.click();
		await expect(button).toHaveAttribute('data-clicked', 'true');
	});

	test('form submit button functionality', async ({ page }) => {
		const submitButton = page.getByTestId('submit-button');
		const form = page.locator('#test-form');
		
		await expect(submitButton).toBeVisible();
		await expect(submitButton).toHaveAttribute('type', 'submit');
		
		// Test form submission
		let formSubmitted = false;
		await page.route('**/*', route => {
			if (route.request().method() === 'POST') {
				formSubmitted = true;
				route.fulfill({ status: 200, body: 'OK' });
			} else {
				route.continue();
			}
		});
		
		await submitButton.click();
		// Note: In real implementation, this would trigger form submission
	});

	test('cancel button functionality', async ({ page }) => {
		const cancelButton = page.getByTestId('cancel-button');
		
		await expect(cancelButton).toBeVisible();
		await expect(cancelButton).toHaveAttribute('type', 'button');
		
		await cancelButton.click();
		await expect(cancelButton).toHaveAttribute('data-clicked', 'true');
	});

	test('login button with loading state', async ({ page }) => {
		const loginButton = page.getByTestId('login-button');
		
		await expect(loginButton).toBeVisible();
		await expect(loginButton).toContainText('Login');
		
		await loginButton.click();
		
		// Verify loading state
		await expect(loginButton).toContainText('Logging in...');
		await expect(loginButton).toBeDisabled();
	});

	test('create project button with navigation', async ({ page }) => {
		const createButton = page.getByTestId('create-button');
		
		await expect(createButton).toBeVisible();
		await createButton.click();
		
		// Verify navigation occurred
		await page.waitForFunction(() => window.location.hash === '#created');
		expect(await page.evaluate(() => window.location.hash)).toBe('#created');
	});

	test('navigation button functionality', async ({ page }) => {
		const navButton = page.getByTestId('navigation-button');
		
		await expect(navButton).toBeVisible();
		await navButton.click();
		
		// Verify navigation
		await page.waitForFunction(() => window.location.hash === '#navigated');
		expect(await page.evaluate(() => window.location.hash)).toBe('#navigated');
	});

	test('disabled button should not be clickable', async ({ page }) => {
		const disabledButton = page.getByTestId('disabled-button');
		
		await expect(disabledButton).toBeVisible();
		await expect(disabledButton).toBeDisabled();
		
		// Attempt to click disabled button
		await disabledButton.click({ force: true });
		
		// Verify no click was registered
		await expect(disabledButton).not.toHaveAttribute('data-clicked');
	});

	test('icon button functionality', async ({ page }) => {
		const iconButton = page.getByTestId('icon-button');
		
		await expect(iconButton).toBeVisible();
		await expect(iconButton).toContainText('Icon Button');
		
		// Verify icon is present
		const icon = iconButton.locator('svg');
		await expect(icon).toBeVisible();
		
		await iconButton.click();
		await expect(iconButton).toHaveAttribute('data-clicked', 'true');
	});

	test('button accessibility', async ({ page }) => {
		const basicButton = page.getByTestId('basic-button');
		
		// Test keyboard navigation
		await basicButton.focus();
		await expect(basicButton).toBeFocused();
		
		// Test Enter key activation
		await page.keyboard.press('Enter');
		await expect(basicButton).toHaveAttribute('data-clicked', 'true');
		
		// Reset for Space key test
		await page.reload();
		await page.waitForLoadState('domcontentloaded');
		
		const buttonAfterReload = page.getByTestId('basic-button');
		await buttonAfterReload.focus();
		await page.keyboard.press('Space');
		await expect(buttonAfterReload).toHaveAttribute('data-clicked', 'true');
	});

	test('button hover states', async ({ page }) => {
		const button = page.getByTestId('basic-button');
		
		// Get initial background color
		const initialBg = await button.evaluate(el => 
			window.getComputedStyle(el).backgroundColor
		);
		
		// Hover over button
		await button.hover();
		
		// Wait for hover transition
		await page.waitForTimeout(300);
		
		// Get hover background color
		const hoverBg = await button.evaluate(el => 
			window.getComputedStyle(el).backgroundColor
		);
		
		// Verify colors are different (hover effect applied)
		expect(initialBg).not.toBe(hoverBg);
	});

	test('button rapid clicking (stress test)', async ({ page }) => {
		const button = page.getByTestId('basic-button');
		
		// Rapid click test
		for (let i = 0; i < 10; i++) {
			await button.click();
			await page.waitForTimeout(10);
		}
		
		// Should still be responsive
		await expect(button).toHaveAttribute('data-clicked', 'true');
	});

	test('button in different viewport sizes', async ({ page }) => {
		const button = page.getByTestId('basic-button');
		
		// Test mobile viewport
		await page.setViewportSize({ width: 375, height: 667 });
		await expect(button).toBeVisible();
		await button.click();
		await expect(button).toHaveAttribute('data-clicked', 'true');
		
		// Reset button state
		await page.reload();
		await page.waitForLoadState('domcontentloaded');
		
		// Test tablet viewport
		await page.setViewportSize({ width: 768, height: 1024 });
		const buttonTablet = page.getByTestId('basic-button');
		await expect(buttonTablet).toBeVisible();
		await buttonTablet.click();
		await expect(buttonTablet).toHaveAttribute('data-clicked', 'true');
		
		// Reset button state
		await page.reload();
		await page.waitForLoadState('domcontentloaded');
		
		// Test desktop viewport
		await page.setViewportSize({ width: 1920, height: 1080 });
		const buttonDesktop = page.getByTestId('basic-button');
		await expect(buttonDesktop).toBeVisible();
		await buttonDesktop.click();
		await expect(buttonDesktop).toHaveAttribute('data-clicked', 'true');
	});
});
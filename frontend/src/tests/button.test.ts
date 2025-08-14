import { describe, it, expect, vi } from 'vitest';
import { buttonVariants } from '$lib/components/ui/button';

describe('shadcn Button Component Variants', () => {
	it('buttonVariants function generates correct classes for default variant', () => {
		const classes = buttonVariants();
		
		expect(classes).toContain('inline-flex');
		expect(classes).toContain('items-center');
		expect(classes).toContain('justify-center');
		expect(classes).toContain('whitespace-nowrap');
		expect(classes).toContain('rounded-md');
		expect(classes).toContain('text-sm');
		expect(classes).toContain('font-medium');
		expect(classes).toContain('bg-primary');
		expect(classes).toContain('text-primary-foreground');
		expect(classes).toContain('hover:bg-primary/90');
		expect(classes).toContain('h-10');
		expect(classes).toContain('px-4');
		expect(classes).toContain('py-2');
	});

	it('buttonVariants function generates correct classes for outline variant', () => {
		const classes = buttonVariants({ variant: 'outline' });
		
		expect(classes).toContain('border');
		expect(classes).toContain('border-input');
		expect(classes).toContain('bg-background');
		expect(classes).toContain('hover:bg-accent');
		expect(classes).toContain('hover:text-accent-foreground');
	});

	it('buttonVariants function generates correct classes for destructive variant', () => {
		const classes = buttonVariants({ variant: 'destructive' });
		
		expect(classes).toContain('bg-destructive');
		expect(classes).toContain('text-destructive-foreground');
		expect(classes).toContain('hover:bg-destructive/90');
	});

	it('buttonVariants function generates correct classes for secondary variant', () => {
		const classes = buttonVariants({ variant: 'secondary' });
		
		expect(classes).toContain('bg-secondary');
		expect(classes).toContain('text-secondary-foreground');
		expect(classes).toContain('hover:bg-secondary/80');
	});

	it('buttonVariants function generates correct classes for ghost variant', () => {
		const classes = buttonVariants({ variant: 'ghost' });
		
		expect(classes).toContain('hover:bg-accent');
		expect(classes).toContain('hover:text-accent-foreground');
	});

	it('buttonVariants function generates correct classes for link variant', () => {
		const classes = buttonVariants({ variant: 'link' });
		
		expect(classes).toContain('text-primary');
		expect(classes).toContain('underline-offset-4');
		expect(classes).toContain('hover:underline');
	});

	it('buttonVariants function generates correct classes for small size', () => {
		const classes = buttonVariants({ size: 'sm' });
		
		expect(classes).toContain('h-9');
		expect(classes).toContain('rounded-md');
		expect(classes).toContain('px-3');
	});

	it('buttonVariants function generates correct classes for large size', () => {
		const classes = buttonVariants({ size: 'lg' });
		
		expect(classes).toContain('h-11');
		expect(classes).toContain('rounded-md');
		expect(classes).toContain('px-8');
	});

	it('buttonVariants function generates correct classes for icon size', () => {
		const classes = buttonVariants({ size: 'icon' });
		
		expect(classes).toContain('h-10');
		expect(classes).toContain('w-10');
	});

	it('buttonVariants function includes accessibility classes', () => {
		const classes = buttonVariants();
		
		expect(classes).toContain('focus-visible:outline-none');
		expect(classes).toContain('focus-visible:ring-2');
		expect(classes).toContain('focus-visible:ring-ring');
		expect(classes).toContain('focus-visible:ring-offset-2');
		expect(classes).toContain('disabled:pointer-events-none');
		expect(classes).toContain('disabled:opacity-50');
	});

	it('buttonVariants function handles custom className', () => {
		const customClass = 'my-custom-class';
		const classes = buttonVariants({ className: customClass });
		
		expect(classes).toContain(customClass);
	});

	it('buttonVariants function combines variant and size correctly', () => {
		const classes = buttonVariants({ variant: 'outline', size: 'sm' });
		
		// Should have outline variant classes
		expect(classes).toContain('border');
		expect(classes).toContain('bg-background');
		
		// Should have small size classes
		expect(classes).toContain('h-9');
		expect(classes).toContain('px-3');
	});
});
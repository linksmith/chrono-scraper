import type { VariantProps } from 'tailwind-variants';
import { tv } from 'tailwind-variants';
import Root from './badge.svelte';

export const badgeVariants = tv({
	base: 'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
	variants: {
		variant: {
			default: 'border-transparent bg-primary text-primary-foreground hover:bg-primary/80',
			secondary: 'border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80',
			destructive: 'border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/80',
			outline: 'text-foreground',
			success: 'border-transparent bg-green-500 text-white hover:bg-green-600',
			warning: 'border-transparent bg-yellow-500 text-white hover:bg-yellow-600',
			info: 'border-transparent bg-blue-500 text-white hover:bg-blue-600'
		}
	},
	defaultVariants: {
		variant: 'default'
	}
});

export type Variant = VariantProps<typeof badgeVariants>['variant'];

export {
	Root,
	//
	Root as Badge
};
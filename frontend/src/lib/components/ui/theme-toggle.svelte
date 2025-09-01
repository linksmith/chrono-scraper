<script lang="ts">
	import { Moon, Sun } from 'lucide-svelte';
	import { Button } from './button';
	import { onMount } from 'svelte';

	let isDark = false;

	onMount(() => {
		// Check localStorage first, then system preference
		const savedTheme = localStorage.getItem('theme');
		const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
		
		if (savedTheme === 'dark' || (!savedTheme && systemPrefersDark)) {
			isDark = true;
			document.documentElement.classList.add('dark');
		} else {
			isDark = false;
			document.documentElement.classList.remove('dark');
		}

		// Listen for system theme changes
		const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
		const handleChange = (e: MediaQueryListEvent) => {
			if (!localStorage.getItem('theme')) {
				// Only auto-switch if user hasn't manually set a preference
				isDark = e.matches;
				if (e.matches) {
					document.documentElement.classList.add('dark');
				} else {
					document.documentElement.classList.remove('dark');
				}
			}
		};
		
		mediaQuery.addEventListener('change', handleChange);
		
		return () => {
			mediaQuery.removeEventListener('change', handleChange);
		};
	});

	function toggleTheme() {
		isDark = !isDark;
		
		if (isDark) {
			document.documentElement.classList.add('dark');
			localStorage.setItem('theme', 'dark');
		} else {
			document.documentElement.classList.remove('dark');
			localStorage.setItem('theme', 'light');
		}
	}
</script>

<Button
	variant="outline"
	size="sm"
	onclick={toggleTheme}
	class="h-9 w-9 p-0"
	aria-label="Toggle theme"
>
	{#if isDark}
		<Sun class="h-4 w-4" />
	{:else}
		<Moon class="h-4 w-4" />
	{/if}
</Button>

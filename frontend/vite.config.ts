import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		host: true,
		port: 5173,
		allowedHosts: ['localhost', '127.0.0.1', 'dl'],
		proxy: {
			'/api': {
				target: 'http://backend:8000',
				changeOrigin: true,
				secure: false,
			}
		}
	}
});
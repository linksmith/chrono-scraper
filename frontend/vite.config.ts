import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	optimizeDeps: {
		include: ['date-fns']
	},
	server: {
		host: true,
		port: 5173,
		allowedHosts: ['localhost', '127.0.0.1', 'dl'],
		proxy: {
			'/api': {
				target: 'http://backend:8000',
				changeOrigin: true,
				secure: false,
				configure: (proxy, options) => {
					proxy.on('proxyReq', (proxyReq, req, res) => {
						// Forward cookies
						if (req.headers.cookie) {
							proxyReq.setHeader('cookie', req.headers.cookie);
						}
					});
				}
			},
			// Enable WebSocket proxying for API paths
			'/api/v1/ws': {
				target: 'ws://backend:8000',
				ws: true,
				changeOrigin: true,
				secure: false
			}
		}
	}
});
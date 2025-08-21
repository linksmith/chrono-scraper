import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	optimizeDeps: {
		include: ['date-fns'],
		esbuildOptions: {
			sourcemap: false
		}
	},
	esbuild: {
		sourcemap: false
	},
	build: {
		sourcemap: false
	},
	css: {
		devSourcemap: false
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
				followRedirects: false,
				configure: (proxy, options) => {
					proxy.on('proxyReq', (proxyReq, req, res) => {
						// Forward cookies
						if (req.headers.cookie) {
							proxyReq.setHeader('cookie', req.headers.cookie);
						}
					});
					
					proxy.on('proxyRes', (proxyRes, req, res) => {
						// Intercept 307 redirects and make them relative
						if (proxyRes.statusCode === 307 && proxyRes.headers.location) {
							const location = proxyRes.headers.location;
							if (location.startsWith('http://backend:8000')) {
								proxyRes.headers.location = location.replace('http://backend:8000', '');
							}
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
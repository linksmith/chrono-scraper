import type { Handle } from '@sveltejs/kit';
import { redirect } from '@sveltejs/kit';

const PROTECTED_ROUTES = [
	'/projects',
	'/search',
	'/analytics',
	'/profile',
	'/admin'
];

const ADMIN_ROUTES = [
	'/admin'
];

export const handle: Handle = async ({ event, resolve }) => {
    // Session-based auth only; no JWT token
    const token = undefined;
	
	// Check if route requires authentication
	const isProtectedRoute = PROTECTED_ROUTES.some(route => 
		event.url.pathname.startsWith(route)
	);
	
	const isAdminRoute = ADMIN_ROUTES.some(route => 
		event.url.pathname.startsWith(route)
	);
	
	// Always verify session via cookie against backend
	try {
		// Use internal Docker service name for server-side requests
		const backendUrl = process.env.BACKEND_URL || 'http://backend:8000';
		const response = await fetch(`${backendUrl}/api/v1/auth/me`, {
			headers: {
				'Cookie': event.request.headers.get('cookie') || ''
			}
		});
		if (response.ok) {
			const user = await response.json();
			event.locals.user = user;
			event.locals.isAuthenticated = true;
			event.locals.isAdmin = user.is_admin || false;
		} else {
			event.locals.user = null;
			event.locals.isAuthenticated = false;
			event.locals.isAdmin = false;
		}
	} catch (error) {
		console.error('Auth verification failed:', error);
		event.locals.user = null;
		event.locals.isAuthenticated = false;
		event.locals.isAdmin = false;
	}
	
	// Redirect if authentication is required
	if (isProtectedRoute && !event.locals.isAuthenticated) {
		throw redirect(302, `/auth/login?redirect=${encodeURIComponent(event.url.pathname)}`);
	}
	
	// Redirect if admin access is required
	if (isAdminRoute && (!event.locals.isAuthenticated || !event.locals.isAdmin)) {
		throw redirect(302, '/');
	}
	
	const response = await resolve(event);
	return response;
};
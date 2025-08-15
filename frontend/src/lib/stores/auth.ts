import { writable, derived } from 'svelte/store';
import { browser } from '$app/environment';
import { goto } from '$app/navigation';
import { getApiUrl } from '$lib/utils';

export interface User {
	id: number;
	email: string;
	username: string;
	full_name?: string;
	is_active: boolean;
	is_admin: boolean;
	is_verified: boolean;
	created_at: string;
	last_login?: string;
}

export interface AuthState {
	user: User | null;
	isAuthenticated: boolean;
	isLoading: boolean;
	error: string | null;
}

// Create the auth store
function createAuthStore() {
	const { subscribe, set, update } = writable<AuthState>({
		user: null,
		isAuthenticated: false,
		isLoading: true,
		error: null
	});

	return {
		subscribe,
		
		// Initialize auth state from server
		async init() {
			if (!browser) return;
			
			update(state => ({ ...state, isLoading: true, error: null }));
			
			try {
				// Check session-based authentication first
				const response = await fetch('/api/v1/auth/me', {
					credentials: 'include'
				});
				
				if (response.ok) {
					const user = await response.json();
					set({
						user,
						isAuthenticated: true,
						isLoading: false,
						error: null
					});
				} else {
					set({
						user: null,
						isAuthenticated: false,
						isLoading: false,
						error: null
					});
				}
			} catch (error) {
				console.error('Auth initialization failed:', error);
				set({
					user: null,
					isAuthenticated: false,
					isLoading: false,
					error: 'Failed to check authentication status'
				});
			}
		},
		
		// Login with email and password
		async login(email: string, password: string) {
			update(state => ({ ...state, isLoading: true, error: null }));
			
			try {
				const response = await fetch(getApiUrl('/api/v1/auth/login/json'), {
					method: 'POST',
					headers: {
						'Content-Type': 'application/json'
					},
					credentials: 'include',
					body: JSON.stringify({ email, password })
				});
				
				if (response.ok) {
					const user = await response.json();
					set({
						user,
						isAuthenticated: true,
						isLoading: false,
						error: null
					});
					return { success: true };
				} else {
					const errorData = await response.json();
					const error = errorData.detail || 'Login failed';
					update(state => ({ ...state, isLoading: false, error }));
					return { success: false, error };
				}
			} catch (error) {
				const errorMessage = 'Network error during login';
				update(state => ({ ...state, isLoading: false, error: errorMessage }));
				return { success: false, error: errorMessage };
			}
		},
		
		// Register new user
		async register(userData: {
			email: string;
			password: string;
			username: string;
			full_name?: string;
		}) {
			update(state => ({ ...state, isLoading: true, error: null }));
			
			try {
				const response = await fetch(getApiUrl('/api/v1/auth/register'), {
					method: 'POST',
					headers: {
						'Content-Type': 'application/json'
					},
					credentials: 'include',
					body: JSON.stringify(userData)
				});
				
				if (response.ok) {
					const user = await response.json();
					set({
						user,
						isAuthenticated: true,
						isLoading: false,
						error: null
					});
					return { success: true };
				} else {
					const errorData = await response.json();
					const error = errorData.detail || 'Registration failed';
					update(state => ({ ...state, isLoading: false, error }));
					return { success: false, error };
				}
			} catch (error) {
				const errorMessage = 'Network error during registration';
				update(state => ({ ...state, isLoading: false, error: errorMessage }));
				return { success: false, error: errorMessage };
			}
		},
		
		// Logout
		async logout() {
			try {
				await fetch(getApiUrl('/api/v1/auth/logout'), {
					method: 'POST',
					credentials: 'include'
				});
			} catch (error) {
				console.error('Logout request failed:', error);
			}
			
			set({
				user: null,
				isAuthenticated: false,
				isLoading: false,
				error: null
			});
			
			goto('/auth/login');
		},
		
		// Update user profile
		async updateProfile(updates: Partial<User>) {
			update(state => ({ ...state, isLoading: true, error: null }));
			
			try {
				const response = await fetch(getApiUrl('/api/v1/auth/profile'), {
					method: 'PATCH',
					headers: {
						'Content-Type': 'application/json'
					},
					credentials: 'include',
					body: JSON.stringify(updates)
				});
				
				if (response.ok) {
					const updatedUser = await response.json();
					update(state => ({
						...state,
						user: updatedUser,
						isLoading: false,
						error: null
					}));
					return { success: true };
				} else {
					const errorData = await response.json();
					const error = errorData.detail || 'Profile update failed';
					update(state => ({ ...state, isLoading: false, error }));
					return { success: false, error };
				}
			} catch (error) {
				const errorMessage = 'Network error during profile update';
				update(state => ({ ...state, isLoading: false, error: errorMessage }));
				return { success: false, error: errorMessage };
			}
		},
		
		// Change password
		async changePassword(currentPassword: string, newPassword: string) {
			update(state => ({ ...state, isLoading: true, error: null }));
			
			try {
				const response = await fetch(getApiUrl('/api/v1/auth/change-password'), {
					method: 'POST',
					headers: {
						'Content-Type': 'application/json'
					},
					credentials: 'include',
					body: JSON.stringify({
						current_password: currentPassword,
						new_password: newPassword
					})
				});
				
				if (response.ok) {
					update(state => ({ ...state, isLoading: false, error: null }));
					return { success: true };
				} else {
					const errorData = await response.json();
					const error = errorData.detail || 'Password change failed';
					update(state => ({ ...state, isLoading: false, error }));
					return { success: false, error };
				}
			} catch (error) {
				const errorMessage = 'Network error during password change';
				update(state => ({ ...state, isLoading: false, error: errorMessage }));
				return { success: false, error: errorMessage };
			}
		},
		
		// Clear error
		clearError() {
			update(state => ({ ...state, error: null }));
		}
	};
}

export const auth = createAuthStore();

// Derived stores for convenience
export const user = derived(auth, $auth => $auth.user);
export const isAuthenticated = derived(auth, $auth => $auth.isAuthenticated);
export const isLoading = derived(auth, $auth => $auth.isLoading);
export const authError = derived(auth, $auth => $auth.error);
export const isAdmin = derived(auth, $auth => $auth.user?.is_admin || false);

// Navigation guard for protected routes
export function requireAuth() {
	if (browser) {
		auth.subscribe(state => {
			if (!state.isLoading && !state.isAuthenticated) {
				goto('/auth/login');
			}
		});
	}
}

// Admin guard for admin-only routes
export function requireAdmin() {
	if (browser) {
		auth.subscribe(state => {
			if (!state.isLoading) {
				if (!state.isAuthenticated) {
					goto('/auth/login');
				} else if (!state.user?.is_admin) {
					goto('/'); // Redirect to home if not admin
				}
			}
		});
	}
}
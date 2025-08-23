import { writable } from 'svelte/store';
import { browser } from '$app/environment';

export interface AppError {
	id: string;
	message: string;
	type: 'error' | 'warning' | 'info' | 'success';
	timestamp: Date;
	dismissible?: boolean;
	autoRemove?: boolean;
	duration?: number;
	source?: string;
	details?: any;
}

interface ErrorState {
	errors: AppError[];
	isOnline: boolean;
}

function createErrorStore() {
	const { subscribe, set, update } = writable<ErrorState>({
		errors: [],
		isOnline: true
	});

	// Generate unique error ID
	const generateId = () => `error_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

	// Remove specific error function
	const removeError = (id: string) => {
		update(state => ({
			...state,
			errors: state.errors.filter(error => error.id !== id)
		}));
	};

	return {
		subscribe,

		// Add a new error/notification
		add: (error: Omit<AppError, 'id' | 'timestamp'>) => {
			const newError: AppError = {
				id: generateId(),
				timestamp: new Date(),
				dismissible: true,
				autoRemove: true,
				duration: 5000,
				...error
			};

			update(state => ({
				...state,
				errors: [...state.errors, newError]
			}));

			// Auto remove after duration
			if (newError.autoRemove && newError.duration) {
				setTimeout(() => {
					removeError(newError.id);
				}, newError.duration);
			}

			return newError.id;
		},

		// Remove specific error
		remove: removeError,

		// Clear all errors
		clear: () => {
			update(state => ({
				...state,
				errors: []
			}));
		},

		// Clear errors by type
		clearType: (type: AppError['type']) => {
			update(state => ({
				...state,
				errors: state.errors.filter(error => error.type !== type)
			}));
		},

		// Helper methods for common error types
		error: (message: string, options?: Partial<AppError>) => {
			const newError: AppError = {
				id: generateId(),
				timestamp: new Date(),
				dismissible: true,
				autoRemove: true,
				message,
				type: 'error',
				duration: 8000,
				...options
			};

			update(state => ({
				...state,
				errors: [...state.errors, newError]
			}));

			// Auto remove after duration
			if (newError.autoRemove && newError.duration) {
				setTimeout(() => {
					removeError(newError.id);
				}, newError.duration);
			}

			return newError.id;
		},

		warning: (message: string, options?: Partial<AppError>) => {
			const newError: AppError = {
				id: generateId(),
				timestamp: new Date(),
				dismissible: true,
				autoRemove: true,
				message,
				type: 'warning',
				duration: 6000,
				...options
			};

			update(state => ({
				...state,
				errors: [...state.errors, newError]
			}));

			// Auto remove after duration
			if (newError.autoRemove && newError.duration) {
				setTimeout(() => {
					removeError(newError.id);
				}, newError.duration);
			}

			return newError.id;
		},

		success: (message: string, options?: Partial<AppError>) => {
			const newError: AppError = {
				id: generateId(),
				timestamp: new Date(),
				dismissible: true,
				autoRemove: true,
				message,
				type: 'success',
				duration: 4000,
				...options
			};

			update(state => ({
				...state,
				errors: [...state.errors, newError]
			}));

			// Auto remove after duration
			if (newError.autoRemove && newError.duration) {
				setTimeout(() => {
					removeError(newError.id);
				}, newError.duration);
			}

			return newError.id;
		},

		info: (message: string, options?: Partial<AppError>) => {
			const newError: AppError = {
				id: generateId(),
				timestamp: new Date(),
				dismissible: true,
				autoRemove: true,
				message,
				type: 'info',
				duration: 5000,
				...options
			};

			update(state => ({
				...state,
				errors: [...state.errors, newError]
			}));

			// Auto remove after duration
			if (newError.autoRemove && newError.duration) {
				setTimeout(() => {
					removeError(newError.id);
				}, newError.duration);
			}

			return newError.id;
		},

		// Handle API errors
		handleApiError: (error: any, context?: string) => {
			let message = 'An unexpected error occurred';
			let details = error;

			// Handle different error types
			if (error?.response) {
				// HTTP error response
				const status = error.response.status;
				const data = error.response.data;

				switch (status) {
					case 400:
						message = data?.detail || 'Invalid request. Please check your input.';
						break;
					case 401:
						message = 'You are not authorized. Please log in again.';
						break;
					case 403:
						message = 'You do not have permission to perform this action.';
						break;
					case 404:
						message = 'The requested resource was not found.';
						break;
					case 422:
						message = data?.detail || 'Validation error. Please check your input.';
						if (Array.isArray(data?.detail)) {
							message = data.detail.map((err: any) => err.msg).join(', ');
						}
						break;
					case 429:
						message = 'Too many requests. Please try again later.';
						break;
					case 500:
						message = 'Server error. Please try again later.';
						break;
					case 502:
					case 503:
					case 504:
						message = 'Service temporarily unavailable. Please try again later.';
						break;
					default:
						message = `Request failed with status ${status}`;
				}
			} else if (error?.message) {
				// JavaScript Error object
				message = error.message;
			} else if (typeof error === 'string') {
				message = error;
			}

			const newError: AppError = {
				id: generateId(),
				timestamp: new Date(),
				dismissible: true,
				autoRemove: true,
				message: context ? `${context}: ${message}` : message,
				type: 'error',
				source: context,
				details,
				duration: 8000
			};

			update(state => ({
				...state,
				errors: [...state.errors, newError]
			}));

			// Auto remove after duration
			if (newError.autoRemove && newError.duration) {
				setTimeout(() => {
					removeError(newError.id);
				}, newError.duration);
			}

			return newError.id;
		},

		// Handle network errors
		handleNetworkError: (error: any, context?: string) => {
			const isOffline = !navigator.onLine;
			
			update(state => ({
				...state,
				isOnline: !isOffline
			}));

			if (isOffline) {
				const newError: AppError = {
					id: generateId(),
					timestamp: new Date(),
					dismissible: true,
					autoRemove: true,
					message: 'You appear to be offline. Please check your internet connection.',
					type: 'warning',
					source: context,
					duration: 10000
				};

				update(state => ({
					...state,
					errors: [...state.errors, newError]
				}));

				// Auto remove after duration
				if (newError.autoRemove && newError.duration) {
					setTimeout(() => {
						removeError(newError.id);
					}, newError.duration);
				}

				return newError.id;
			}

			const newError: AppError = {
				id: generateId(),
				timestamp: new Date(),
				dismissible: true,
				autoRemove: true,
				message: context ? `${context}: Network error occurred` : 'Network error occurred',
				type: 'error',
				source: context,
				duration: 6000
			};

			update(state => ({
				...state,
				errors: [...state.errors, newError]
			}));

			// Auto remove after duration
			if (newError.autoRemove && newError.duration) {
				setTimeout(() => {
					removeError(newError.id);
				}, newError.duration);
			}

			return newError.id;
		},

		// Update online status
		setOnlineStatus: (isOnline: boolean) => {
			update(state => ({
				...state,
				isOnline
			}));
		}
	};
}

export const errorStore = createErrorStore();

// Initialize network status monitoring
if (browser) {
	// Monitor online/offline status
	window.addEventListener('online', () => {
		errorStore.setOnlineStatus(true);
		errorStore.success('Connection restored');
	});

	window.addEventListener('offline', () => {
		errorStore.setOnlineStatus(false);
		errorStore.warning('You are now offline');
	});

	// Global error handler for unhandled errors
	window.addEventListener('error', (event) => {
		errorStore.add({
			message: `Unexpected error: ${event.message}`,
			type: 'error',
			source: 'global',
			details: {
				filename: event.filename,
				lineno: event.lineno,
				colno: event.colno,
				error: event.error
			}
		});
	});

	// Global handler for unhandled promise rejections
	window.addEventListener('unhandledrejection', (event) => {
		errorStore.add({
			message: `Unhandled promise rejection: ${event.reason}`,
			type: 'error',
			source: 'promise',
			details: event.reason
		});
		
		// Prevent the default browser console error
		event.preventDefault();
	});
}
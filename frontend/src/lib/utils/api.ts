import { errorStore } from '$lib/stores/error';
import { loadingStore } from '$lib/stores/loading';
import { goto } from '$app/navigation';

export interface ApiOptions extends RequestInit {
	showError?: boolean;
	showSuccess?: boolean;
	successMessage?: string;
	retries?: number;
	retryDelay?: number;
	timeout?: number;
	loadingKey?: string;
	showLoading?: boolean;
}

export interface ApiResponse<T = any> {
	data?: T;
	error?: any;
	success: boolean;
	status?: number;
}

class ApiClient {
	private baseUrl = '';

	constructor(baseUrl = '') {
		this.baseUrl = baseUrl;
	}

	// Retry logic with exponential backoff
	private async retry<T>(
		fn: () => Promise<T>,
		retries: number = 3,
		delay: number = 1000
	): Promise<T> {
		try {
			return await fn();
		} catch (error) {
			if (retries > 0) {
				await new Promise(resolve => setTimeout(resolve, delay));
				return this.retry(fn, retries - 1, delay * 2);
			}
			throw error;
		}
	}

	// Main request method
	async request<T = any>(
		endpoint: string,
		options: ApiOptions = {}
	): Promise<ApiResponse<T>> {
		const {
			showError = true,
			showSuccess = false,
			successMessage = 'Operation completed successfully',
			retries = 1,
			retryDelay = 1000,
			timeout = 30000,
			loadingKey = `api_${endpoint.replace(/[^a-zA-Z0-9]/g, '_')}`,
			showLoading = true,
			...fetchOptions
		} = options;

		// Set loading state
		if (showLoading) {
			loadingStore.setLoading(loadingKey, true);
		}

		try {
			const controller = new AbortController();
			const timeoutId = setTimeout(() => controller.abort(), timeout);

			const response = await this.retry(
				async () => {
					const response = await fetch(`${this.baseUrl}${endpoint}`, {
						credentials: 'include',
						headers: {
							'Content-Type': 'application/json',
							...fetchOptions.headers,
						},
						signal: controller.signal,
						...fetchOptions,
					});

					clearTimeout(timeoutId);
					return response;
				},
				retries,
				retryDelay
			);

			// Handle different response types
			let data: T;
			const contentType = response.headers.get('Content-Type') || '';
			
			if (contentType.includes('application/json')) {
				data = await response.json();
			} else if (contentType.includes('text/')) {
				data = (await response.text()) as unknown as T;
			} else {
				data = (await response.blob()) as unknown as T;
			}

			if (!response.ok) {
				// Handle specific HTTP error codes
				switch (response.status) {
					case 401:
						if (showError) {
							errorStore.add({
								message: 'Your session has expired. Please log in again.',
								type: 'warning',
								source: 'api'
							});
						}
						// Redirect to login
						await goto('/auth/login');
						break;
					case 403:
						if (showError) {
							errorStore.add({
								message: 'You do not have permission to perform this action.',
								type: 'error',
								source: 'api'
							});
						}
						break;
					case 422:
						// Validation errors
						if (showError) {
							const message = Array.isArray(data)
								? data.map((err: any) => err.msg || err.message).join(', ')
								: (data as any)?.detail || 'Validation error occurred';
							
							errorStore.add({
								message,
								type: 'warning',
								source: 'validation'
							});
						}
						break;
					case 429:
						if (showError) {
							errorStore.add({
								message: 'Too many requests. Please slow down and try again.',
								type: 'warning',
								source: 'rate_limit'
							});
						}
						break;
					default:
						if (showError) {
							errorStore.handleApiError(
								{ response: { status: response.status, data } },
								`API ${fetchOptions.method || 'GET'} ${endpoint}`
							);
						}
				}

				return {
					success: false,
					error: data,
					status: response.status
				};
			}

			// Success response
			if (showSuccess) {
				errorStore.success(successMessage);
			}

			return {
				success: true,
				data,
				status: response.status
			};

		} catch (error: any) {
			// Network or other errors
			if (error.name === 'AbortError') {
				if (showError) {
					errorStore.add({
						message: 'Request timed out. Please try again.',
						type: 'warning',
						source: 'timeout'
					});
				}
			} else {
				if (showError) {
					errorStore.handleNetworkError(error, `API ${fetchOptions.method || 'GET'} ${endpoint}`);
				}
			}

			return {
				success: false,
				error
			};
		} finally {
			// Clear loading state
			if (showLoading) {
				loadingStore.setLoading(loadingKey, false);
			}
		}
	}

	// Convenience methods
	async get<T = any>(endpoint: string, options?: ApiOptions): Promise<ApiResponse<T>> {
		return this.request<T>(endpoint, { ...options, method: 'GET' });
	}

	async post<T = any>(endpoint: string, data?: any, options?: ApiOptions): Promise<ApiResponse<T>> {
		return this.request<T>(endpoint, {
			...options,
			method: 'POST',
			body: data ? JSON.stringify(data) : undefined,
		});
	}

	async put<T = any>(endpoint: string, data?: any, options?: ApiOptions): Promise<ApiResponse<T>> {
		return this.request<T>(endpoint, {
			...options,
			method: 'PUT',
			body: data ? JSON.stringify(data) : undefined,
		});
	}

	async patch<T = any>(endpoint: string, data?: any, options?: ApiOptions): Promise<ApiResponse<T>> {
		return this.request<T>(endpoint, {
			...options,
			method: 'PATCH',
			body: data ? JSON.stringify(data) : undefined,
		});
	}

	async delete<T = any>(endpoint: string, options?: ApiOptions): Promise<ApiResponse<T>> {
		return this.request<T>(endpoint, { ...options, method: 'DELETE' });
	}

	// File upload method
	async upload<T = any>(
		endpoint: string, 
		formData: FormData, 
		options?: Omit<ApiOptions, 'headers'>
	): Promise<ApiResponse<T>> {
		const { showError = true, ...otherOptions } = options || {};

		return this.request<T>(endpoint, {
			...otherOptions,
			method: 'POST',
			body: formData,
			headers: {
				// Don't set Content-Type for FormData - browser will set it with boundary
			},
			showError
		});
	}
}

// Create and export the default API client
export const api = new ApiClient('/api/v1');

// Export factory for custom base URLs
export const createApiClient = (baseUrl: string) => new ApiClient(baseUrl);

// Utility functions for common operations
export const apiUtils = {
	// Check if error is a network error
	isNetworkError: (error: any): boolean => {
		return !error.response && (
			error.code === 'NETWORK_ERROR' ||
			error.message?.includes('fetch') ||
			!navigator.onLine
		);
	},

	// Check if error is a validation error
	isValidationError: (error: any): boolean => {
		return error.response?.status === 422;
	},

	// Check if error is an auth error
	isAuthError: (error: any): boolean => {
		return error.response?.status === 401;
	},

	// Extract error message from API response
	extractErrorMessage: (error: any): string => {
		if (error.response?.data?.detail) {
			if (Array.isArray(error.response.data.detail)) {
				return error.response.data.detail.map((err: any) => err.msg).join(', ');
			}
			return error.response.data.detail;
		}
		if (error.message) {
			return error.message;
		}
		return 'An unexpected error occurred';
	}
};
import { writable } from 'svelte/store';

export interface LoadingState {
	[key: string]: boolean;
}

interface LoadingStore {
	states: LoadingState;
	global: boolean;
}

function createLoadingStore() {
	const { subscribe, set, update } = writable<LoadingStore>({
		states: {},
		global: false
	});

	return {
		subscribe,

		// Set loading state for a specific key
		setLoading: (key: string, loading: boolean) => {
			update(store => ({
				...store,
				states: {
					...store.states,
					[key]: loading
				}
			}));
		},

		// Set global loading state
		setGlobal: (loading: boolean) => {
			update(store => ({
				...store,
				global: loading
			}));
		},

		// Check if specific key is loading
		isLoading: (key: string): boolean => {
			let loading = false;
			subscribe(store => {
				loading = store.states[key] || false;
			})();
			return loading;
		},

		// Check if any operation is loading
		isAnyLoading: (): boolean => {
			let loading = false;
			subscribe(store => {
				loading = store.global || Object.values(store.states).some(state => state);
			})();
			return loading;
		},

		// Clear specific loading state
		clear: (key: string) => {
			update(store => {
				const { [key]: _, ...states } = store.states;
				return {
					...store,
					states
				};
			});
		},

		// Clear all loading states
		clearAll: () => {
			set({
				states: {},
				global: false
			});
		},

		// Helper for async operations
		withLoading: async <T>(
			key: string, 
			operation: () => Promise<T>,
			options: { 
				global?: boolean;
				errorHandler?: (error: any) => void;
			} = {}
		): Promise<T> => {
			const { global = false, errorHandler } = options;

			try {
				if (global) {
					createLoadingStore().setGlobal(true);
				} else {
					createLoadingStore().setLoading(key, true);
				}

				const result = await operation();
				return result;
			} catch (error) {
				if (errorHandler) {
					errorHandler(error);
				} else {
					throw error;
				}
				throw error;
			} finally {
				if (global) {
					createLoadingStore().setGlobal(false);
				} else {
					createLoadingStore().setLoading(key, false);
				}
			}
		}
	};
}

export const loadingStore = createLoadingStore();

// Derived stores for common loading states
export const isGlobalLoading = writable(false);
export const isAuthLoading = writable(false);
export const isApiLoading = writable(false);

// Update derived stores when main store changes
loadingStore.subscribe(store => {
	isGlobalLoading.set(store.global);
	isAuthLoading.set(store.states.auth || false);
	isApiLoading.set(store.states.api || false);
});
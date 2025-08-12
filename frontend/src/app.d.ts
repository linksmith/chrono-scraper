/// <reference types="@sveltejs/kit" />

declare global {
	namespace App {
		interface Locals {
			user: {
				id: number;
				email: string;
				username: string;
				full_name?: string;
				is_active: boolean;
				is_admin: boolean;
				created_at: string;
				last_login?: string;
			} | null;
			isAuthenticated: boolean;
			isAdmin: boolean;
		}
		// interface Error {}
		// interface PageData {}
		// interface PageState {}
		// interface Platform {}
	}
}

export {};
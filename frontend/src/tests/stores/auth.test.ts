/**
 * Tests for Auth Store
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { auth } from '../../lib/stores/auth';

// Mock getApiUrl utility  
vi.mock('../../lib/utils', () => ({
  getApiUrl: (path: string) => `http://localhost:8000${path}`
}));

describe('Auth Store', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset fetch mock
    global.fetch = vi.fn();
    
    // Reset the store to initial state
    // Since we can't directly reset the store, we'll ensure clean state in each test
  });

  describe('Initial State', () => {
    it('should have correct initial state', () => {
      const state = get(auth);
      
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
      expect(state.isLoading).toBe(true); // Default loading state
      expect(state.error).toBeNull();
    });
  });

  describe('Login', () => {
    it('should successfully login with valid credentials', async () => {
      const mockUser = {
        id: 1,
        email: 'test@example.com',
        username: 'testuser',
        full_name: 'Test User',
        is_active: true,
        is_admin: false,
        created_at: '2024-01-01T00:00:00Z'
      };

      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: true,
        json: async () => mockUser
      });

      const result = await auth.login('test@example.com', 'password123');

      expect(result.success).toBe(true);
      expect(global.fetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v1/auth/login',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include'
        })
      );
    });

    it('should handle login failure with invalid credentials', async () => {
      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({
          detail: 'Incorrect email or password'
        })
      });

      const result = await auth.login('wrong@example.com', 'wrongpassword');

      expect(result.success).toBe(false);
      expect(result.error).toBe('Incorrect email or password');
    });
  });

  describe('Error Handling', () => {
    it('should clear errors when clearError is called', () => {
      auth.clearError();
      const state = get(auth);
      expect(state.error).toBeNull();
    });
  });
});
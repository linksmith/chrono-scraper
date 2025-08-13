/**
 * Test setup and configuration
 */
import { vi } from 'vitest';
import { beforeEach } from 'vitest';

// Mock fetch globally
global.fetch = vi.fn();

// Mock browser APIs for node environment
global.window = {
  location: {
    href: 'http://localhost:5173',
    origin: 'http://localhost:5173',
    pathname: '/',
    search: '',
    hash: ''
  }
} as any;

global.document = {
  body: {
    appendChild: vi.fn(),
    removeChild: vi.fn(),
    querySelector: vi.fn(),
    querySelectorAll: vi.fn()
  },
  createElement: vi.fn(() => ({
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    setAttribute: vi.fn(),
    getAttribute: vi.fn(),
    appendChild: vi.fn(),
    removeChild: vi.fn()
  })),
  createTextNode: vi.fn(),
  addEventListener: vi.fn(),
  removeEventListener: vi.fn()
} as any;

global.localStorage = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn()
};

global.sessionStorage = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn()
};

// Mock SvelteKit modules
vi.mock('$app/environment', () => ({
  browser: false,
  building: false,
  dev: true,
  version: '1.0.0'
}));

vi.mock('$app/navigation', () => ({
  goto: vi.fn(),
  invalidate: vi.fn(),
  invalidateAll: vi.fn(),
  preloadData: vi.fn(),
  preloadCode: vi.fn(),
  beforeNavigate: vi.fn(),
  afterNavigate: vi.fn(),
  pushState: vi.fn(),
  replaceState: vi.fn()
}));

vi.mock('$app/stores', () => ({
  page: {
    subscribe: vi.fn(() => vi.fn())
  },
  navigating: {
    subscribe: vi.fn(() => vi.fn())
  },
  updated: {
    subscribe: vi.fn(() => vi.fn())
  }
}));

// Reset all mocks before each test
beforeEach(() => {
  vi.resetAllMocks();
  if (global.localStorage && global.localStorage.clear) {
    global.localStorage.clear();
  }
  if (global.sessionStorage && global.sessionStorage.clear) {
    global.sessionStorage.clear();
  }
});
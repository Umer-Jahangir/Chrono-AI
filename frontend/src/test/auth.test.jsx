import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import {
  CHRONO_TOKEN_KEY,
  apiRequest,
  getAccessToken,
  storeAccessToken,
} from '../lib/apiClient';

const user = {
  id: '00000000-0000-0000-0000-000000000001',
  email: 'fixture@example.invalid',
  display_name: 'Chrono Fixture',
  picture_url: null,
};

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function installGoogleMock() {
  let credentialCallback;
  window.google = {
    accounts: {
      id: {
        initialize: vi.fn(({ callback }) => { credentialCallback = callback; }),
        renderButton: vi.fn((element) => {
          const button = document.createElement('button');
          button.textContent = 'Continue with Google';
          button.addEventListener('click', () => credentialCallback({ credential: 'google-id-fixture' }));
          element.appendChild(button);
        }),
        disableAutoSelect: vi.fn(),
      },
    },
  };
}

describe('authenticated application shell', () => {
  beforeEach(() => {
    installGoogleMock();
  });

  it('shows Google Sign-In and hides the existing application while signed out', async () => {
    vi.stubGlobal('fetch', vi.fn());
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Welcome to Chrono AI' })).toBeVisible();
    expect(await screen.findByRole('button', { name: 'Continue with Google' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Welcome to Chrono AI' }).closest('.auth-card')).toHaveClass('min-w-0');
    expect(screen.queryByRole('link', { name: 'Dashboard' })).not.toBeInTheDocument();
  });

  it('exchanges the Google credential, stores only the Chrono token, and verifies /auth/me', async () => {
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/auth/google')) {
        return Promise.resolve(jsonResponse({
          access_token: 'chrono-token-fixture', token_type: 'bearer', expires_in: 3600, user,
        }));
      }
      if (url.endsWith('/auth/me')) return Promise.resolve(jsonResponse(user));
      throw new Error(`Unexpected URL ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Continue with Google' }));
    expect(await screen.findByRole('link', { name: 'Dashboard' })).toBeVisible();

    const authCall = fetchMock.mock.calls.find(([url]) => url.endsWith('/auth/google'));
    expect(JSON.parse(authCall[1].body)).toEqual({ credential: 'google-id-fixture' });
    expect(authCall[1].headers.Authorization).toBeUndefined();
    const meCall = fetchMock.mock.calls.find(([url]) => url.endsWith('/auth/me'));
    expect(meCall[1].headers.Authorization).toBe('Bearer chrono-token-fixture');
    expect(window.localStorage.getItem(CHRONO_TOKEN_KEY)).toBe('chrono-token-fixture');
    expect(JSON.stringify({ ...window.localStorage })).not.toContain('google-id-fixture');
  });

  it('restores a stored session only after /auth/me succeeds', async () => {
    storeAccessToken('restored-token');
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(user)));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    expect(screen.getByText('Verifying your Chrono session…')).toBeVisible();
    expect(await screen.findByRole('link', { name: 'Home' })).toBeVisible();
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/auth\/me$/);
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe('Bearer restored-token');
  });

  it('clears an invalid or expired token and returns to login', async () => {
    storeAccessToken('expired-token');
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ detail: 'Authentication required' }, 401))));
    render(<App />);
    expect(await screen.findByText('Your session expired. Please sign in again.')).toBeVisible();
    expect(getAccessToken()).toBeNull();
    expect(screen.queryByRole('link', { name: 'Search' })).not.toBeInTheDocument();
  });

  it('preserves a potentially valid token on a retryable network failure', async () => {
    storeAccessToken('possibly-valid-token');
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('offline'))));
    render(<App />);
    expect(await screen.findByText('Unable to reach Chrono. Check your connection and retry.')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Retry session check' })).toBeVisible();
    expect(getAccessToken()).toBe('possibly-valid-token');
  });

  it('logout removes the Chrono token and hides protected navigation', async () => {
    storeAccessToken('logout-token');
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse(user))));
    render(<App />);
    const signOut = await screen.findByRole('button', { name: 'Sign out of Chrono' });
    expect(signOut).toHaveTextContent('Sign out');
    fireEvent.click(signOut);
    expect(await screen.findByRole('heading', { name: 'Welcome to Chrono AI' })).toBeVisible();
    expect(getAccessToken()).toBeNull();
    expect(screen.queryByRole('link', { name: 'Dashboard' })).not.toBeInTheDocument();
  });
});

describe('central API client', () => {
  it('adds a bearer token and never adds a client-controlled user_id', async () => {
    storeAccessToken('api-token');
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse({ ok: true })));
    vi.stubGlobal('fetch', fetchMock);
    await apiRequest('/ask', { method: 'POST', body: { question: 'Show my PDFs', limit: 10 } });
    const options = fetchMock.mock.calls[0][1];
    expect(options.headers.Authorization).toBe('Bearer api-token');
    expect(JSON.parse(options.body)).toEqual({ question: 'Show my PDFs', limit: 10 });
    expect(options.body).not.toContain('user_id');
  });

  it.each([
    [401, 'Your session expired'],
    [403, 'permission'],
    [422, 'invalid'],
    [429, 'too many requests'],
    [500, 'temporarily unavailable'],
  ])('handles HTTP %s with a safe user-facing message', async (status, message) => {
    storeAccessToken('error-token');
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ detail: '<private>' }, status))));
    await expect(apiRequest('/protected')).rejects.toThrow(message);
    if (status === 401) expect(getAccessToken()).toBeNull();
  });

  it('handles a non-JSON server response without exposing internals', async () => {
    storeAccessToken('html-error-token');
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('<html>proxy error</html>', { status: 502 }))));
    await expect(apiRequest('/protected')).rejects.toThrow('temporarily unavailable');
  });

  it('reports network errors as retryable without logging tokens', async () => {
    storeAccessToken('never-log-this-token');
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('offline'))));
    await expect(apiRequest('/protected')).rejects.toMatchObject({ retryable: true, status: 0 });
    expect(logSpy).not.toHaveBeenCalled();
  });
});

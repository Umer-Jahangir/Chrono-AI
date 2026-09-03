import { chronoConfig } from '../config';

export const CHRONO_TOKEN_KEY = 'chrono_access_token';
export const UNAUTHORIZED_EVENT = 'chrono:unauthorized';

const statusMessages = {
  401: 'Your session expired. Please sign in again.',
  403: 'You do not have permission to perform this action.',
  422: 'Some information was invalid. Please review it and try again.',
  429: 'Chrono is receiving too many requests. Please wait and try again.',
};

export class ApiError extends Error {
  constructor(message, { status = 0, details = null, retryable = false } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.details = details;
    this.retryable = retryable;
  }
}

export function getAccessToken() {
  return window.localStorage.getItem(CHRONO_TOKEN_KEY);
}

export function storeAccessToken(token) {
  window.localStorage.setItem(CHRONO_TOKEN_KEY, token);
}

export function clearAccessToken() {
  window.localStorage.removeItem(CHRONO_TOKEN_KEY);
}

function announceUnauthorized() {
  clearAccessToken();
  window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
}

async function parseResponse(response) {
  if (response.status === 204) return null;
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function errorForResponse(response, payload) {
  if (response.status === 401) announceUnauthorized();
  const fallback = response.status >= 500
    ? 'Chrono is temporarily unavailable. Please try again.'
    : 'Chrono could not complete this request.';
  return new ApiError(statusMessages[response.status] || fallback, {
    status: response.status,
    details: response.status === 422 && typeof payload === 'object' ? payload?.detail : null,
    retryable: response.status === 429 || response.status >= 500,
  });
}

export async function apiRequest(path, {
  method = 'GET',
  body,
  auth = true,
  signal,
  timeoutMs = 15000,
} = {}) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort('timeout'), timeoutMs);
  const abortFromCaller = () => controller.abort('cancelled');
  signal?.addEventListener('abort', abortFromCaller, { once: true });

  const headers = { Accept: 'application/json' };
  if (auth) {
    const token = getAccessToken();
    if (!token) {
      window.clearTimeout(timeoutId);
      throw new ApiError(statusMessages[401], { status: 401 });
    }
    headers.Authorization = `Bearer ${token}`;
  }
  let requestBody = body;
  if (body !== undefined && !(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    requestBody = JSON.stringify(body);
  }

  try {
    const response = await fetch(`${chronoConfig.apiBaseUrl}${path}`, {
      method,
      headers,
      body: requestBody,
      signal: controller.signal,
    });
    const payload = await parseResponse(response);
    if (!response.ok) throw errorForResponse(response, payload);
    return payload;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (controller.signal.aborted) {
      const timedOut = controller.signal.reason === 'timeout';
      throw new ApiError(
        timedOut ? 'Chrono took too long to respond. Please retry.' : 'The request was cancelled.',
        { retryable: timedOut },
      );
    }
    throw new ApiError('Unable to reach Chrono. Check your connection and retry.', {
      retryable: true,
    });
  } finally {
    window.clearTimeout(timeoutId);
    signal?.removeEventListener('abort', abortFromCaller);
  }
}

export const chronoApi = Object.freeze({
  exchangeGoogleCredential: (credential) => apiRequest('/auth/google', {
    method: 'POST',
    auth: false,
    body: { credential },
  }),
  me: () => apiRequest('/auth/me'),
  ask: (question, options = {}) => apiRequest('/ask', {
    method: 'POST',
    body: { question, limit: 10 },
    ...options,
  }),
  timeline: (history = false, options = {}) => apiRequest(
    history ? '/timeline/history?limit=100' : '/timeline?limit=100',
    options,
  ),
  driveStatus: (options = {}) => apiRequest('/integrations/google-drive/status', options),
  dashboardSummary: (range = 'this_week', options = {}) => apiRequest(
    `/dashboard/summary?range=${encodeURIComponent(range)}`,
    options,
  ),
});

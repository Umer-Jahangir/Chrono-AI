const trimTrailingSlash = (value) => value.replace(/\/+$/, '');

export const chronoConfig = Object.freeze({
  apiBaseUrl: trimTrailingSlash(
    import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  ),
  googleClientId: (import.meta.env.VITE_GOOGLE_CLIENT_ID || '').trim(),
});

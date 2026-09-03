import { useEffect, useRef, useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { chronoConfig } from '../../config';

export default function LoginPage() {
  const buttonRef = useRef(null);
  const { status, message, loginWithGoogleCredential, restoreSession } = useAuth();
  const [providerError, setProviderError] = useState('');
  const [providerStatus, setProviderStatus] = useState('loading');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    let script = document.getElementById('google-identity-services');
    if (!script) {
      script = document.createElement('script');
      script.id = 'google-identity-services';
      script.src = 'https://accounts.google.com/gsi/client';
      script.async = true;
      script.defer = true;
      document.head.appendChild(script);
    }

    const failProvider = () => {
      if (!active) return;
      setProviderStatus('error');
      setProviderError('Google Sign-In could not load. Check your connection and retry.');
      if (script) script.dataset.failed = 'true';
    };

    const renderGoogleButton = () => {
      if (!active || !buttonRef.current) return;
      if (!chronoConfig.googleClientId) {
        setProviderError('Google Sign-In needs VITE_GOOGLE_CLIENT_ID in the frontend environment.');
        setProviderStatus('error');
        return;
      }
      const identity = window.google?.accounts?.id;
      if (!identity) {
        failProvider();
        return;
      }
      setProviderError('');
      setProviderStatus('ready');
      buttonRef.current.replaceChildren();
      identity.initialize({
        client_id: chronoConfig.googleClientId,
        callback: ({ credential }) => {
          if (!credential) {
            setProviderError('Google did not return a sign-in credential.');
            return;
          }
          loginWithGoogleCredential(credential).catch(() => {});
        },
      });
      identity.renderButton(buttonRef.current, {
        theme: 'outline',
        size: 'large',
        shape: 'pill',
        text: 'continue_with',
        width: 280,
      });
    };

    const timeout = window.setTimeout(failProvider, 8_000);
    if (window.google?.accounts?.id) renderGoogleButton();
    else {
      script?.addEventListener('load', renderGoogleButton);
      script?.addEventListener('error', failProvider);
    }
    return () => {
      active = false;
      window.clearTimeout(timeout);
      script?.removeEventListener('load', renderGoogleButton);
      script?.removeEventListener('error', failProvider);
    };
  }, [attempt, loginWithGoogleCredential]);

  const retryGoogle = () => {
    const script = document.getElementById('google-identity-services');
    if (script?.dataset.failed === 'true') script.remove();
    setProviderError('');
    setProviderStatus('loading');
    setAttempt((value) => value + 1);
  };

  return (
    <main className="relative flex min-h-dvh w-full min-w-0 items-center justify-center overflow-x-hidden overflow-y-auto bg-background px-4 py-8">
      <div className="absolute inset-0 bg-gradient-to-b from-primary-container/20 via-transparent to-transparent pointer-events-none" />
      <div className="absolute -top-32 -left-32 w-96 h-96 rounded-full bg-primary/10 blur-3xl pointer-events-none" />
      <section className="auth-card relative min-w-0 rounded-2xl border border-outline-variant/30 bg-surface-container-lowest p-6 text-center shadow-2xl sm:p-10">
        <div className="w-14 h-14 mx-auto rounded-2xl bg-primary text-on-primary flex items-center justify-center shadow-lg mb-6" aria-hidden="true">
          <span className="material-symbols-outlined text-3xl">history_edu</span>
        </div>
        <h1 className="mb-3 text-3xl font-bold leading-tight text-on-surface sm:text-4xl">Welcome to Chrono AI</h1>
        <p className="mx-auto mb-7 max-w-sm text-sm leading-6 text-on-surface-variant sm:text-base">
          Sign in to search your private memory timeline. Protected data stays hidden until your session is verified.
        </p>
        <div
          ref={buttonRef}
          data-testid="google-signin"
          className="google-signin-slot flex min-h-11 min-w-0 max-w-full items-center justify-center overflow-hidden"
          aria-label="Sign in with Google"
        />
        {providerStatus === 'loading' && status !== 'signingIn' && (
          <p className="mt-3 text-sm text-on-surface-variant" role="status">Loading Google Sign-In…</p>
        )}
        {status === 'signingIn' && (
          <p className="mt-4 text-sm text-primary" role="status">Verifying your Google account…</p>
        )}
        {(providerError || message) && (
          <div className="mt-5 rounded-xl bg-error-container text-on-error-container p-3 text-sm" role="alert">
            {providerError || message}
          </div>
        )}
        {providerStatus === 'error' && (
          <button type="button" onClick={retryGoogle} className="mt-4 inline-flex items-center justify-center gap-2 rounded-lg border border-outline-variant px-4 py-2 text-sm font-semibold text-primary hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40">
            <span className="material-symbols-outlined text-[18px]" aria-hidden="true">refresh</span> Retry Google Sign-In
          </button>
        )}
        {status === 'error' && (
          <button
            type="button"
            onClick={restoreSession}
            className="mt-4 inline-flex items-center justify-center rounded-lg border border-outline-variant px-4 py-2 text-primary hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
          >
            Retry session check
          </button>
        )}
        <p className="mt-8 text-xs text-on-surface-variant">
          Chrono never asks for or stores your Google password.
        </p>
      </section>
    </main>
  );
}

import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import AskResults from '../components/ask/AskResults';
import { ApiError, chronoApi } from '../lib/apiClient';

const exampleQuestions = [
  'What technical skills and experience does Umer Jahangir have?',
  'Show files created on August 29, 2026.',
  'How many PDF files do I have?',
];

export default function SearchPage() {
  const location = useLocation();
  const initialQuestion = typeof location.state?.question === 'string' ? location.state.question : '';
  const [question, setQuestion] = useState(initialQuestion);
  const [lastQuestion, setLastQuestion] = useState('');
  const [response, setResponse] = useState(null);
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isTipsOpen, setIsTipsOpen] = useState(false);
  const activeRequest = useRef(null);
  const isSubmitting = useRef(false);
  const didAutoSearch = useRef(false);

  useEffect(() => () => activeRequest.current?.abort(), []);

  const runSearch = useCallback(async (requestedQuestion = question) => {
    const trimmed = requestedQuestion.trim();
    if (trimmed.length < 2 || isSubmitting.current) return;
    isSubmitting.current = true;
    const controller = new AbortController();
    activeRequest.current = controller;
    setQuestion(trimmed);
    setLastQuestion(trimmed);
    setIsLoading(true);
    setError(null);
    setResponse(null);
    try {
      const result = await chronoApi.ask(trimmed, { signal: controller.signal });
      setResponse(result);
    } catch (requestError) {
      if (!(requestError instanceof ApiError && requestError.message === 'The request was cancelled.')) {
        setError(requestError);
      }
    } finally {
      if (activeRequest.current === controller) {
        activeRequest.current = null;
        isSubmitting.current = false;
        setIsLoading(false);
      }
    }
  }, [question]);

  useEffect(() => {
    if (initialQuestion && !didAutoSearch.current) {
      didAutoSearch.current = true;
      runSearch(initialQuestion);
    }
  }, [initialQuestion, runSearch]);

  const submit = (event) => {
    event.preventDefault();
    runSearch();
  };

  return (
    <div className="relative grid min-h-[calc(100dvh-4rem)] w-full min-w-0 flex-1 grid-cols-1 overflow-x-hidden xl:grid-cols-[18rem_minmax(0,1fr)]">
      {isTipsOpen && (
        <button type="button" aria-label="Close search tips" className="fixed inset-0 top-16 z-30 bg-gray-900/40 xl:hidden" onClick={() => setIsTipsOpen(false)} />
      )}

      <aside className={`fixed bottom-0 left-0 top-16 z-40 flex w-[min(86vw,18rem)] flex-col overflow-y-auto border-r border-border bg-surface p-5 transition-transform duration-300 xl:sticky xl:top-16 xl:h-[calc(100dvh-4rem)] xl:w-72 ${isTipsOpen ? 'translate-x-0' : '-translate-x-full xl:translate-x-0'}`}>
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-sm font-semibold text-text-main">Natural search</h2>
          <button type="button" onClick={() => setIsTipsOpen(false)} className="flex h-8 w-8 items-center justify-center rounded-md hover:bg-gray-100 xl:hidden" aria-label="Close tips"><span className="material-symbols-outlined" aria-hidden="true">close</span></button>
        </div>
        <p className="text-sm text-text-muted leading-relaxed mb-6">
          Ask naturally. Chrono can interpret content questions, file types, dates, event history, owners, and counts.
        </p>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-text-main mb-3">Try an example</h3>
        <div className="space-y-3">
          {exampleQuestions.map((example) => (
            <button
              key={example}
              type="button"
              disabled={isLoading}
              onClick={() => { setQuestion(example); runSearch(example); }}
              className="w-full text-left p-3 rounded-xl bg-white border border-border text-sm text-text-main hover:border-primary hover:text-primary transition-colors disabled:opacity-60"
            >
              {example}
            </button>
          ))}
        </div>
        <div className="mt-auto pt-6 text-xs text-text-muted border-t border-border">
          Results are private to your authenticated Chrono account. AI answers may be incomplete; verify important information.
        </div>
      </aside>

      <main className="min-w-0 overflow-x-hidden bg-background p-4 sm:p-6 lg:p-8">
        <div className="mx-auto w-full min-w-0 max-w-5xl">
          <form onSubmit={submit} className="sticky top-0 z-20 rounded-2xl border border-border bg-surface p-3 shadow-sm sm:p-4" aria-label="Ask Chrono">
            <div className="flex gap-2">
              <button type="button" onClick={() => setIsTipsOpen(true)} className="rounded-xl border border-border bg-white p-3 text-text-muted xl:hidden" aria-label="Open search tips"><span className="material-symbols-outlined text-[20px]" aria-hidden="true">tips_and_updates</span></button>
              <label htmlFor="chrono-question" className="sr-only">Ask Chrono about your files and timeline</label>
              <div className="relative flex-1">
                <span className="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-primary" aria-hidden="true">search</span>
                <input
                  id="chrono-question"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  disabled={isLoading}
                  autoComplete="off"
                  className="block w-full pl-12 pr-4 py-3.5 border border-border rounded-xl bg-background focus:bg-white focus:ring-2 focus:ring-primary/20 focus:border-primary text-sm transition-all disabled:opacity-70"
                  placeholder="Ask about a document, date, owner, change, or count…"
                />
              </div>
              <button type="submit" disabled={isLoading || question.trim().length < 2} className="bg-primary text-white px-4 sm:px-6 rounded-xl flex items-center justify-center hover:bg-primary-fixed hover:text-on-primary-fixed transition-colors text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed">
                {isLoading ? <span className="material-symbols-outlined animate-spin" aria-hidden="true">progress_activity</span> : <><span className="hidden sm:inline">Search</span><span className="material-symbols-outlined sm:hidden" aria-hidden="true">arrow_forward</span></>}
              </button>
            </div>
          </form>

          <div className="py-6" aria-live="polite" aria-busy={isLoading}>
            {isLoading && (
              <div className="rounded-2xl bg-white border border-border p-10 text-center" role="status">
                <span className="material-symbols-outlined text-primary text-4xl animate-spin" aria-hidden="true">progress_activity</span>
                <p className="mt-3 text-text-main font-medium">Searching your Chrono memories…</p>
                <p className="mt-1 text-sm text-text-muted">This may include metadata, lexical, and semantic retrieval.</p>
              </div>
            )}

            {error && (
              <div className="rounded-2xl bg-error-container border border-error/20 p-5" role="alert">
                <h2 className="font-semibold text-on-error-container">Search could not be completed</h2>
                <p className="mt-1 text-sm text-on-error-container">{error.message}</p>
                {error.retryable && lastQuestion && (
                  <button type="button" disabled={isLoading} onClick={() => runSearch(lastQuestion)} className="mt-4 px-4 py-2 rounded-lg bg-white border border-error/20 text-on-error-container hover:bg-error-container disabled:opacity-50">Retry</button>
                )}
              </div>
            )}

            {!isLoading && !error && response && <AskResults response={response} />}

            {!isLoading && !error && !response && (
              <section className="mx-auto flex min-h-[22rem] w-full max-w-3xl min-w-0 flex-col items-center justify-center rounded-2xl border border-border bg-white p-6 text-center sm:p-12">
                <div className="w-12 h-12 rounded-full bg-primary/10 text-primary mx-auto flex items-center justify-center mb-4" aria-hidden="true"><span className="material-symbols-outlined">auto_awesome</span></div>
                <h1 className="text-xl font-bold text-text-main">Search your memory timeline</h1>
                <p className="mt-2 text-sm text-text-muted max-w-lg mx-auto">
                  Ask a question above. Chrono will show grounded answers, citations, structured files, history, or a clear explanation when metadata is unavailable.
                </p>
              </section>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

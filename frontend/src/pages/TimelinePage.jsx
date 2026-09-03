import { useCallback, useEffect, useState } from 'react';
import { formatChronoDate } from '../lib/format';
import { chronoApi } from '../lib/apiClient';
import { DriveTitle, OpenDriveButton } from '../components/common/DriveLink';

function TimelineRow({ item }) {
  const title = item.title || 'Untitled Drive item';
  const date = item.event_date;
  const mimeType = item.mime_type;
  const isFolder = item.item_type === 'folder';
  return (
    <article className="relative flex gap-4 p-4 sm:p-5 rounded-2xl bg-white border border-outline-variant/30 shadow-sm">
      <div className="relative z-10 w-11 h-11 rounded-full bg-primary/10 text-primary flex items-center justify-center flex-shrink-0 border-4 border-background" aria-hidden="true">
        <span className="material-symbols-outlined text-xl">{isFolder ? 'folder' : 'description'}</span>
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-1">
          <h2 className="min-w-0 break-words font-semibold text-on-surface"><DriveTitle title={title} openUrl={item.open_url} /></h2>
          {date && <time className="text-xs text-on-surface-variant flex-shrink-0" dateTime={date}>{formatChronoDate(date)}</time>}
        </div>
        <div className="mt-2 flex flex-wrap gap-2 text-xs text-on-surface-variant">
          <span className="px-2 py-1 rounded-full bg-surface-container">{item.source || 'google_drive'}</span>
          {item.event_type && <span className="px-2 py-1 rounded-full bg-surface-container capitalize">{item.event_type}</span>}
          {mimeType && <span className="px-2 py-1 rounded-full bg-surface-container break-all">{isFolder ? 'Folder' : mimeType}</span>}
        </div>
        {item.excerpt && <p className="mt-3 break-words text-sm leading-6 text-on-surface-variant">{item.excerpt}</p>}
        {item.open_url && <div className="mt-3"><OpenDriveButton title={title} openUrl={item.open_url} /></div>}
      </div>
    </article>
  );
}

export default function TimelinePage() {
  const [view, setView] = useState('current');
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadTimeline = useCallback(async (signal) => {
    setLoading(true);
    setError(null);
    try {
      setData(await chronoApi.timeline(view === 'history', { signal }));
    } catch (requestError) {
      if (!signal?.aborted) setError(requestError);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [view]);

  useEffect(() => {
    const controller = new AbortController();
    const task = window.setTimeout(() => loadTimeline(controller.signal), 0);
    return () => {
      window.clearTimeout(task);
      controller.abort();
    };
  }, [loadTimeline]);

  const items = Array.isArray(data?.items) ? data.items : [];
  return (
    <main className="min-h-[calc(100dvh-4rem)] min-w-0 flex-1 overflow-x-hidden bg-background px-4 py-6 sm:px-8 sm:py-8">
      <div className="max-w-4xl mx-auto">
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-8">
          <div>
            <p className="text-xs uppercase tracking-wider text-primary font-semibold mb-2">Authenticated Drive activity</p>
            <h1 className="font-headline-lg text-headline-lg text-on-surface">Your memory timeline</h1>
            <p className="text-sm text-on-surface-variant mt-2">Current synchronized items or immutable change history.</p>
          </div>
          <div className="inline-flex p-1 rounded-xl bg-surface-container border border-outline-variant/30" role="tablist" aria-label="Timeline view">
            {['current', 'history'].map((option) => (
              <button
                key={option}
                type="button"
                role="tab"
                aria-selected={view === option}
                onClick={() => setView(option)}
                className={`px-4 py-2 rounded-lg text-sm font-medium capitalize ${view === option ? 'bg-white text-primary shadow-sm' : 'text-on-surface-variant'}`}
              >
                {option}
              </button>
            ))}
          </div>
        </div>

        {loading && <div className="p-10 text-center text-on-surface-variant" role="status">Loading your timeline…</div>}
        {!loading && error && (
          <div className="p-5 rounded-xl bg-error-container text-on-error-container" role="alert">
            <p>{error.message}</p>
            {error.retryable && <button type="button" onClick={() => loadTimeline()} className="mt-3 px-4 py-2 bg-white rounded-lg border border-error/20">Retry</button>}
          </div>
        )}
        {!loading && !error && items.length === 0 && (
          <div className="p-10 text-center rounded-2xl border border-dashed border-outline-variant text-on-surface-variant" role="status">
            No {view === 'history' ? 'Drive events' : 'current memories'} are available for this account yet.
          </div>
        )}
        {!loading && !error && items.length > 0 && (
          <div className="relative space-y-4 before:absolute before:left-[37px] before:top-6 before:bottom-6 before:w-px before:bg-outline-variant/40">
            {items.map((item, index) => <TimelineRow key={`${item.title}-${item.event_date}-${index}`} item={item} />)}
          </div>
        )}
      </div>
    </main>
  );
}

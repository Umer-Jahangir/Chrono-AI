import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { DriveTitle, OpenDriveButton } from '../components/common/DriveLink';
import { ApiError, chronoApi } from '../lib/apiClient';
import { formatChronoDate, formatRelativeTime } from '../lib/format';

const ranges = [
  ['this_week', 'This week'],
  ['last_7_days', 'Last 7 days'],
  ['last_30_days', 'Last 30 days'],
];
const eventTypes = [
  ['created', 'Created', 'bg-emerald-500'],
  ['modified', 'Modified', 'bg-blue-500'],
  ['moved', 'Moved', 'bg-violet-500'],
  ['trashed', 'Trashed', 'bg-amber-500'],
  ['restored', 'Restored', 'bg-teal-500'],
  ['deleted', 'Deleted', 'bg-rose-500'],
];

function driveState(status, error) {
  if (error) return { label: 'Unavailable', color: 'bg-warning' };
  if (!status) return { label: 'Loading', color: 'bg-outline' };
  if (status.status === 'error') return { label: 'Error', color: 'bg-error' };
  if ((status.drive_events || 0) > 0 || (status.indexed_items || 0) > 0) {
    return { label: 'Connected', color: 'bg-success' };
  }
  return { label: 'Ready', color: 'bg-primary' };
}

function fileIcon(item) {
  if (item.item_type === 'folder') return 'folder';
  if (item.mime_type === 'application/pdf') return 'picture_as_pdf';
  if (item.mime_type?.startsWith('image/')) return 'image';
  if (item.mime_type?.includes('sheet')) return 'table_view';
  return 'description';
}

function LoadingCard({ label }) {
  return (
    <div className="flex min-h-44 items-center justify-center rounded-2xl border border-outline-variant/30 bg-white p-6" role="status">
      <span className="material-symbols-outlined animate-spin text-3xl text-primary" aria-hidden="true">progress_activity</span>
      <span className="ml-3 text-sm text-on-surface-variant">{label}</span>
    </div>
  );
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const [question, setQuestion] = useState('');
  const [range, setRange] = useState('this_week');
  const [status, setStatus] = useState(null);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const inFlight = useRef(false);

  useEffect(() => {
    let disposed = false;
    let controller = null;
    const refresh = async () => {
      if (document.hidden || inFlight.current) return;
      inFlight.current = true;
      controller = new AbortController();
      setError(null);
      setIsLoading(true);
      try {
        const [nextStatus, nextSummary] = await Promise.all([
          chronoApi.driveStatus({ signal: controller.signal }),
          chronoApi.dashboardSummary(range, { signal: controller.signal }),
        ]);
        if (!disposed) {
          setStatus(nextStatus);
          setSummary(nextSummary);
        }
      } catch (requestError) {
        if (!disposed && !(requestError instanceof ApiError && requestError.message === 'The request was cancelled.')) {
          setError(requestError);
        }
      } finally {
        inFlight.current = false;
        if (!disposed) setIsLoading(false);
      }
    };
    const onVisibilityChange = () => { if (!document.hidden) refresh(); };
    refresh();
    const interval = window.setInterval(refresh, 45_000);
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      disposed = true;
      controller?.abort();
      window.clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      inFlight.current = false;
    };
  }, [range, refreshKey]);

  const openSearch = (value = question) => {
    const trimmed = value.trim();
    if (trimmed.length >= 2) navigate('/search', { state: { question: trimmed } });
  };
  const connection = driveState(status, error);
  const days = summary?.days || [];
  const maxTotal = Math.max(1, ...days.map((day) => day.total || 0));
  const recentItems = summary?.recent_items || [];

  return (
    <div className="w-full min-w-0 overflow-x-hidden">
      <section className="relative flex min-h-[360px] w-full items-center justify-center overflow-hidden px-4 py-14 sm:px-8">
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="h-[34rem] w-[34rem] rounded-full bg-primary/10 opacity-60 blur-[100px]" />
        </div>
        <div className="relative z-10 mx-auto flex w-full max-w-4xl min-w-0 flex-col items-center gap-5">
          <div className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-surface-container-low px-4 py-1.5">
            <span className="h-2 w-2 rounded-full bg-primary" />
            <span className="text-xs font-semibold text-primary">Authenticated Chrono search</span>
          </div>
          <h1 className="text-center text-3xl font-bold leading-tight text-on-surface sm:text-5xl">
            Ask anything about your <span className="text-primary">digital memory.</span>
          </h1>
          <form className="relative w-full min-w-0" onSubmit={(event) => { event.preventDefault(); openSearch(); }}>
            <div className="flex min-w-0 items-center gap-2 rounded-2xl border border-outline-variant/40 bg-white/90 p-2 shadow-xl backdrop-blur-xl focus-within:border-primary/50 focus-within:ring-4 focus-within:ring-primary/10">
              <span className="material-symbols-outlined ml-2 flex-shrink-0 text-primary" aria-hidden="true">search</span>
              <label className="sr-only" htmlFor="dashboard-question">Ask Chrono</label>
              <input
                id="dashboard-question"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                className="min-w-0 flex-1 bg-transparent px-2 py-3 text-sm outline-none sm:text-base"
                placeholder="Ask about your Drive files, activity, owners, or dates…"
              />
              <button type="submit" disabled={question.trim().length < 2} className="inline-flex h-11 flex-shrink-0 items-center justify-center gap-2 rounded-xl bg-primary px-4 text-sm font-semibold text-white transition hover:bg-on-primary-fixed-variant active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 sm:px-6">
                <span className="hidden sm:inline">Search</span>
                <span className="material-symbols-outlined text-[20px]" aria-hidden="true">arrow_forward</span>
              </button>
            </div>
          </form>
          <div className="flex max-w-full flex-wrap items-center justify-center gap-2">
            {['Show my PDF files', 'What changed this week?', 'How many files do I have?'].map((suggestion) => (
              <button key={suggestion} type="button" onClick={() => openSearch(suggestion)} className="rounded-full border border-outline-variant/30 bg-white/70 px-3 py-2 text-xs text-on-surface transition hover:border-primary/40 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40">
                {suggestion}
              </button>
            ))}
          </div>
        </div>
      </section>

      <div className="mx-auto w-full max-w-7xl space-y-8 px-4 pb-12 sm:px-6 lg:px-8">
        <section aria-labelledby="connections-heading">
          <div className="mb-4">
            <h2 id="connections-heading" className="text-2xl font-bold text-on-surface">Neural Connections</h2>
            <p className="mt-1 text-sm text-on-surface-variant">Real integration health from your authenticated account.</p>
          </div>
          {isLoading && !status ? <LoadingCard label="Loading Google Drive status…" /> : (
            <div className="grid gap-4 md:grid-cols-[minmax(0,2fr)_minmax(16rem,1fr)]">
              <article className="min-w-0 rounded-2xl border border-primary/20 bg-white p-5 shadow-sm sm:p-6">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary material-symbols-outlined" aria-hidden="true">add_to_drive</span>
                    <div className="min-w-0">
                      <h3 className="font-semibold text-on-surface">Google Drive</h3>
                      <p className="mt-1 flex items-center gap-2 text-sm text-on-surface-variant">
                        <span className={`h-2 w-2 rounded-full ${connection.color}`} />{connection.label}
                      </p>
                    </div>
                  </div>
                  {error && <button type="button" onClick={() => setRefreshKey((value) => value + 1)} className="rounded-lg border border-warning/30 px-3 py-2 text-xs font-semibold text-on-surface hover:bg-warning-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40">Retry</button>}
                </div>
                {error ? (
                  <p className="mt-5 text-sm text-on-surface-variant" role="alert">{error.message}</p>
                ) : (
                  <dl className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {[
                      ['Drive events', status?.drive_events ?? 0],
                      ['Indexed items', status?.indexed_items ?? 0],
                      ['Memory chunks', status?.memory_chunks ?? 0],
                      ['Embedded chunks', status?.embedded_chunks ?? 0],
                    ].map(([label, value]) => (
                      <div key={label} className="rounded-xl bg-background p-3">
                        <dt className="text-xs text-on-surface-variant">{label}</dt>
                        <dd className="mt-1 text-xl font-bold text-on-surface">{value}</dd>
                      </div>
                    ))}
                  </dl>
                )}
                {status?.last_event_received_at && (
                  <p className="mt-4 text-xs text-on-surface-variant">
                    Last received {formatRelativeTime(status.last_event_received_at)} · {status.last_event_type || 'Drive event'}
                  </p>
                )}
              </article>
              <article className="rounded-2xl border border-dashed border-outline-variant bg-surface-container-low p-5 sm:p-6">
                <span className="material-symbols-outlined text-2xl text-on-surface-variant" aria-hidden="true">extension</span>
                <h3 className="mt-3 font-semibold text-on-surface">More sources</h3>
                <p className="mt-2 text-sm leading-6 text-on-surface-variant">Slack and Notion are <strong>Coming soon</strong>. Google Drive is the only active integration in this MVP.</p>
              </article>
            </div>
          )}
        </section>

        <section className="grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(20rem,0.8fr)]" aria-label="Drive activity dashboard">
          <article className="min-w-0 overflow-hidden rounded-2xl border border-outline-variant/30 bg-white p-4 shadow-sm sm:p-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-xl font-bold text-on-surface">Memory Pulse</h2>
                <p className="mt-1 text-sm text-on-surface-variant">Immutable Drive events by {summary?.timezone || 'application'} day.</p>
              </div>
              <label className="text-xs font-semibold text-on-surface-variant">
                <span className="sr-only">Activity range</span>
                <select value={range} onChange={(event) => setRange(event.target.value)} className="rounded-lg border border-outline-variant bg-white px-3 py-2 text-sm text-on-surface focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20">
                  {ranges.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
                </select>
              </label>
            </div>
            {isLoading && !summary ? <div className="mt-5"><LoadingCard label="Loading Drive activity…" /></div> : error && !summary ? (
              <div className="mt-6 rounded-xl bg-warning-bg p-4 text-sm text-on-surface-variant" role="alert">Activity is unavailable. Retry the dashboard request.</div>
            ) : (
              <>
                {summary?.event_count === 0 && (
                  <p className="mt-6 rounded-xl border border-dashed border-outline-variant p-4 text-center text-sm text-on-surface-variant" role="status">No Drive activity occurred in this range. Zero-activity days are shown below.</p>
                )}
                <div className="mt-6 flex h-48 min-w-0 items-end gap-1 overflow-x-auto border-b border-outline-variant/40 pb-2 sm:gap-2" aria-label={`${summary?.event_count || 0} Drive events in selected range`} role="img">
                  {days.map((day) => (
                    <div key={day.date} className="flex h-full min-w-7 flex-1 flex-col items-center justify-end gap-2" title={`${day.date}: ${day.total} events`}>
                      <div className="flex w-full max-w-10 flex-col-reverse overflow-hidden rounded-t bg-surface-container" style={{ height: `${Math.max(day.total ? 8 : 2, (day.total / maxTotal) * 100)}%` }}>
                        {eventTypes.map(([type, , color]) => day[type] > 0 && (
                          <span key={type} className={`${color} block w-full`} style={{ height: `${(day[type] / day.total) * 100}%` }} />
                        ))}
                      </div>
                      <span className="max-w-full truncate text-[10px] text-on-surface-variant">{new Date(`${day.date}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric' })}</span>
                    </div>
                  ))}
                </div>
                <ul className="mt-5 grid grid-cols-2 gap-2 text-xs sm:grid-cols-3" aria-label="Event totals">
                  {eventTypes.map(([type, label, color]) => (
                    <li key={type} className="flex items-center gap-2 text-on-surface-variant"><span className={`h-2.5 w-2.5 rounded-full ${color}`} />{label}: {summary?.event_counts?.[type] ?? 0}</li>
                  ))}
                </ul>
              </>
            )}
          </article>

          <article className="min-w-0 rounded-2xl border border-outline-variant/30 bg-white p-4 shadow-sm sm:p-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-xl font-bold text-on-surface">Recent Memories</h2>
                <p className="mt-1 text-xs text-on-surface-variant">Latest immutable Drive activity</p>
              </div>
              <Link to="/timeline" className="rounded text-xs font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40">View full history</Link>
            </div>
            {!isLoading && recentItems.length === 0 ? (
              <p className="mt-6 rounded-xl border border-dashed border-outline-variant p-5 text-center text-sm text-on-surface-variant" role="status">No Drive activity is available yet.</p>
            ) : (
              <ol className="mt-5 space-y-3">
                {recentItems.map((item, index) => (
                  <li key={`${item.title}-${item.event_date}-${index}`} className="min-w-0 rounded-xl border border-outline-variant/30 p-3">
                    <div className="flex min-w-0 items-start gap-3">
                      <span className="material-symbols-outlined flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary" aria-hidden="true">{fileIcon(item)}</span>
                      <div className="min-w-0 flex-1">
                        <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
                          <h3 className="min-w-0 break-words text-sm font-semibold text-on-surface"><DriveTitle title={item.title} openUrl={item.open_url} /></h3>
                          {item.event_date && <time className="whitespace-nowrap text-[11px] text-on-surface-variant" dateTime={item.event_date} title={formatChronoDate(item.event_date, summary?.timezone)}>{formatRelativeTime(item.event_date)}</time>}
                        </div>
                        <p className="mt-1 text-xs capitalize text-on-surface-variant">{item.event_type || 'Drive event'} · {item.item_type || 'file'}</p>
                        {item.excerpt && <p className="mt-2 line-clamp-2 break-words text-xs leading-5 text-on-surface-variant">{item.excerpt}</p>}
                        {item.open_url && <div className="mt-2"><OpenDriveButton title={item.title} openUrl={item.open_url} compact /></div>}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </article>
        </section>
      </div>
    </div>
  );
}

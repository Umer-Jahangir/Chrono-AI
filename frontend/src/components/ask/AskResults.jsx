import ReactMarkdown, { defaultUrlTransform } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import { DriveTitle, OpenDriveButton } from '../common/DriveLink';
import { formatChronoDate } from '../../lib/format';

const markdownSchema = {
  ...defaultSchema,
  tagNames: ['a', 'blockquote', 'br', 'code', 'em', 'h1', 'h2', 'h3', 'h4', 'li', 'ol', 'p', 'pre', 'strong', 'ul'],
  attributes: { a: ['href', 'title'] },
  protocols: { href: ['http', 'https'] },
};

function markdownUrlTransform(url) {
  try {
    const parsed = new URL(url, window.location.origin);
    if (parsed.protocol === 'https:' || parsed.protocol === 'http:') return defaultUrlTransform(url);
  } catch {
    return '';
  }
  return '';
}

const markdownComponents = {
  a: ({ href, children, ...props }) => (
    <a
      {...props}
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="font-medium text-primary underline decoration-primary/35 underline-offset-4 hover:decoration-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
    >
      {children}
    </a>
  ),
};

function labelForMime(mimeType, itemType) {
  if (itemType === 'folder') return 'Folder';
  if (!mimeType) return 'File';
  if (mimeType === 'application/pdf') return 'PDF';
  if (mimeType.includes('document') || mimeType.includes('word')) return 'Document';
  if (mimeType.includes('sheet') || mimeType.includes('csv')) return 'Spreadsheet';
  return mimeType;
}

export function ItemCard({ item, history = false }) {
  const primaryDate = history ? item.event_date : (item.modified_time || item.event_date);
  return (
    <article className="min-w-0 overflow-hidden rounded-2xl border border-border bg-white p-4 shadow-sm sm:p-5">
      <div className="flex min-w-0 items-start gap-3 sm:gap-4">
        <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary" aria-hidden="true">
          <span className="material-symbols-outlined">
            {item.item_type === 'folder' ? 'folder' : 'description'}
          </span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h3 className="min-w-0 max-w-full break-words text-base font-semibold text-text-main">
              <DriveTitle title={item.title} openUrl={item.open_url} />
            </h3>
            <span className="max-w-full break-all rounded bg-gray-100 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-text-muted">
              {labelForMime(item.mime_type, item.item_type)}
            </span>
          </div>
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted">
            {item.source && <span>Source: {item.source}</span>}
            {item.event_type && <span>Event: {item.event_type}</span>}
            {primaryDate && <time dateTime={primaryDate}>{formatChronoDate(primaryDate)}</time>}
          </div>
          {!history && (item.created_time || item.modified_time) && (
            <div className="mt-2 flex flex-wrap gap-x-4 text-xs text-text-muted">
              {item.created_time && <span>Created: {formatChronoDate(item.created_time)}</span>}
              {item.modified_time && <span>Modified: {formatChronoDate(item.modified_time)}</span>}
            </div>
          )}
          {item.owner_display_names?.length > 0 && (
            <p className="mt-2 break-words text-xs text-text-muted">
              Owner{item.owner_display_names.length === 1 ? '' : 's'}: {item.owner_display_names.join(', ')}
            </p>
          )}
          {item.excerpt && <p className="mt-3 break-words text-sm leading-6 text-text-muted">{item.excerpt}</p>}
          {item.open_url && <div className="mt-4"><OpenDriveButton title={item.title} openUrl={item.open_url} /></div>}
        </div>
      </div>
    </article>
  );
}

function sourcePassages(source) {
  if (Array.isArray(source.passages) && source.passages.length) return source.passages;
  return source.excerpt ? [{ citation: source.citation, excerpt: source.excerpt }] : [];
}

function Citations({ sources = [] }) {
  if (!sources.length) return null;
  return (
    <section aria-labelledby="sources-heading" className="mt-6 scroll-mt-24">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 id="sources-heading" className="text-lg font-bold text-text-main">Source documents</h2>
        <span className="text-xs text-text-muted">{sources.length} document{sources.length === 1 ? '' : 's'}</span>
      </div>
      <ol className="space-y-3">
        {sources.map((source, sourceIndex) => {
          const passages = sourcePassages(source);
          return (
            <li
              key={`${source.title}-${source.citation || sourceIndex}`}
              id={`source-citation-${source.citation || sourceIndex + 1}`}
              className="min-w-0 scroll-mt-24 overflow-hidden rounded-2xl border border-outline-variant/30 bg-surface-container-low p-4 sm:p-5"
            >
              <div className="flex min-w-0 items-start gap-3">
                <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-on-primary">
                  {source.citation || sourceIndex + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex min-w-0 flex-col items-start justify-between gap-3 sm:flex-row">
                    <div className="min-w-0">
                      <h3 className="max-w-full break-words text-sm font-semibold text-on-surface">
                        <DriveTitle title={source.title} openUrl={source.open_url} />
                      </h3>
                      {source.event_date && (
                        <time className="mt-1 block text-xs text-on-surface-variant" dateTime={source.event_date}>
                          {formatChronoDate(source.event_date)}
                        </time>
                      )}
                    </div>
                    <OpenDriveButton title={source.title} openUrl={source.open_url} compact />
                  </div>
                  {passages.length > 0 && (
                    <ol className="mt-4 space-y-3">
                      {passages.map((passage, passageIndex) => (
                        <li key={`${passage.citation}-${passageIndex}`} className="rounded-xl border border-outline-variant/25 bg-white/70 p-3">
                          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-primary">
                            Passage {passageIndex + 1} · Citation [{passage.citation}]
                          </p>
                          <p className="break-words text-sm leading-6 text-on-surface-variant">{passage.excerpt}</p>
                        </li>
                      ))}
                    </ol>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

export default function AskResults({ response }) {
  if (!response) return null;
  const items = Array.isArray(response.items) ? response.items : [];
  const sources = Array.isArray(response.sources) ? response.sources : [];
  const isHistory = response.intent === 'event_history';
  const isUnsupported = response.intent === 'unsupported';
  const showEmpty = !isUnsupported
    && !['content_question', 'aggregate'].includes(response.intent)
    && items.length === 0
    && sources.length === 0;

  return (
    <div data-testid="ask-response" className="min-w-0 space-y-5 overflow-hidden">
      <section className={`scroll-mt-24 overflow-hidden rounded-2xl border p-5 shadow-sm sm:p-6 ${isUnsupported ? 'border-warning/30 bg-warning-bg' : 'border-border bg-white'}`}>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-primary">
            {isUnsupported ? 'Capability unavailable' : 'Chrono answer'}
          </p>
          {response.retrieval_mode && (
            <span className="max-w-full break-all rounded-full bg-background px-2.5 py-1 text-[10px] uppercase tracking-wider text-text-muted">
              {response.retrieval_mode}
            </span>
          )}
        </div>
        <div className="chrono-markdown max-w-[76ch] break-words text-base leading-7 text-text-main">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[[rehypeSanitize, markdownSchema]]}
            urlTransform={markdownUrlTransform}
            components={markdownComponents}
          >
            {response.answer || 'Chrono returned no answer.'}
          </ReactMarkdown>
        </div>
      </section>

      {showEmpty && (
        <div className="rounded-xl border border-dashed border-outline-variant p-8 text-center text-text-muted" role="status">
          No matching Chrono items were found. Try a broader question.
        </div>
      )}

      {items.length > 0 && (
        <section aria-labelledby="items-heading" className="scroll-mt-24">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 id="items-heading" className="text-lg font-bold text-text-main">
              {isHistory ? 'Event history' : 'Matching items'}
            </h2>
            <span className="text-sm text-text-muted">{items.length} result{items.length === 1 ? '' : 's'}</span>
          </div>
          <div className="space-y-3">
            {items.map((item, index) => (
              <ItemCard key={`${item.title}-${item.event_date || item.modified_time || index}`} item={item} history={isHistory} />
            ))}
          </div>
        </section>
      )}

      <Citations sources={sources} />
    </div>
  );
}

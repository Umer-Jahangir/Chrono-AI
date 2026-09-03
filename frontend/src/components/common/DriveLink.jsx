function titleText(title) {
  return title || 'Untitled item';
}

export function DriveTitle({ title, openUrl, className = '' }) {
  if (!openUrl) return <span className={className}>{titleText(title)}</span>;
  return (
    <a
      href={openUrl}
      target="_blank"
      rel="noopener noreferrer"
      className={`${className} rounded-sm underline decoration-primary/35 underline-offset-4 hover:text-primary hover:decoration-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40`}
      title={`Open ${titleText(title)} in Google Drive in a new tab`}
    >
      {titleText(title)}
    </a>
  );
}

export function OpenDriveButton({ title, openUrl, compact = false }) {
  if (!openUrl) return null;
  return (
    <a
      href={openUrl}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-lg border border-primary/25 bg-primary/5 px-3 py-2 text-xs font-semibold text-primary transition hover:border-primary/50 hover:bg-primary/10 active:translate-y-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
      aria-label={`Open ${titleText(title)} in Google Drive (opens in a new tab)`}
    >
      <span className="material-symbols-outlined text-[18px]" aria-hidden="true">open_in_new</span>
      {!compact && <span>Open in Google Drive</span>}
    </a>
  );
}

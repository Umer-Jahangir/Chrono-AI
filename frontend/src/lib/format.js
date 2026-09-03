export function formatChronoDate(value, timeZone) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
    ...(timeZone ? { timeZone } : {}),
  }).format(date);
}

export function formatRelativeTime(value, now = Date.now()) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const seconds = Math.round((date.getTime() - now) / 1000);
  const ranges = [
    [60, 'second'], [60, 'minute'], [24, 'hour'], [7, 'day'], [5, 'week'], [12, 'month'],
  ];
  let amount = seconds;
  for (const [boundary, unit] of ranges) {
    if (Math.abs(amount) < boundary) {
      return new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(amount, unit);
    }
    amount = Math.round(amount / boundary);
  }
  return new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(amount, 'year');
}

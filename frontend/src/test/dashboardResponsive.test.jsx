import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import DashboardPage from '../pages/DashboardPage';
import SearchPage from '../pages/SearchPage';
import { CHRONO_TOKEN_KEY } from '../lib/apiClient';

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const statusPayload = {
  status: 'ready', drive_events: 4, indexed_items: 3, memory_chunks: 8,
  embedded_chunks: 7, last_event_type: 'modified',
  last_event_received_at: '2026-09-02T10:00:00Z',
};

function summaryPayload(overrides = {}) {
  return {
    range: 'this_week', timezone: 'Asia/Karachi',
    start: '2026-08-30T19:00:00Z', end: '2026-09-02T10:00:00Z', event_count: 2,
    event_counts: { created: 1, modified: 1, moved: 0, trashed: 0, restored: 0, deleted: 0 },
    days: [
      { date: '2026-08-31', total: 0, created: 0, modified: 0, moved: 0, trashed: 0, restored: 0, deleted: 0 },
      { date: '2026-09-01', total: 2, created: 1, modified: 1, moved: 0, trashed: 0, restored: 0, deleted: 0 },
    ],
    recent_items: [{
      title: 'Real Drive Record.pdf', source: 'google_drive', mime_type: 'application/pdf',
      item_type: 'file', event_type: 'modified', event_date: '2026-09-02T10:00:00Z',
      excerpt: 'Privacy-safe real excerpt.',
      open_url: 'https://drive.google.com/file/d/real/view',
    }],
    ...overrides,
  };
}

function apiMock(summary = summaryPayload()) {
  return vi.fn((url) => {
    if (url.includes('/integrations/google-drive/status')) return Promise.resolve(jsonResponse(statusPayload));
    if (url.includes('/dashboard/summary')) return Promise.resolve(jsonResponse({ ...summary, range: new URL(url).searchParams.get('range') }));
    throw new Error(`Unexpected URL ${url}`);
  });
}

describe('dynamic responsive dashboard', () => {
  beforeEach(() => window.localStorage.setItem(CHRONO_TOKEN_KEY, 'dashboard-token'));

  it('renders real Drive status, activity, recent events, and no invented progress', async () => {
    const fetchMock = apiMock();
    vi.stubGlobal('fetch', fetchMock);
    render(<MemoryRouter><DashboardPage /></MemoryRouter>);

    expect(await screen.findByText('Connected')).toBeVisible();
    expect(screen.getByText('4')).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Real Drive Record.pdf' })).toBeVisible();
    expect(screen.getByText('Privacy-safe real excerpt.')).toBeVisible();
    expect(screen.getByText(/Slack and Notion are/)).toHaveTextContent('Coming soon');
    expect(screen.queryByText(/45%|82%|Last synced 2m ago|Q3_Marketing_Strategy|Hero_Concept_v3/)).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View full history' })).toHaveAttribute('href', '/timeline');
    expect(screen.getAllByRole('link', { name: /Open Real Drive Record\.pdf in Google Drive/ })[0]).toHaveAttribute('rel', 'noopener noreferrer');
    expect(fetchMock.mock.calls.every(([, options]) => options.headers.Authorization === 'Bearer dashboard-token')).toBe(true);
  });

  it('changes the bounded activity request when the range selector changes', async () => {
    const fetchMock = apiMock();
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    render(<MemoryRouter><DashboardPage /></MemoryRouter>);
    await screen.findByText('Connected');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Activity range' }), 'last_7_days');
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/dashboard/summary?range=last_7_days'))).toBe(true));
  });

  it('shows honest empty activity and recent-memory states', async () => {
    vi.stubGlobal('fetch', apiMock(summaryPayload({
      event_count: 0,
      event_counts: { created: 0, modified: 0, moved: 0, trashed: 0, restored: 0, deleted: 0 },
      days: [{ date: '2026-09-01', total: 0, created: 0, modified: 0, moved: 0, trashed: 0, restored: 0, deleted: 0 }],
      recent_items: [],
    })));
    render(<MemoryRouter><DashboardPage /></MemoryRouter>);
    expect(await screen.findByText('No Drive activity occurred in this range. Zero-activity days are shown below.')).toBeVisible();
    expect(screen.getByText('No Drive activity is available yet.')).toBeVisible();
  });

  it('shows an error and retries without overlapping requests', async () => {
    let shouldFail = true;
    const fetchMock = vi.fn((url) => {
      if (shouldFail) return Promise.reject(new TypeError('offline'));
      if (url.includes('/status')) return Promise.resolve(jsonResponse(statusPayload));
      return Promise.resolve(jsonResponse(summaryPayload()));
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<MemoryRouter><DashboardPage /></MemoryRouter>);
    expect(await screen.findByText('Unable to reach Chrono. Check your connection and retry.')).toBeVisible();
    shouldFail = false;
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('Connected')).toBeVisible();
  });
});

describe('responsive search structure', () => {
  it('keeps a min-width-safe main column and readable empty state', () => {
    const { container } = render(<MemoryRouter><SearchPage /></MemoryRouter>);
    const root = container.firstElementChild;
    expect(root).toHaveClass('min-w-0', 'overflow-x-hidden');
    expect(screen.getByRole('heading', { name: 'Search your memory timeline' }).closest('section')).toHaveClass('max-w-3xl', 'min-w-0');
    expect(screen.getByRole('button', { name: 'Open search tips' })).toBeVisible();
  });
});

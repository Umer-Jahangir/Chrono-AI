import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import SearchPage from '../pages/SearchPage';
import TimelinePage from '../pages/TimelinePage';
import { CHRONO_TOKEN_KEY } from '../lib/apiClient';

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const emptyAsk = {
  answer: 'Chrono found 0 items.', retrieval_mode: 'structured', intent: 'file_discovery',
  interpreted_filters: {}, items: [], sources: [],
};

describe('authenticated search workspace', () => {
  beforeEach(() => window.localStorage.setItem(CHRONO_TOKEN_KEY, 'search-token'));

  it('prevents empty submissions and sends the exact authenticated /ask schema', async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse({ ...emptyAsk, answer: 'Chrono found 3 files.', intent: 'aggregate' })));
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    render(<MemoryRouter><SearchPage /></MemoryRouter>);
    const input = screen.getByLabelText('Ask Chrono about your files and timeline');
    const submit = screen.getByRole('button', { name: 'Search' });
    expect(submit).toBeDisabled();
    await user.type(input, 'How many PDF files do I have?');
    await user.click(submit);
    expect(await screen.findByText('Chrono found 3 files.')).toBeVisible();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe('http://localhost:8000/ask');
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe('Bearer search-token');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ question: 'How many PDF files do I have?', limit: 10 });
  });

  it('shows loading, disables duplicate submission, and then renders results', async () => {
    let resolveFetch;
    const fetchMock = vi.fn(() => new Promise((resolve) => { resolveFetch = resolve; }));
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    render(<MemoryRouter><SearchPage /></MemoryRouter>);
    await user.type(screen.getByLabelText('Ask Chrono about your files and timeline'), 'Show my PDFs');
    const submit = screen.getByRole('button', { name: 'Search' });
    await user.click(submit);
    expect(screen.getByText('Searching your Chrono memories…')).toBeVisible();
    expect(submit).toBeDisabled();
    fireEvent.click(submit);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await act(async () => resolveFetch(jsonResponse(emptyAsk)));
    expect(await screen.findByText('No matching Chrono items were found. Try a broader question.')).toBeVisible();
  });

  it('clears a rejected session when /ask returns 401', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ detail: 'Authentication required' }, 401))));
    const user = userEvent.setup();
    render(<MemoryRouter><SearchPage /></MemoryRouter>);
    await user.type(screen.getByLabelText('Ask Chrono about your files and timeline'), 'Show my PDFs');
    await user.click(screen.getByRole('button', { name: 'Search' }));
    expect(await screen.findByText('Your session expired. Please sign in again.')).toBeVisible();
    expect(window.localStorage.getItem(CHRONO_TOKEN_KEY)).toBeNull();
  });

  it('shows a retry action for network and server failures', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('offline'))));
    const user = userEvent.setup();
    render(<MemoryRouter><SearchPage /></MemoryRouter>);
    await user.type(screen.getByLabelText('Ask Chrono about your files and timeline'), 'Show my PDFs');
    await user.click(screen.getByRole('button', { name: 'Search' }));
    expect(await screen.findByText('Unable to reach Chrono. Check your connection and retry.')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeVisible();
  });
});

describe('authenticated timeline', () => {
  beforeEach(() => window.localStorage.setItem(CHRONO_TOKEN_KEY, 'timeline-token'));

  it('loads current memories and immutable history with bearer authentication', async () => {
    const fetchMock = vi.fn((url) => {
      if (url.includes('/timeline/history')) return Promise.resolve(jsonResponse({
        view: 'history', count: 1, items: [{ title: 'History.pdf', source: 'google_drive', event_type: 'deleted', event_date: '2026-08-30T10:00:00Z', item_type: 'file', open_url: null }],
      }));
      return Promise.resolve(jsonResponse({
        view: 'current', count: 1, items: [{ title: 'Current.pdf', source: 'google_drive', event_type: 'modified', event_date: '2026-08-29T10:00:00Z', mime_type: 'application/pdf', item_type: 'file', open_url: 'https://drive.google.com/file/d/current/view' }],
      }));
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<TimelinePage />);
    expect(await screen.findByRole('heading', { name: 'Current.pdf' })).toBeVisible();
    expect(screen.getByRole('link', { name: /Open Current\.pdf in Google Drive/ })).toHaveAttribute('target', '_blank');
    fireEvent.click(screen.getByRole('tab', { name: 'history' }));
    expect(await screen.findByRole('heading', { name: 'History.pdf' })).toBeVisible();
    expect(fetchMock.mock.calls.every(([, options]) => options.headers.Authorization === 'Bearer timeline-token')).toBe(true);
    expect(screen.queryByText('<not rendered>')).not.toBeInTheDocument();
  });

  it('shows an empty timeline state', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ view: 'current', count: 0, items: [] }))));
    render(<TimelinePage />);
    expect(await screen.findByText('No current memories are available for this account yet.')).toBeVisible();
  });
});

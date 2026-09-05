import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import AskResults from '../components/ask/AskResults';

const base = { retrieval_mode: 'structured', interpreted_filters: {}, sources: [], items: [] };

describe('/ask result rendering', () => {
  it('renders a grounded content answer and numbered citations', () => {
    render(<AskResults response={{
      ...base,
      intent: 'content_question',
      retrieval_mode: 'hybrid',
      answer: 'Whiskers needs 55 grams of food [1].',
      sources: [{
        citation: 1,
        title: 'Feline Care Guide',
        excerpt: 'Whiskers purrs and needs 55 grams of food.',
        event_date: '2026-08-29T10:00:00Z',
      }],
    }} />);
    expect(screen.getByText('Whiskers needs 55 grams of food [1].')).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Feline Care Guide' })).toBeVisible();
    expect(screen.getByText('Whiskers purrs and needs 55 grams of food.')).toBeVisible();
  });

  it('renders a cited lexical-extractive fallback honestly', () => {
    render(<AskResults response={{
      ...base,
      intent: 'content_question',
      retrieval_mode: 'lexical-extractive',
      answer: 'The most relevant Chrono memory passage is [1].',
      sources: [{ citation: 1, title: 'Evidence.txt', excerpt: 'Supported evidence.', event_date: '2026-08-29T10:00:00Z' }],
    }} />);
    expect(screen.getByText('lexical-extractive')).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Evidence.txt' })).toBeVisible();
  });

  it('renders structured file discovery fields without raw metadata', () => {
    render(<AskResults response={{
      ...base,
      intent: 'file_discovery',
      answer: 'Chrono found 1 item.',
      items: [{
        title: 'Project.pdf', source: 'google_drive', mime_type: 'application/pdf',
        item_type: 'file', event_type: 'modified', created_time: '2026-08-01T10:00:00Z',
        modified_time: '2026-08-29T10:00:00Z', owner_display_names: ['Fixture Owner'],
      }],
    }} />);
    expect(screen.getByRole('heading', { name: 'Project.pdf' })).toBeVisible();
    expect(screen.getByText('PDF')).toBeVisible();
    expect(screen.getByText('Owner: Fixture Owner')).toBeVisible();
    expect(screen.queryByText(/metadata_json/i)).not.toBeInTheDocument();
  });

  it('renders content-search items and excerpts', () => {
    render(<AskResults response={{
      ...base,
      intent: 'content_search', answer: 'Chrono found 1 relevant document.',
      items: [{ title: 'Resume.pdf', source: 'google_drive', mime_type: 'application/pdf', item_type: 'file', excerpt: 'Python and Django experience.' }],
    }} />);
    expect(screen.getByText('Python and Django experience.')).toBeVisible();
  });

  it('renders aggregate answers without expecting result items', () => {
    render(<AskResults response={{ ...base, intent: 'aggregate', answer: 'Chrono found 3 files.' }} />);
    expect(screen.getByText('Chrono found 3 files.')).toBeVisible();
    expect(screen.queryByRole('heading', { name: 'Matching items' })).not.toBeInTheDocument();
  });

  it('renders event history in backend order', () => {
    render(<AskResults response={{
      ...base, intent: 'event_history', answer: 'Chrono found 2 Drive events.',
      items: [
        { title: 'Report.pdf', source: 'google_drive', item_type: 'file', event_type: 'deleted', event_date: '2026-08-30T10:00:00Z' },
        { title: 'Report.pdf', source: 'google_drive', item_type: 'file', event_type: 'created', event_date: '2026-08-29T10:00:00Z' },
      ],
    }} />);
    const events = screen.getAllByText(/Event:/).map((node) => node.textContent);
    expect(events).toEqual(['Event: deleted', 'Event: created']);
  });

  it('displays unsupported capability explanations as answers, not errors', () => {
    render(<AskResults response={{ ...base, intent: 'unsupported', answer: 'Chrono cannot determine sender information.' }} />);
    expect(screen.getByText('Capability unavailable')).toBeVisible();
    expect(screen.getByText('Chrono cannot determine sender information.')).toBeVisible();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows an empty-result state for a completed discovery query', () => {
    render(<AskResults response={{ ...base, intent: 'file_discovery', answer: 'Chrono found 0 items.' }} />);
    expect(screen.getByText('No matching Chrono items were found. Try a broader question.')).toBeVisible();
  });

  it('drops hostile answer HTML and keeps titles and excerpts inert', () => {
    const { container } = render(<AskResults response={{
      ...base,
      intent: 'content_question',
      answer: '<img src=x onerror=alert(1)>',
      sources: [{ citation: 1, title: '<script>alert(1)</script>', excerpt: '<a href="javascript:alert(1)">open</a>', event_date: '2026-08-29T10:00:00Z' }],
    }} />);
    expect(screen.queryByText('<img src=x onerror=alert(1)>')).not.toBeInTheDocument();
    expect(screen.getByText('<script>alert(1)</script>')).toBeVisible();
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('a')).toBeNull();
  });

  it('renders safe Markdown headings, emphasis, lists, and links', () => {
    render(<AskResults response={{
      ...base,
      intent: 'content_question',
      answer: '### Technical Skills\n\n**Backend:**\n\n- Python\n- Django\n\n[Reference](https://example.com)',
    }} />);
    expect(screen.getByRole('heading', { name: 'Technical Skills' })).toBeVisible();
    expect(screen.getByText('Backend:').tagName).toBe('STRONG');
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    expect(screen.getByRole('link', { name: 'Reference' })).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('rejects executable Markdown URLs', () => {
    const { container } = render(<AskResults response={{
      ...base, intent: 'content_question', answer: '[Run this](javascript:alert(1))',
    }} />);
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
  });

  it('renders validated Drive links and omits links when open_url is missing', () => {
    const safeUrl = 'https://drive.google.com/file/d/fixture/view';
    render(<AskResults response={{
      ...base,
      intent: 'file_discovery',
      answer: 'Chrono found 2 items.',
      items: [
        { title: 'Linked.pdf', source: 'google_drive', item_type: 'file', open_url: safeUrl },
        { title: 'Unlinked.pdf', source: 'google_drive', item_type: 'file', open_url: null },
      ],
    }} />);
    const titleLink = screen.getByRole('link', { name: 'Linked.pdf' });
    expect(titleLink).toHaveAttribute('href', safeUrl);
    expect(titleLink).toHaveAttribute('target', '_blank');
    expect(titleLink).toHaveAttribute('rel', 'noopener noreferrer');
    expect(screen.getByRole('heading', { name: 'Unlinked.pdf' }).querySelector('a')).toBeNull();
    expect(screen.getAllByRole('link')).toHaveLength(2);
  });

  it('does not render unsafe or lookalike Drive URLs as links', () => {
    render(<AskResults response={{
      ...base,
      intent: 'file_discovery',
      answer: 'Chrono found 2 items.',
      items: [
        { title: 'Unsafe.pdf', source: 'google_drive', item_type: 'file', open_url: 'javascript:alert(1)' },
        { title: 'Lookalike.pdf', source: 'google_drive', item_type: 'file', open_url: 'https://drive.google.com.evil.test/file' },
      ],
    }} />);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Unsafe.pdf' }).querySelector('a')).toBeNull();
  });

  it('groups multiple cited passages beneath one linked source document', () => {
    const safeUrl = 'https://docs.google.com/document/d/fixture/edit';
    render(<AskResults response={{
      ...base,
      intent: 'content_question',
      answer: 'Supported by two passages [1] [2].',
      sources: [{
        citation: 1, title: 'Grouped Source', event_date: '2026-08-29T10:00:00Z',
        open_url: safeUrl,
        passages: [
          { citation: 1, excerpt: 'First [REDACTED EMAIL] passage.' },
          { citation: 2, excerpt: 'Second [REDACTED PHONE] passage.' },
        ],
      }],
    }} />);
    expect(screen.getByText('1 document')).toBeVisible();
    expect(screen.getByText('First [REDACTED EMAIL] passage.')).toBeVisible();
    expect(screen.getByText('Second [REDACTED PHONE] passage.')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Grouped Source' })).toHaveAttribute('href', safeUrl);
    expect(screen.queryByText(/fixture@example/i)).not.toBeInTheDocument();
  });

  it('renders only finalized sources without orphan citation labels', () => {
    render(<AskResults response={{
      ...base,
      intent: 'content_question',
      retrieval_mode: 'hybrid',
      answer: 'Python and Django [1]; computer vision [2].',
      sources: [{
        citation: 1, title: 'Resume.pdf', event_date: '2026-08-29T10:00:00Z',
        passages: [
          { citation: 1, excerpt: 'Python and Django.' },
          { citation: 2, excerpt: 'Computer vision.' },
        ],
      }],
    }} />);
    expect(screen.getByText('1 document')).toBeVisible();
    expect(screen.getByText(/Citation \[1\]/)).toBeVisible();
    expect(screen.getByText(/Citation \[2\]/)).toBeVisible();
    expect(screen.queryByText(/\[3\]|\[4\]/)).not.toBeInTheDocument();
    expect(screen.queryByText('fyp.txt')).not.toBeInTheDocument();
  });

  it('renders every finalized group for a genuinely multi-document answer', () => {
    render(<AskResults response={{
      ...base,
      intent: 'content_question', retrieval_mode: 'hybrid', answer: 'Two facts [1] [2].',
      sources: [
        { citation: 1, title: 'First.pdf', excerpt: 'First fact.', event_date: '2026-08-29T10:00:00Z' },
        { citation: 2, title: 'Second.pdf', excerpt: 'Second fact.', event_date: '2026-08-30T10:00:00Z' },
      ],
    }} />);
    expect(screen.getByText('2 documents')).toBeVisible();
    expect(screen.getByRole('heading', { name: 'First.pdf' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Second.pdf' })).toBeVisible();
  });
});

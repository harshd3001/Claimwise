import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from './client';

afterEach(() => vi.restoreAllMocks());

describe('typed API client', () => {
  it('loads categories from the public category catalog endpoint', async () => {
    const categories = [
      { id: 'category-meals', name: 'Meals' },
      { id: 'category-travel', name: 'Travel' },
    ];
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(categories), { status: 200 }),
    );

    await expect(api.categories()).resolves.toEqual(categories);
    expect(fetchMock.mock.calls[0][0]).toBe('/api/categories');
  });

  it('sends the demo identity and quoted version precondition on mutations', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ id: 'c1' }), { status: 200 }));
    await api.action('manager-demo', 'c1', 7, 'approve', { approved_amount_paise: 4500 });
    const [, options] = fetchMock.mock.calls[0];
    const headers = new Headers(options?.headers);
    expect(headers.get('X-Demo-User-ID')).toBe('manager-demo');
    expect(headers.get('If-Match')).toBe('"7"');
    expect(options?.method).toBe('POST');
    expect(JSON.parse(String(options?.body))).toEqual({ approved_amount_paise: 4500 });
  });

  it('surfaces stale-version responses as actionable API errors', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      code: 'stale_version',
      message: 'Old server message',
    }), { status: 412, headers: { 'Content-Type': 'application/json' } }));
    await expect(api.action('manager-demo', 'c1', 1, 'reject', { comment: 'Please clarify' }))
      .rejects.toMatchObject({
        status: 412,
        code: 'stale_version',
        message: 'This claim changed since you opened it. Reload the latest version before deciding.',
      });
  });

  it('preserves server field validation details', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      code: 'invalid_claim',
      message: 'Please correct the claim.',
      fields: { merchant: 'Required' },
    }), { status: 422, headers: { 'Content-Type': 'application/json' } }));
    await expect(api.create('employee-demo', {
      merchant: '', category: 'Travel', category_id: null, description: 'Meeting', expense_date: '2026-10-01', amount_paise: 100,
    })).rejects.toMatchObject({ status: 422, fields: { merchant: 'Required' } });
  });

  it.each([
    [401, 'Your demo identity is missing or no longer valid. Choose an identity and try again.'],
    [403, 'This action is not available for the selected demo role.'],
    [404, 'This claim is no longer available. Return to the list and refresh.'],
    [409, 'This claim can no longer make that transition. Reload it to see the latest status.'],
    [428, 'The latest claim version is required. Reload the claim before trying again.'],
  ])('provides a clear recovery message for HTTP %i', async (status, message) => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      code: 'request_failed',
      message: 'The request could not be completed.',
    }), { status, headers: { 'Content-Type': 'application/json' } }));
    await expect(api.claims('employee-demo')).rejects.toMatchObject({ status, message });
  });
});

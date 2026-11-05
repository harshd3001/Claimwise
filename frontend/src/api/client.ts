import type { ApiErrorBody, Claim, ClaimDetail, ClaimFields, ClaimList, DemoUser } from '../types';

export class ApiError extends Error {
  status: number;
  code: string;
  fields: Record<string, string>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message || 'The request could not be completed.');
    this.name = 'ApiError';
    this.status = status;
    this.code = body.code;
    this.fields = body.fields ?? {};
  }
}

type RequestOptions = {
  method?: string;
  userId?: string;
  version?: number | string;
  body?: unknown;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<{ data: T; etag: string | null }> {
  const headers = new Headers({ Accept: 'application/json' });
  if (options.body !== undefined) headers.set('Content-Type', 'application/json');
  if (options.userId) headers.set('X-Demo-User-ID', options.userId);
  if (options.version !== undefined) {
    const etag = String(options.version);
    headers.set('If-Match', etag.startsWith('"') ? etag : `"${etag}"`);
  }

  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method: options.method ?? 'GET',
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    throw new Error('We could not reach Claimwise. Check your connection and try again.');
  }

  if (!response.ok) {
    let body: ApiErrorBody = { code: 'request_failed', message: 'The request could not be completed.' };
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      // Keep a useful status-specific message if the server response is not JSON.
    }
    if (response.status === 401) body.message = 'Your demo identity is missing or no longer valid. Choose an identity and try again.';
    if (response.status === 403) body.message = 'This action is not available for the selected demo role.';
    if (response.status === 404) body.message = 'This claim is no longer available. Return to the list and refresh.';
    if (response.status === 409 && body.code === 'request_failed') body.message = 'This claim can no longer make that transition. Reload it to see the latest status.';
    if (response.status === 412) body.message = 'This claim changed since you opened it. Reload the latest version before deciding.';
    if (response.status === 422 && body.code === 'request_failed') body.message = 'Some details need attention. Review the fields and try again.';
    if (response.status === 428) body.message = 'The latest claim version is required. Reload the claim before trying again.';
    throw new ApiError(response.status, body);
  }

  if (response.status === 204) return { data: undefined as T, etag: response.headers.get('ETag') };
  return { data: (await response.json()) as T, etag: response.headers.get('ETag') };
}

const userPath = (userId?: string) => ({ userId });
const claimFromResponse = (data: Claim | ClaimDetail): Claim => 'claim' in data ? data.claim : data;

export const api = {
  async users(): Promise<DemoUser[]> {
    const { data } = await request<DemoUser[] | { items: DemoUser[] }>('/users');
    return Array.isArray(data) ? data : data.items;
  },
  async categories(): Promise<string[]> {
    const { data } = await request<string[]>('/categories');
    return data;
  },
  async me(userId: string): Promise<DemoUser> {
    const { data } = await request<DemoUser>('/me', userPath(userId));
    return data;
  },
  async claims(userId: string, status?: string): Promise<ClaimList> {
    const query = status && status !== 'all' ? `?status=${encodeURIComponent(status)}` : '';
    const { data } = await request<ClaimList>(`/claims${query}`, userPath(userId));
    return data;
  },
  async claim(userId: string, claimId: string): Promise<{ detail: ClaimDetail; etag: string | null }> {
    const { data, etag } = await request<ClaimDetail>(`/claims/${encodeURIComponent(claimId)}`, userPath(userId));
    return { detail: data, etag };
  },
  async create(userId: string, fields: ClaimFields): Promise<Claim> {
    const { data } = await request<Claim | ClaimDetail>('/claims', { method: 'POST', userId, body: fields });
    return claimFromResponse(data);
  },
  async update(userId: string, claimId: string, version: number | string, fields: Partial<ClaimFields>): Promise<Claim> {
    const { data } = await request<Claim | ClaimDetail>(`/claims/${encodeURIComponent(claimId)}`, {
      method: 'PATCH', userId, version, body: fields,
    });
    return claimFromResponse(data);
  },
  async remove(userId: string, claimId: string, version: number | string): Promise<void> {
    await request<void>(`/claims/${encodeURIComponent(claimId)}`, { method: 'DELETE', userId, version });
  },
  async action(userId: string, claimId: string, version: number | string, action: 'submit' | 'reopen' | 'approve' | 'reject' | 'mark-paid', body?: unknown): Promise<Claim> {
    const { data } = await request<Claim | ClaimDetail>(`/claims/${encodeURIComponent(claimId)}/${action}`, {
      method: 'POST', userId, version, body: body ?? {},
    });
    return claimFromResponse(data);
  },
};

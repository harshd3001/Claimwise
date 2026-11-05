import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import { ApiError, api } from './api/client';
import type { Claim, ClaimDetail, DemoUser } from './types';
import './index.css';

vi.mock('./api/client', () => ({
  ApiError: class ApiError extends Error {
    status: number;
    code: string;
    fields: Record<string, string>;
    constructor(status: number, body: { code: string; message: string; fields?: Record<string, string> }) {
      super(body.message);
      this.status = status;
      this.code = body.code;
      this.fields = body.fields ?? {};
    }
  },
  api: {
    users: vi.fn(),
    categories: vi.fn(),
    me: vi.fn(),
    claims: vi.fn(),
    claim: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    action: vi.fn(),
  },
}));

const employee: DemoUser = { id: 'employee-demo', name: 'Maya Employee', email: 'maya@example.test', role: 'employee' };
const manager: DemoUser = { id: 'manager-demo', name: 'User Manager', email: 'user-manager@example.test', role: 'user_manager' };
const submitted: Claim = {
  id: 'claim-1', employee_id: employee.id, merchant: 'Metro Cab', category: 'Travel', category_id: 'cat-travel', receipt_number: null,
  description: 'Client meeting in Bengaluru', expense_date: '2026-10-12', amount_paise: 245050,
  approved_amount_paise: null, status: 'submitted', version: 3, created_at: '2026-10-12T10:00:00Z',
  updated_at: '2026-10-13T10:00:00Z', deleted_at: null,
};
const detail: ClaimDetail = {
  claim: submitted,
  events: [{
    id: 'event-1', actor_id: employee.id, actor_name: employee.name, action: 'submitted',
    from_status: 'draft', to_status: 'submitted', comment: null, details: null, created_at: '2026-10-13T10:00:00Z',
  }],
};

async function setup(role: 'employee' | 'user_manager' = 'employee', claimItems: Claim[] = [submitted]) {
  const user = role === 'employee' ? employee : manager;
  vi.mocked(api.users).mockResolvedValue([employee, manager]);
  vi.mocked(api.me).mockResolvedValue(user);
  vi.mocked(api.claims).mockResolvedValue({ items: claimItems, total: claimItems.length });
  vi.mocked(api.claim).mockResolvedValue({ detail, etag: '"3"' });
  const userActions = userEvent.setup();
  render(<App />);
  await screen.findByRole('heading', { name: role === 'employee' ? 'My claims' : 'Review claims' });
  return userActions;
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  vi.mocked(api.categories).mockResolvedValue([
    { id: 'cat-meals', name: 'Meals' },
    { id: 'cat-travel', name: 'Travel' },
    { id: 'cat-accommodation', name: 'Accommodation' },
    { id: 'cat-office-supplies', name: 'Office supplies' },
    { id: 'cat-software', name: 'Software & subscriptions' },
    { id: 'cat-communication', name: 'Communication' },
    { id: 'cat-training', name: 'Training & education' },
    { id: 'cat-client-entertainment', name: 'Client entertainment' },
    { id: 'cat-other', name: 'Other' },
  ]);
  vi.mocked(api.create).mockResolvedValue({ ...submitted, status: 'draft' });
  vi.mocked(api.update).mockResolvedValue({ ...submitted, status: 'draft' });
  vi.mocked(api.action).mockResolvedValue(submitted);
});

describe('Claimwise journeys', () => {
  it('shows a loading state while the identity is being resolved', async () => {
    let resolveMe!: (user: DemoUser) => void;
    vi.mocked(api.users).mockResolvedValue([employee, manager]);
    vi.mocked(api.me).mockReturnValue(new Promise((resolve) => { resolveMe = resolve; }));
    vi.mocked(api.claims).mockResolvedValue({ items: [], total: 0 });
    render(<App />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading your Claimwise workspace');
    resolveMe(employee);
    expect(await screen.findByRole('heading', { name: 'My claims' })).toBeInTheDocument();
  });

  it('migrates a previously saved reviewer identity to User Manager', async () => {
    localStorage.setItem('claimwise-demo-user', 'approver-demo');
    vi.mocked(api.users).mockResolvedValue([employee, manager]);
    vi.mocked(api.me).mockResolvedValue(manager);
    vi.mocked(api.claims).mockResolvedValue({ items: [], total: 0 });

    render(<App />);

    expect(await screen.findByRole('heading', { name: 'Review claims' })).toBeInTheDocument();
    expect(localStorage.getItem('claimwise-demo-user')).toBe('manager-demo');
    expect(api.me).toHaveBeenCalledWith('manager-demo');
    expect(screen.getByRole('option', { name: 'User Manager — User Manager' })).toBeInTheDocument();
  });

  it('shows a labeled loading state while claims are being fetched', async () => {
    let resolveClaims!: (result: { items: Claim[]; total: number }) => void;
    vi.mocked(api.users).mockResolvedValue([employee, manager]);
    vi.mocked(api.me).mockResolvedValue(employee);
    vi.mocked(api.claims).mockReturnValue(new Promise((resolve) => { resolveClaims = resolve; }));
    render(<App />);
    await screen.findByRole('heading', { name: 'My claims' });
    expect(screen.getByRole('status')).toHaveTextContent('Loading claims');
    resolveClaims({ items: [], total: 0 });
    expect(await screen.findByText('Your claim list is clear')).toBeInTheDocument();
  });

  it('shows partial approved and paid amounts in claim cards but omits full approvals', async () => {
    const partialApproved: Claim = {
      ...submitted,
      id: 'claim-partial-approved',
      merchant: 'Partial approval',
      status: 'approved',
      approved_amount_paise: 200000,
    };
    const partialPaid: Claim = {
      ...partialApproved,
      id: 'claim-partial-paid',
      merchant: 'Partial payment',
      status: 'paid',
    };
    const fullyApproved: Claim = {
      ...partialApproved,
      id: 'claim-full-approved',
      merchant: 'Full approval',
      approved_amount_paise: submitted.amount_paise,
    };

    await setup('user_manager', [partialApproved, partialPaid, fullyApproved]);
    await userEvent.setup().click(screen.getByRole('button', { name: 'Reviewed' }));

    expect(screen.getByText('Approved ₹2,000.00 of ₹2,450.50')).toBeInTheDocument();
    expect(screen.getByText('Paid ₹2,000.00 of ₹2,450.50')).toBeInTheDocument();
    expect(screen.queryByText('Approved ₹2,450.50 of ₹2,450.50')).not.toBeInTheDocument();
  });

  it('validates required fields and amount precision before creating a draft', async () => {
    const user = await setup();
    await user.click(screen.getByRole('button', { name: '＋ New claim' }));
    expect(screen.getByRole('option', { name: 'Travel' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Custom…' })).toBeInTheDocument();
    await user.type(screen.getByLabelText(/Amount \(INR\)/), '12.345');
    await user.click(screen.getByRole('button', { name: 'Save draft' }));
    expect(await screen.findByText('Enter the merchant or vendor.')).toBeInTheDocument();
    expect(screen.getByText('Enter a positive amount in INR with no more than two decimal places.')).toBeInTheDocument();
    expect(api.create).not.toHaveBeenCalled();
  });

  it('converts rupees to paise when an employee creates a claim', async () => {
    const user = await setup();
    vi.mocked(api.create).mockResolvedValue({ ...submitted, id: 'claim-new', status: 'draft', amount_paise: 12505 });
    vi.mocked(api.claim).mockResolvedValue({ detail: { ...detail, claim: { ...submitted, id: 'claim-new', merchant: 'Corner Cafe', status: 'draft', amount_paise: 12505 } }, etag: '"1"' });
    await user.click(screen.getByRole('button', { name: '＋ New claim' }));
    await user.type(screen.getByLabelText(/Merchant/), 'Corner Cafe');
    await user.selectOptions(screen.getByLabelText(/Category/), 'cat-meals');
    fireEvent.change(screen.getByLabelText(/Expense date/), { target: { value: '2026-10-20' } });
    await user.type(screen.getByLabelText(/Amount \(INR\)/), '125.05');
    await user.type(screen.getByLabelText(/Business purpose/), 'Team planning');
    await user.click(screen.getByRole('button', { name: 'Save draft' }));
    await waitFor(() => expect(api.create).toHaveBeenCalledWith(employee.id, expect.objectContaining({
      category: 'Meals',
      category_id: 'cat-meals',
      amount_paise: 12505,
    })));
    expect(await screen.findByRole('heading', { name: 'Corner Cafe' })).toBeInTheDocument();
  });

  it('lets an employee choose and save a custom category', async () => {
    const user = await setup();
    vi.mocked(api.create).mockResolvedValue({ ...submitted, id: 'claim-custom-category', status: 'draft', category: 'Volunteer support' });
    vi.mocked(api.claim).mockResolvedValue({
      detail: {
        ...detail,
        claim: { ...submitted, id: 'claim-custom-category', merchant: 'Community Center', category: 'Volunteer support', status: 'draft' },
      },
      etag: '"1"',
    });

    await user.click(screen.getByRole('button', { name: '＋ New claim' }));
    await user.type(screen.getByLabelText(/Merchant/), 'Community Center');
    await user.selectOptions(screen.getByRole('combobox', { name: /Category/ }), '__custom__');
    await user.type(screen.getByLabelText('Custom category'), 'Volunteer support');
    fireEvent.change(screen.getByLabelText(/Expense date/), { target: { value: '2026-10-20' } });
    await user.type(screen.getByLabelText(/Amount \(INR\)/), '42.50');
    await user.type(screen.getByLabelText(/Business purpose/), 'Volunteer event supplies');
    await user.click(screen.getByRole('button', { name: 'Save draft' }));

    await waitFor(() => expect(api.create).toHaveBeenCalledWith(
      employee.id,
      expect.objectContaining({ category: 'Volunteer support', category_id: null }),
    ));
    expect(await screen.findByText(/Volunteer support/)).toBeInTheDocument();
  });

  it('saves an optional receipt number and shows it in claim details', async () => {
    const user = await setup();
    vi.mocked(api.create).mockResolvedValue({
      ...submitted,
      id: 'claim-with-receipt',
      merchant: 'Metro Cafe',
      status: 'draft',
      receipt_number: 'INV-007-A',
    });
    vi.mocked(api.claim).mockResolvedValue({
      detail: {
        ...detail,
        claim: {
          ...submitted,
          id: 'claim-with-receipt',
          merchant: 'Metro Cafe',
          status: 'draft',
          receipt_number: 'INV-007-A',
        },
      },
      etag: '"1"',
    });

    await user.click(screen.getByRole('button', { name: '＋ New claim' }));
    await user.type(screen.getByLabelText(/Merchant/), 'Metro Cafe');
    await user.selectOptions(screen.getByRole('combobox', { name: /Category/ }), 'cat-meals');
    await user.type(screen.getByLabelText('Receipt / Bill Number (optional)'), '  INV-007-A  ');
    fireEvent.change(screen.getByLabelText(/Expense date/), { target: { value: '2026-10-20' } });
    await user.type(screen.getByLabelText(/Amount \(INR\)/), '42.50');
    await user.type(screen.getByLabelText(/Business purpose/), 'Team lunch');
    await user.click(screen.getByRole('button', { name: 'Save draft' }));

    await waitFor(() => expect(api.create).toHaveBeenCalledWith(
      employee.id,
      expect.objectContaining({ receipt_number: 'INV-007-A' }),
    ));
    expect(await screen.findByText('Receipt / Bill Number')).toBeInTheDocument();
    expect(screen.getByText('INV-007-A')).toBeInTheDocument();
  });

  it('allows rejection without a comment', async () => {
    const user = await setup('user_manager');
    await user.click(screen.getByRole('button', { name: /Metro Cab/ }));
    await screen.findByRole('heading', { name: 'Review this claim' });
    expect(screen.getByLabelText('Decision comment (optional)')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Reject claim' }));
    await waitFor(() => expect(api.action).toHaveBeenCalledWith(manager.id, submitted.id, '"3"', 'reject', undefined));
  });

  it('treats a blank rejection comment as omitted', async () => {
    const user = await setup('user_manager');
    await user.click(screen.getByRole('button', { name: /Metro Cab/ }));
    await screen.findByRole('heading', { name: 'Review this claim' });
    await user.type(screen.getByLabelText(/Decision comment/), '   ');
    await user.click(screen.getByRole('button', { name: 'Reject claim' }));
    await waitFor(() => expect(api.action).toHaveBeenCalledWith(manager.id, submitted.id, '"3"', 'reject', undefined));
  });

  it('saves an optional rejection comment with the decision', async () => {
    const user = await setup('user_manager');
    await user.click(screen.getByRole('button', { name: /Metro Cab/ }));
    await screen.findByRole('heading', { name: 'Review this claim' });
    await user.type(screen.getByLabelText(/Decision comment/), 'Please include the client name.');
    await user.click(screen.getByRole('button', { name: 'Reject claim' }));
    await waitFor(() => expect(api.action).toHaveBeenCalledWith(manager.id, submitted.id, '"3"', 'reject', { comment: 'Please include the client name.' }));
  });

  it('styles the required legend marker in red', async () => {
    const user = await setup();
    await user.click(screen.getByRole('button', { name: '＋ New claim' }));
    const marker = screen.getByText('*', { selector: '.required-note-marker' });
    expect(getComputedStyle(marker).color).toBe('var(--color-danger)');
    expect(getComputedStyle(document.documentElement).getPropertyValue('--color-danger')).toBe('#f87171');
  });

  it('shows a recoverable conflict and reload action on a stale decision', async () => {
    const user = await setup('user_manager');
    await user.click(screen.getByRole('button', { name: /Metro Cab/ }));
    await screen.findByRole('heading', { name: 'Review this claim' });
    vi.mocked(api.action).mockRejectedValue(new ApiError(412, { code: 'stale', message: 'This claim changed since you opened it.' }));
    await user.click(screen.getByRole('button', { name: 'Approve claim' }));
    expect(await screen.findByText('This claim changed since you opened it.')).toBeInTheDocument();
    expect(screen.queryByText('Claim approved.')).not.toBeInTheDocument();
    await user.click(screen.getAllByRole('button', { name: 'Reload latest' })[0]);
    await waitFor(() => expect(api.claim).toHaveBeenCalledTimes(2));
  });

  it('shows employee rejection feedback and offers the correction path', async () => {
    const user = await setup();
    vi.mocked(api.claim).mockResolvedValue({
      detail: {
        ...detail,
        claim: { ...submitted, status: 'rejected' },
        events: [{
          ...detail.events[0], id: 'event-rejected', action: 'rejected', from_status: 'submitted',
          to_status: 'rejected', comment: 'Please add the business purpose.',
        }],
      },
      etag: '"4"',
    });
    await user.click(screen.getByRole('button', { name: /Metro Cab/ }));
    expect(await screen.findByText('“Please add the business purpose.”')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reopen and edit' })).toBeInTheDocument();
  });

  it('reopens a rejected claim, saves a correction, and resubmits with fresh versions', async () => {
    const user = await setup();
    const rejected: ClaimDetail = {
      ...detail,
      claim: { ...submitted, status: 'rejected', version: 4 },
      events: [{
        ...detail.events[0], id: 'event-rejected', action: 'rejected',
        from_status: 'submitted', to_status: 'rejected', comment: 'Please add the business purpose.',
      }],
    };
    const reopened: ClaimDetail = { ...rejected, claim: { ...rejected.claim, status: 'draft', version: 5 } };
    const corrected: ClaimDetail = {
      ...reopened,
      claim: { ...reopened.claim, description: 'Client meeting and project planning', version: 6 },
    };
    const resubmitted: ClaimDetail = {
      ...corrected,
      claim: { ...corrected.claim, status: 'submitted', version: 7 },
      events: [...corrected.events, {
        id: 'event-resubmitted', actor_id: employee.id, actor_name: employee.name, action: 'submitted',
        from_status: 'draft', to_status: 'submitted', comment: null, details: null, created_at: '2026-10-15T10:00:00Z',
      }],
    };
    vi.mocked(api.claim)
      .mockResolvedValueOnce({ detail: rejected, etag: '"4"' })
      .mockResolvedValueOnce({ detail: reopened, etag: '"5"' })
      .mockResolvedValueOnce({ detail: corrected, etag: '"6"' })
      .mockResolvedValueOnce({ detail: resubmitted, etag: '"7"' });

    await user.click(screen.getByRole('button', { name: /Metro Cab/ }));
    await screen.findByText('“Please add the business purpose.”');
    await user.click(screen.getByRole('button', { name: 'Reopen and edit' }));
    await screen.findByRole('heading', { name: 'Edit claim draft' });
    const purpose = screen.getByLabelText(/Business purpose/);
    await user.clear(purpose);
    await user.type(purpose, 'Client meeting and project planning');
    await user.click(screen.getByRole('button', { name: 'Save draft' }));
    await screen.findByRole('button', { name: 'Submit for approval' });
    expect(api.update).toHaveBeenCalledWith(
      employee.id, submitted.id, '"5"',
      expect.objectContaining({ description: 'Client meeting and project planning' }),
    );
    await user.click(screen.getByRole('button', { name: 'Submit for approval' }));
    await waitFor(() => expect(api.action).toHaveBeenCalledWith(employee.id, submitted.id, '"6"', 'submit', undefined));
    expect(await screen.findByText('Submitted', { selector: '.status-badge' })).toBeInTheDocument();
  });

  it('supports partial approval and only then marks an approved claim paid', async () => {
    const user = await setup('user_manager');
    const approved: ClaimDetail = {
      ...detail,
      claim: { ...submitted, status: 'approved', approved_amount_paise: 200000, version: 4 },
      events: [...detail.events, {
        id: 'event-approved',
        actor_id: manager.id,
        actor_name: manager.name,
        action: 'approved',
        from_status: 'submitted',
        to_status: 'approved',
        comment: 'Approved the client travel portion.',
        details: null,
        created_at: '2026-10-14T10:00:00Z',
      }],
    };
    const paid: ClaimDetail = {
      ...approved,
      claim: { ...approved.claim, status: 'paid', version: 5 },
      events: [...approved.events, {
        id: 'event-paid',
        actor_id: manager.id,
        actor_name: manager.name,
        action: 'paid',
        from_status: 'approved',
        to_status: 'paid',
        comment: null,
        details: null,
        created_at: '2026-10-15T10:00:00Z',
      }],
    };
    vi.mocked(api.claim)
      .mockResolvedValueOnce({ detail, etag: '"3"' })
      .mockResolvedValueOnce({ detail: approved, etag: '"4"' })
      .mockResolvedValueOnce({ detail: paid, etag: '"5"' });

    await user.click(screen.getByRole('button', { name: /Metro Cab/ }));
    await screen.findByRole('heading', { name: 'Review this claim' });
    const approvedAmount = screen.getByLabelText(/Approved amount/);
    await user.clear(approvedAmount);
    await user.type(approvedAmount, '2000.00');
    await user.type(screen.getByLabelText('Decision comment (optional)'), 'Approved the client travel portion.');
    await user.click(screen.getByRole('button', { name: 'Approve claim' }));
    await screen.findByRole('button', { name: 'Mark as paid' });
    expect(api.action).toHaveBeenCalledWith(manager.id, submitted.id, '"3"', 'approve', {
      approved_amount_paise: 200000,
      comment: 'Approved the client travel portion.',
    });
    expect(screen.getByText('₹2,450.50')).toBeInTheDocument();
    expect(screen.getByText('₹2,000.00')).toBeInTheDocument();
    expect(screen.getByText('“Approved the client travel portion.”')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Mark as paid' }));
    expect(await screen.findByText('Paid', { selector: '.status-badge' })).toBeInTheDocument();
    expect(screen.getByText('₹', { selector: '.marker-paid' })).toBeInTheDocument();
    expect(api.action).toHaveBeenLastCalledWith(manager.id, submitted.id, '"4"', 'mark-paid', undefined);
  });
});

import { useCallback, useEffect, useMemo, useState } from 'react';
import { ApiError, api } from './api/client';
import ClaimForm from './ClaimForm';
import { formatINR, parseRupeesToPaise, paiseToInput } from './money';
import type { Claim, ClaimCategory, ClaimDetail, ClaimFields, ClaimStatus, DemoUser } from './types';

type LoadedDetail = ClaimDetail & { etag: string | null };
const statusNames: Record<ClaimStatus, string> = {
  draft: 'Draft',
  submitted: 'Submitted',
  approved: 'Approved',
  rejected: 'Rejected',
  paid: 'Paid',
};
const statusIcons: Record<ClaimStatus, string> = {
  draft: '◷',
  submitted: '◉',
  approved: '✓',
  rejected: '!',
  paid: '₹',
};
const actionNames: Record<string, string> = {
  created: 'Created claim',
  updated: 'Updated claim details',
  submitted: 'Submitted for approval',
  reopened: 'Reopened for correction',
  approved: 'Approved claim',
  rejected: 'Rejected claim',
  deleted: 'Removed draft from claim list',
  paid: 'Marked as paid',
};

function messageFor(error: unknown) {
  if (error instanceof ApiError) return error.message;
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.';
}

function dateLabel(value: string) {
  return new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(value));
}

function dateTimeLabel(value: string) {
  return new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' }).format(new Date(value));
}

function StatusBadge({ status }: { status: ClaimStatus }) {
  return <span className={`status-badge status-${status}`}><span aria-hidden="true">{statusIcons[status]}</span>{statusNames[status]}</span>;
}

function ClaimCard({ claim, onOpen }: { claim: Claim; onOpen: () => void }) {
  return (
    <button className="claim-card" type="button" onClick={onOpen}>
      <span className="claim-card-main">
        <span className="claim-merchant">{claim.merchant}</span>
        <span className="claim-meta">{claim.category} <span aria-hidden="true">·</span> {dateLabel(claim.expense_date)}</span>
      </span>
      <span className="claim-card-right">
        <span className="claim-amount">{formatINR(claim.amount_paise)}</span>
        <StatusBadge status={claim.status} />
        {claim.approved_amount_paise !== null && claim.approved_amount_paise < claim.amount_paise && (
          <span className="claim-approved-amount">
            {claim.status === 'paid' ? 'Paid' : 'Approved'} {formatINR(claim.approved_amount_paise)} of {formatINR(claim.amount_paise)}
          </span>
        )}
      </span>
      <span className="claim-updated">Updated {dateLabel(claim.updated_at)}</span>
      <span className="claim-arrow" aria-hidden="true">→</span>
    </button>
  );
}

function ClaimDetails({ detail, currentUser, busy, onEdit, onAction, onBack, onReload, onDelete }: {
  detail: LoadedDetail;
  currentUser: DemoUser;
  busy: boolean;
  onEdit: () => void;
  onAction: (action: 'submit' | 'reopen' | 'approve' | 'reject' | 'mark-paid', body?: unknown) => Promise<boolean>;
  onBack: () => void;
  onReload: () => void;
  onDelete: () => void;
}) {
  const { claim, events } = detail;
  const isOwner = currentUser.role === 'employee' && claim.employee_id === currentUser.id;
  const canEdit = isOwner && claim.status === 'draft' && !claim.deleted_at;
  const canReview = currentUser.role === 'user_manager' && claim.status === 'submitted';
  const [approvedInput, setApprovedInput] = useState(paiseToInput(claim.amount_paise));
  const [comment, setComment] = useState('');
  const [reviewError, setReviewError] = useState('');
  const [localSuccess, setLocalSuccess] = useState('');

  async function doAction(action: 'submit' | 'reopen' | 'approve' | 'reject' | 'mark-paid', body?: unknown) {
    setLocalSuccess('');
    const succeeded = await onAction(action, body);
    if (succeeded) {
      setLocalSuccess(action === 'submit' ? 'Claim submitted for approval.' : action === 'reopen' ? 'Claim reopened. You can now update the draft.' : action === 'approve' ? 'Claim approved.' : action === 'reject' ? 'Claim rejected. The employee can review the outcome and any comment.' : 'Claim marked as paid.');
    }
  }

  async function reject() {
    setReviewError('');
    const trimmedComment = comment.trim();
    await doAction('reject', trimmedComment ? { comment: trimmedComment } : undefined);
  }

  async function approve() {
    const amount = parseRupeesToPaise(approvedInput);
    if (amount === null || amount > claim.amount_paise) {
      setReviewError('Enter an approved amount greater than ₹0.00 and no more than the claimed amount.');
      document.getElementById('approved-amount')?.focus();
      return;
    }
    setReviewError('');
    const trimmedComment = comment.trim();
    await doAction('approve', {
      approved_amount_paise: amount,
      ...(trimmedComment ? { comment: trimmedComment } : {}),
    });
  }

  return (
    <section aria-labelledby="detail-title">
      <button className="back-link" type="button" onClick={onBack}>← Back to claims</button>
      <div className="detail-top panel">
        <div className="detail-heading">
          <div>
            <p className="eyebrow">Claim details</p>
            <h2 id="detail-title">{claim.merchant}</h2>
            <p className="detail-subtitle">{claim.category} <span aria-hidden="true">·</span> Expense on {dateLabel(claim.expense_date)}</p>
          </div>
          <StatusBadge status={claim.status} />
        </div>
        <div className="amount-summary">
          <div><span>Claimed amount</span><strong>{formatINR(claim.amount_paise)}</strong></div>
          {claim.approved_amount_paise !== null && (
            <div><span>Approved amount</span><strong>{formatINR(claim.approved_amount_paise)}</strong></div>
          )}
        </div>
        <div className="detail-description">
          <h3>Business purpose</h3>
          <p>{claim.description}</p>
        </div>
        {claim.receipt_number && (
          <div className="detail-description">
            <h3>Receipt / Bill Number</h3>
            <p>{claim.receipt_number}</p>
          </div>
        )}
        {claim.deleted_at && <p className="notice">This draft was removed from your claim list. Its history is read-only.</p>}
        {localSuccess && <p className="inline-success" role="status">{localSuccess}</p>}
        {canEdit && (
          <div className="action-row">
            <button type="button" className="button button-primary" onClick={() => void doAction('submit')} disabled={busy}>Submit for approval</button>
            <button type="button" className="button button-secondary" onClick={onEdit} disabled={busy}>Edit draft</button>
            <button type="button" className="button button-danger-quiet" onClick={onDelete} disabled={busy}>Delete draft</button>
          </div>
        )}
        {isOwner && claim.status === 'rejected' && (
          <div className="action-row">
            <button type="button" className="button button-primary" onClick={() => void doAction('reopen')} disabled={busy}>Reopen and edit</button>
          </div>
        )}
        {currentUser.role === 'user_manager' && claim.status === 'approved' && (
          <div className="action-row"><button type="button" className="button button-primary" onClick={() => void doAction('mark-paid')} disabled={busy}>Mark as paid</button></div>
        )}
        {canReview && (
          <div className="review-box">
            <div>
              <p className="eyebrow">Your decision</p>
              <h3>Review this claim</h3>
            </div>
            <div className="field">
              <label htmlFor="approved-amount">Approved amount (INR)</label>
              <div className="input-prefix"><span aria-hidden="true">₹</span><input id="approved-amount" type="number" step="0.01" min="0.01" max={claim.amount_paise / 100} value={approvedInput} onChange={(event) => setApprovedInput(event.target.value)} aria-describedby="approval-help" /></div>
              <p className="field-help" id="approval-help">Defaults to the full claimed amount ({formatINR(claim.amount_paise)}). You can enter a lower amount.</p>
            </div>
            <div className="field">
              <label htmlFor="review-comment">Decision comment (optional)</label>
              <textarea id="review-comment" rows={3} value={comment} onChange={(event) => { setComment(event.target.value); setReviewError(''); }} aria-describedby="comment-help" />
              <p className="field-help" id="comment-help">Optional for approval or rejection. Any note is saved in activity history.</p>
            </div>
            {reviewError && <p className="field-error" role="alert">{reviewError}</p>}
            <div className="review-actions">
              <button className="button button-primary" type="button" onClick={() => void approve()} disabled={busy}>Approve claim</button>
              <button className="button button-danger" type="button" onClick={() => void reject()} disabled={busy}>Reject claim</button>
            </div>
          </div>
        )}
      </div>
      <div className="panel history-panel">
        <div className="panel-heading">
          <div><p className="eyebrow">A clear record</p><h2>Activity history</h2></div>
          <button type="button" className="button button-secondary button-small" onClick={onReload}>Reload latest</button>
        </div>
        {events.length === 0 ? <p className="muted">No activity has been recorded yet.</p> : (
          <ol className="timeline">
            {events.map((event) => (
              <li key={event.id}>
                <span className={`timeline-marker marker-${event.action}`} aria-hidden="true">{event.action === 'approved' ? '✓' : event.action === 'rejected' ? '!' : event.action === 'paid' ? '₹' : '•'}</span>
                <div className="timeline-content">
                  <strong>{actionNames[event.action] ?? event.action}</strong>
                  <span className="timeline-by">{event.actor_name} <span aria-hidden="true">·</span> <time dateTime={event.created_at}>{dateTimeLabel(event.created_at)}</time></span>
                  {event.comment && <p className="event-comment">“{event.comment}”</p>}
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}

export default function App() {
  const [users, setUsers] = useState<DemoUser[]>([]);
  const [categories, setCategories] = useState<ClaimCategory[]>([]);
  const [userId, setUserId] = useState(() => {
    const storedUserId = localStorage.getItem('claimwise-demo-user');
    if (storedUserId === 'approver-demo') {
      localStorage.setItem('claimwise-demo-user', 'manager-demo');
      return 'manager-demo';
    }
    return storedUserId ?? 'employee-demo';
  });
  const [identityAttempt, setIdentityAttempt] = useState(0);
  const [currentUser, setCurrentUser] = useState<DemoUser | null>(null);
  const [identityLoading, setIdentityLoading] = useState(true);
  const [identityError, setIdentityError] = useState('');
  const [claims, setClaims] = useState<Claim[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState('');
  const [filter, setFilter] = useState('all');
  const [managerTab, setManagerTab] = useState<'queue' | 'reviewed'>('queue');
  const [detail, setDetail] = useState<LoadedDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [globalError, setGlobalError] = useState<{ message: string; recover: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [formMode, setFormMode] = useState<'create' | 'edit' | null>(null);
  const [formServerFields, setFormServerFields] = useState<Record<string, string>>({});
  const [flash, setFlash] = useState('');

  useEffect(() => {
    let active = true;
    setIdentityLoading(true);
    setIdentityError('');
    const usersRequest = api.users().then((available) => {
      if (active) setUsers(available);
      return available;
    });
    const categoriesRequest = api.categories().then((available) => {
      if (active) setCategories(available);
      return available;
    });
    Promise.all([usersRequest, categoriesRequest, api.me(userId)]).then(([, , me]) => {
      if (!active) return;
      setCurrentUser(me);
      localStorage.setItem('claimwise-demo-user', me.id);
    }).catch((error: unknown) => {
      if (active) setIdentityError(messageFor(error));
    }).finally(() => {
      if (active) setIdentityLoading(false);
    });
    return () => { active = false; };
  }, [userId, identityAttempt]);

  const loadClaims = useCallback(async () => {
    if (!currentUser) return;
    setListLoading(true);
    setListError('');
    try {
      const result = await api.claims(currentUser.id, currentUser.role === 'employee' ? filter : undefined);
      setClaims(result.items);
    } catch (error) {
      setListError(messageFor(error));
    } finally {
      setListLoading(false);
    }
  }, [currentUser, filter]);

  useEffect(() => { void loadClaims(); }, [loadClaims]);

  const openClaim = useCallback(async (claimId: string) => {
    if (!currentUser) return;
    setDetail(null);
    setDetailLoading(true);
    setFormMode(null);
    setDetailError('');
    setGlobalError(null);
    try {
      const result = await api.claim(currentUser.id, claimId);
      setDetail({ ...result.detail, etag: result.etag });
    } catch (error) {
      setDetailError(messageFor(error));
    } finally {
      setDetailLoading(false);
    }
  }, [currentUser]);

  const refreshDetail = useCallback(async () => {
    if (detail) await openClaim(detail.claim.id);
    await loadClaims();
  }, [detail, loadClaims, openClaim]);

  const visibleClaims = useMemo(() => {
    if (currentUser?.role !== 'user_manager') return claims;
    return claims.filter((claim) => managerTab === 'queue' ? claim.status === 'submitted' : claim.status !== 'submitted');
  }, [managerTab, claims, currentUser?.role]);

  function startCreate() {
    setFilter('all');
    setFlash('');
    setFormServerFields({});
    setFormMode('create');
  }

  async function saveClaim(fields: ClaimFields) {
    if (!currentUser) return;
    setBusy(true);
    setGlobalError(null);
    setFormServerFields({});
    try {
      if (formMode === 'edit' && detail) {
        await api.update(currentUser.id, detail.claim.id, detail.etag ?? detail.claim.version, fields);
        setFlash('Draft saved.');
        await openClaim(detail.claim.id);
      } else {
        const created = await api.create(currentUser.id, fields);
        setFlash('Draft saved. Review the details before submitting.');
        setFormMode(null);
        await openClaim(created.id);
      }
      await loadClaims();
    } catch (error) {
      setGlobalError({ message: messageFor(error), recover: error instanceof ApiError && [409, 412, 428].includes(error.status) });
      if (error instanceof ApiError) setFormServerFields(error.fields);
    } finally {
      setBusy(false);
    }
  }

  async function performAction(action: 'submit' | 'reopen' | 'approve' | 'reject' | 'mark-paid', body?: unknown): Promise<boolean> {
    if (!currentUser || !detail) return false;
    setBusy(true);
    setGlobalError(null);
    try {
      await api.action(currentUser.id, detail.claim.id, detail.etag ?? detail.claim.version, action, body);
      await openClaim(detail.claim.id);
      await loadClaims();
      if (action === 'reopen') setFormMode('edit');
      setFlash('');
      return true;
    } catch (error) {
      setGlobalError({ message: messageFor(error), recover: error instanceof ApiError && [409, 412, 428].includes(error.status) });
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function deleteDraft() {
    if (!currentUser || !detail) return;
    const confirmed = window.confirm('Delete this draft? It will leave your claim list, but its history will be retained.');
    if (!confirmed) return;
    setBusy(true);
    setGlobalError(null);
    try {
      await api.remove(currentUser.id, detail.claim.id, detail.etag ?? detail.claim.version);
      setDetail(null);
      setFlash('Draft removed from your claim list. Its history is retained.');
      await loadClaims();
    } catch (error) {
      setGlobalError({ message: messageFor(error), recover: error instanceof ApiError && [409, 412, 428].includes(error.status) });
    } finally {
      setBusy(false);
    }
  }

  function changeIdentity(nextId: string) {
    setUserId(nextId);
    setCurrentUser(null);
    setClaims([]);
    setDetail(null);
    setFormMode(null);
    setFlash('');
    setGlobalError(null);
  }

  if (identityLoading) {
    return <main className="loading-page"><div className="spinner" aria-hidden="true" /><p role="status">Loading your Claimwise workspace…</p></main>;
  }

  return (
    <div className="app-shell">
      <header className="site-header">
        <a className="brand" href="#" onClick={(event) => { event.preventDefault(); setDetail(null); setFormMode(null); }} aria-label="Claimwise home">
          <span className="brand-mark" aria-hidden="true">C</span><span>Claimwise</span>
        </a>
        <div className="header-controls">
          <span className="demo-label"><span aria-hidden="true">●</span> Demo mode</span>
          <label className="identity-picker">
            <span className="sr-only">Choose demo identity</span>
            <select value={userId} onChange={(event) => changeIdentity(event.target.value)} aria-label="Choose demo identity">
              {users.length === 0 && <option value={userId}>{userId}</option>}
              {users.map((user) => <option key={user.id} value={user.id}>{user.name} — {user.role === 'employee' ? 'Employee' : 'User Manager'}</option>)}
            </select>
          </label>
        </div>
      </header>
      <main className="main-content">
        <div className="demo-notice"><span aria-hidden="true">i</span><p>This selector simulates a demo identity; it is not secure authentication. Do not use real or sensitive information.</p></div>
        {identityError && <div className="notice notice-error" role="alert"><p>{identityError}</p><button className="button button-secondary" onClick={() => setIdentityAttempt((attempt) => attempt + 1)} type="button">Retry</button></div>}
        {currentUser && (
          <>
            <div className="page-heading">
              <div>
                <p className="eyebrow">{currentUser.role === 'employee' ? 'Your reimbursement workspace' : 'User Manager workspace'}</p>
                <h1>{detail ? 'Claim details' : formMode === 'create' ? 'New claim' : currentUser.role === 'employee' ? 'My claims' : managerTab === 'queue' ? 'Review claims' : 'Reviewed claims'}</h1>
                <p className="page-description">{currentUser.role === 'employee' ? 'Keep track of your claims from draft to payment.' : 'Review submitted claims and keep decisions moving.'}</p>
              </div>
              {currentUser.role === 'employee' && !detail && formMode !== 'create' && <button className="button button-primary new-claim" type="button" onClick={startCreate}>＋ New claim</button>}
            </div>
            {globalError && <div className="notice notice-error" role="alert"><div><strong>That action did not complete.</strong><p>{globalError.message}</p><p>Your entered details are retained where possible.</p></div>{globalError.recover && <button className="button button-secondary" type="button" onClick={() => void refreshDetail()}>Reload latest</button>}</div>}
            {flash && <p className="flash-message" role="status">{flash}</p>}
            {formMode && currentUser.role === 'employee' && !detail && (
              <ClaimForm categories={categories} busy={busy} serverFields={formServerFields} onCancel={() => { setFormMode(null); setFormServerFields({}); }} onSave={saveClaim} />
            )}
            {detailError && <div className="notice notice-error" role="alert"><p>{detailError}</p><button type="button" className="button button-secondary" onClick={() => { setDetailError(''); void loadClaims(); }}>Back to claims</button></div>}
            {detail && !formMode && (
              <ClaimDetails
                detail={detail}
                currentUser={currentUser}
                busy={busy}
                onBack={() => { setDetail(null); setGlobalError(null); }}
                onEdit={() => { setGlobalError(null); setFormMode('edit'); }}
                onAction={performAction}
                onReload={() => void refreshDetail()}
                onDelete={() => void deleteDraft()}
              />
            )}
            {detail && formMode === 'edit' && currentUser.role === 'employee' && (
              <ClaimForm key={`${detail.claim.id}-${detail.claim.version}`} categories={categories} claim={detail.claim} busy={busy} serverFields={formServerFields} onCancel={() => setFormMode(null)} onSave={saveClaim} />
            )}
            {!detail && !formMode && (
              <>
                {detailLoading ? <div className="list-loading" role="status"><span className="spinner" aria-hidden="true" />Loading claim details…</div> : currentUser.role === 'employee' ? (
                  <div className="list-toolbar">
                    <label className="filter-control">Filter by status
                      <select value={filter} onChange={(event) => setFilter(event.target.value)}>
                        <option value="all">All claims</option>
                        {Object.entries(statusNames).map(([value, name]) => <option key={value} value={value}>{name}</option>)}
                      </select>
                    </label>
                    <span className="result-count">{claims.length} {claims.length === 1 ? 'claim' : 'claims'}</span>
                  </div>
                ) : (
                  <div className="tab-list" role="group" aria-label="User Manager claim lists">
                    <button aria-pressed={managerTab === 'queue'} className={managerTab === 'queue' ? 'active' : ''} type="button" onClick={() => setManagerTab('queue')}>Awaiting review</button>
                    <button aria-pressed={managerTab === 'reviewed'} className={managerTab === 'reviewed' ? 'active' : ''} type="button" onClick={() => setManagerTab('reviewed')}>Reviewed</button>
                  </div>
                )}
                {listError && <div className="notice notice-error" role="alert"><p>{listError}</p><button className="button button-secondary" type="button" onClick={() => void loadClaims()}>Try again</button></div>}
                {listLoading ? <div className="list-loading" role="status"><span className="spinner" aria-hidden="true" />Loading claims…</div> : (
                  visibleClaims.length > 0 ? (
                    <div className="claim-list">{visibleClaims.map((claim) => <ClaimCard key={claim.id} claim={claim} onOpen={() => void openClaim(claim.id)} />)}</div>
                  ) : !listError && (
                    <div className="empty-state panel">
                      <span className="empty-icon" aria-hidden="true">{currentUser.role === 'employee' ? '↗' : '✓'}</span>
                      <h2>{currentUser.role === 'employee' ? filter === 'all' ? 'Your claim list is clear' : `No ${statusNames[filter as ClaimStatus]?.toLowerCase() ?? ''} claims` : managerTab === 'queue' ? 'No claims are waiting for review' : 'No reviewed claims yet'}</h2>
                      <p>{currentUser.role === 'employee' ? 'Create a draft when you are ready to submit a reimbursement claim.' : 'New submitted claims will appear here. You can also switch to reviewed claims to see past decisions.'}</p>
                      {currentUser.role === 'employee' && <button type="button" className="button button-primary" onClick={startCreate}>Create your first claim</button>}
                    </div>
                  )
                )}
              </>
            )}
          </>
        )}
      </main>
      <footer className="site-footer"><span>Claimwise</span><span>Clear claims. Confident decisions.</span></footer>
    </div>
  );
}

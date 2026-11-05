import { useState, type FormEvent } from 'react';
import { parseRupeesToPaise, paiseToInput } from './money';
import type { Claim, ClaimCategory, ClaimFields } from './types';

type Props = {
  categories: ClaimCategory[];
  claim?: Claim;
  busy?: boolean;
  serverFields?: Record<string, string>;
  onCancel: () => void;
  onSave: (fields: ClaimFields) => Promise<void>;
};

const CUSTOM_CATEGORY = '__custom__';

export default function ClaimForm({ categories, claim, busy = false, serverFields = {}, onCancel, onSave }: Props) {
  const [values, setValues] = useState({
    merchant: claim?.merchant ?? '',
    receipt_number: claim?.receipt_number ?? '',
    expense_date: claim?.expense_date ?? new Date().toISOString().slice(0, 10),
    amount: claim ? paiseToInput(claim.amount_paise) : '',
    description: claim?.description ?? '',
  });
  const [categorySelection, setCategorySelection] = useState(() => (
    claim ? claim.category_id ?? CUSTOM_CATEGORY : ''
  ));
  const [customCategory, setCustomCategory] = useState(() => (
    claim?.category_id === null ? claim.category : ''
  ));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [dismissedServerFields, setDismissedServerFields] = useState<Record<string, boolean>>({});

  function update(field: keyof typeof values, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: '' }));
    setDismissedServerFields((current) => ({ ...current, [field]: true }));
  }

  function updateCategorySelection(value: string) {
    setCategorySelection(value);
    setErrors((current) => ({ ...current, category: '' }));
    setDismissedServerFields((current) => ({ ...current, category: true }));
  }

  function updateCustomCategory(value: string) {
    setCustomCategory(value);
    setErrors((current) => ({ ...current, category: '' }));
    setDismissedServerFields((current) => ({ ...current, category: true }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const next: Record<string, string> = {};
    if (!values.merchant.trim()) next.merchant = 'Enter the merchant or vendor.';
    if (values.merchant.trim().length > 120) next.merchant = 'Merchant must be 120 characters or fewer.';
    if (values.receipt_number.trim().length > 120) next.receipt_number = 'Receipt / Bill Number must be 120 characters or fewer.';
    const categoryOption = categories.find((option) => option.id === categorySelection);
    const category = categorySelection === CUSTOM_CATEGORY
      ? customCategory.trim()
      : claim?.category_id === categorySelection
        ? claim.category
        : categoryOption?.name ?? '';
    if (!category) next.category = categorySelection === CUSTOM_CATEGORY ? 'Enter a custom category.' : 'Choose a category.';
    if (category.length > 60) next.category = 'Category must be 60 characters or fewer.';
    const dateParts = /^\d{4}-(\d{2})-(\d{2})$/.exec(values.expense_date);
    const [year, month, day] = values.expense_date.split('-').map(Number);
    const normalizedDate = new Date(Date.UTC(year, month - 1, day));
    const dateIsValid = Boolean(dateParts)
      && normalizedDate.getUTCFullYear() === year
      && normalizedDate.getUTCMonth() + 1 === month
      && normalizedDate.getUTCDate() === day;
    if (!dateIsValid) {
      next.expense_date = 'Enter a valid expense date.';
    }
    const amountPaise = parseRupeesToPaise(values.amount);
    if (amountPaise === null) next.amount = 'Enter a positive amount in INR with no more than two decimal places.';
    if (!values.description.trim()) next.description = 'Explain the business purpose.';
    if (values.description.trim().length > 1000) next.description = 'Description must be 1,000 characters or fewer.';
    setErrors(next);
    const firstInvalid = Object.keys(next)[0];
    if (firstInvalid) {
      const fieldId = firstInvalid === 'category' && categorySelection === CUSTOM_CATEGORY
        ? 'claim-category-custom'
        : `claim-${firstInvalid}`;
      document.getElementById(fieldId)?.focus();
      return;
    }
    await onSave({
      merchant: values.merchant.trim(),
      category,
      category_id: categorySelection === CUSTOM_CATEGORY ? null : categorySelection,
      receipt_number: values.receipt_number.trim() || null,
      expense_date: values.expense_date,
      description: values.description.trim(),
      amount_paise: amountPaise!,
    });
  }

  const fieldError = (key: string) => errors[key] || (dismissedServerFields[key] ? '' : serverFields[key]);
  const control = (key: keyof typeof values, label: string, type = 'text', maxLength?: number) => (
    <div className="field">
      <label htmlFor={`claim-${key}`}>{label} <span aria-hidden="true">*</span></label>
      <input
        id={`claim-${key}`}
        type={type}
        value={values[key]}
        maxLength={maxLength}
        onChange={(event) => update(key, event.target.value)}
        aria-invalid={Boolean(fieldError(key))}
        aria-describedby={fieldError(key) ? `${key}-error` : undefined}
        required
      />
      {fieldError(key) && <p className="field-error" id={`${key}-error`}>{fieldError(key)}</p>}
    </div>
  );
  const categoryError = fieldError('category');

  return (
    <form className="panel form-panel" onSubmit={submit} noValidate>
      <div className="panel-heading">
        <div>
          <p className="eyebrow">{claim ? 'Update details' : 'New reimbursement'}</p>
          <h2>{claim ? 'Edit claim draft' : 'Create a claim'}</h2>
        </div>
        <span className="required-note"><span className="required-note-marker" aria-hidden="true">*</span> Required</span>
      </div>
      <div className="form-grid">
        {control('merchant', 'Merchant', 'text', 120)}
        <div className="field">
          <label htmlFor="claim-category">Category <span aria-hidden="true">*</span></label>
          <select
            id="claim-category"
            value={categorySelection}
            onChange={(event) => updateCategorySelection(event.target.value)}
            aria-invalid={Boolean(categoryError)}
            aria-describedby={categoryError ? 'category-error' : 'category-help'}
            required
          >
            <option value="">Choose a category</option>
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {claim?.category_id === category.id ? claim.category : category.name}
              </option>
            ))}
            <option value={CUSTOM_CATEGORY}>Custom…</option>
          </select>
          {categorySelection === CUSTOM_CATEGORY && (
            <input
              id="claim-category-custom"
              type="text"
              value={customCategory}
              maxLength={60}
              onChange={(event) => updateCustomCategory(event.target.value)}
              placeholder="Enter a custom category"
              aria-label="Custom category"
              aria-invalid={Boolean(categoryError)}
              aria-describedby={categoryError ? 'category-error' : 'category-help'}
              required
            />
          )}
          <p className="field-help" id="category-help">Choose a common category or enter a custom one.</p>
          {categoryError && <p className="field-error" id="category-error">{categoryError}</p>}
        </div>
        {control('expense_date', 'Expense date', 'date')}
        {control('expense_date', 'Expense date', 'date')}
        <div className="field">
          <label htmlFor="claim-receipt_number">Receipt / Bill Number (optional)</label>
          <input
            id="claim-receipt_number"
            type="text"
            value={values.receipt_number}
            maxLength={120}
            onChange={(event) => update('receipt_number', event.target.value)}
            aria-invalid={Boolean(fieldError('receipt_number'))}
            aria-describedby={fieldError('receipt_number') ? 'receipt_number-error' : 'receipt_number-help'}
          />
          <p className="field-help" id="receipt_number-help">Enter the reference printed on the receipt or bill, if available.</p>
          {fieldError('receipt_number') && <p className="field-error" id="receipt_number-error">{fieldError('receipt_number')}</p>}
        </div>
        <div className="field">
          <label htmlFor="claim-amount">Amount (INR) <span aria-hidden="true">*</span></label>
          <div className="input-prefix">
            <span aria-hidden="true">₹</span>
            <input
              id="claim-amount"
              type="number"
              inputMode="decimal"
              min="0.01"
              step="0.01"
              value={values.amount}
              onChange={(event) => update('amount', event.target.value)}
              aria-invalid={Boolean(fieldError('amount'))}
              aria-describedby={fieldError('amount') ? 'amount-error' : 'amount-help'}
              required
            />
          </div>
          <p className="field-help" id="amount-help">Enter rupees with up to two decimal places.</p>
          {fieldError('amount') && <p className="field-error" id="amount-error">{fieldError('amount')}</p>}
        </div>
      </div>
      <div className="field">
        <label htmlFor="claim-description">Business purpose <span aria-hidden="true">*</span></label>
        <textarea
          id="claim-description"
          rows={4}
          maxLength={1000}
          value={values.description}
          onChange={(event) => update('description', event.target.value)}
          aria-invalid={Boolean(fieldError('description'))}
          aria-describedby={fieldError('description') ? 'description-error' : 'description-help'}
          required
        />
        <p className="field-help" id="description-help">Add enough context for your manager. Up to 1,000 characters.</p>
        {fieldError('description') && <p className="field-error" id="description-error">{fieldError('description')}</p>}
      </div>
      <div className="form-actions">
        <button className="button button-primary" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save draft'}</button>
        <button className="button button-secondary" type="button" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </form>
  );
}

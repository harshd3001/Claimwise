# Claimwise — Product and UI Design Guide

This document is the design source of truth for the Claimwise reimbursement app. **Read it before every frontend UI, interaction, or styling change.** Follow its user flows, accessibility requirements, content standards, and visual tokens. If implementation constraints or a product requirement make a rule unsuitable, update this document deliberately before diverging.

Claimwise is a small, trustworthy reimbursement tool for employees and user managers. The interface should feel calm, clear, and dependable: users should always know what happened, what they can do next, and whether an action succeeded.

## 1. Product principles

1. **Clarity over decoration.** Prioritize claim status, amount, next action, and review feedback. Avoid dashboard-like visual clutter, decorative charts, and unnecessary motion.
2. **Trust through feedback.** Confirm every important action, preserve review history, and explain validation/conflicts in plain language.
3. **Prevent mistakes.** Make available actions match the claim's state and the current demo role. Confirm deletion and clearly mark rejection comments as optional.
4. **Consistent, humane language.** Use concise labels and actionable messages; never blame the user or show raw stack traces.
5. **Accessible by default.** Semantic HTML, keyboard support, visible focus, sufficient contrast, and status text/icons in addition to color.
6. **Responsive, not merely shrunk.** Employee and user manager tasks must remain usable on narrow screens without horizontal page scrolling.

## 2. Audience and key journeys

### Employee

1. Select the seeded employee identity in the clearly marked demo switcher.
2. See a useful empty state or a list of own claims grouped/filtered by status.
3. Create a draft with merchant, category, expense date, description, and INR amount.
4. Review the entered details, save, then submit for approval.
5. Open any claim to see its current status and chronological activity.
6. If rejected, read any comment from the User Manager, reopen the claim, correct it, and submit again.
7. See the approved amount (if different from the claimed amount), or see that an approved claim was marked paid.

### User Manager

1. Select the seeded user manager identity; see the submitted queue and previously reviewed claims separately.
2. Open a claim and review its details and history before deciding.
3. Approve with the full amount by default, optionally enter a lower approved amount if partial approval is enabled, or reject with an optional comment.
4. See a success confirmation and the claim move out of the submitted queue.
5. Mark an approved claim paid; never present this action on a rejected or submitted claim.

The identity switcher is a **demo-only simulation**, not real authentication. Keep the notice visible and do not imply that changing identity secures or protects data.

## 3. Information architecture

Keep navigation shallow and task-oriented:

- **My claims** — employee's own non-deleted claims, with status filters and a prominent “New claim” action.
- **Review claims** — user manager's submitted queue.
- **Reviewed claims** — claims the user manager has already decided, with outcome/status visible.
- **Claim detail** — claim summary, allowed next action, and activity history in one place.

The app shell should include:

- A compact product wordmark: **Claimwise**.
- A persistent demo-mode label and identity/role selector.
- A clear page title and a narrow, predictable content width for forms and details.
- Responsive navigation that becomes a simple menu or stacked controls on small screens.

Avoid adding an analytics dashboard, chart library, drag-and-drop layout, or admin console for this assignment; none is needed to complete the required workflow.

## 4. Visual direction and color system

Use a **near-black and emerald-green** palette: restrained, professional, finance-oriented. Green is the primary action and positive-outcome color, but it must not be used as the only status signal. Red is reserved for destructive actions/errors; amber for pending/attention. Keep most surfaces neutral.

Define tokens centrally in the app's global stylesheet (for example `src/index.css`). Components use tokens, not scattered hex values.

| Token | Suggested value | Intended use |
|---|---|---|
| `--color-bg` | `#0B0F0D` | App canvas; near-black, not pure black |
| `--color-surface` | `#121916` | Main cards and form surfaces |
| `--color-surface-raised` | `#19221D` | Menus, hover surfaces, dialogs |
| `--color-border` | `#29352E` | Dividers and subtle card/input borders |
| `--color-text` | `#F2F7F3` | Primary text |
| `--color-text-muted` | `#A7B5AA` | Secondary labels and helper text |
| `--color-primary` | `#22C55E` | Primary actions and selected state |
| `--color-primary-hover` | `#16A34A` | Hover/active primary action |
| `--color-primary-soft` | `#12351F` | Soft selected/success background |
| `--color-success` | `#4ADE80` | Approved/paid positive feedback |
| `--color-warning` | `#FBBF24` | Submitted/pending attention |
| `--color-danger` | `#F87171` | Rejected/error/delete |
| `--color-focus` | `#86EFAC` | Visible keyboard focus ring |

These are starting values, not permission to ignore contrast. Check text, controls, focus rings, badges, and disabled states against their actual backgrounds; target WCAG 2.2 AA contrast (4.5:1 for normal text, 3:1 for large text and meaningful UI boundaries). If a suggested token fails in context, tune the token and update the table.

### Status treatment

Use a compact badge with **icon + visible label**; never use color alone:

- Draft — neutral, “Draft”.
- Submitted — amber, “Submitted” / “Awaiting review”.
- Approved — green, “Approved”.
- Rejected — red, “Rejected”.
- Paid — green with distinct paid icon, “Paid”.

Keep visual distinction between approval and payment. Do not imply that an approved claim is paid.

## 5. Typography, spacing, and shape

- Use a readable system sans-serif stack (for example `Inter, ui-sans-serif, system-ui, sans-serif`) unless a bundled font is already available.
- Body copy: comfortable 14–16px with about 1.5 line-height. Labels and helper text should remain readable; avoid tiny uppercase captions.
- Use a simple type hierarchy: one page heading, section headings, then labels/body text. Avoid gradient text, glowing metrics, and excessive all-caps.
- Use a 4px spacing base; group related fields tightly and separate page sections consistently.
- Use subtle 8–12px card/input radii and 6–8px buttons. Avoid pill-shaped controls everywhere; reserve pills for status/filter badges.
- Prefer quiet borders and restrained shadows over glass effects, glow, fractal/noise overlays, or decorative gradients.
- Use tabular numerals for money and dates where helpful. Display money as INR (`₹`), using Indian grouping and two decimal places when paise are present.

## 6. Page and component behavior

### Claims list

- Each row/card should make merchant/title, expense date, claimed amount, status, and updated/submitted date easy to scan.
- When the approved amount is lower than the claimed amount, show a compact “Approved/Paid amount of claimed amount” line on the card; omit it for full approvals.
- Include a status filter with a clear “All” option. Preserve the selected filter only if it does not hide newly created/updated claims unexpectedly.
- Sort deterministically (most recently updated first); show an informative empty state with a relevant next action.
- On mobile, use stacked claim cards rather than forcing a wide desktop table.

### Claim form

- Group related fields in a clear order: merchant/category, expense date, amount, description.
- Mark required fields visibly and associate each with a persistent label (do not rely on placeholder text).
- Load common category choices from the backend category catalog using each category's stable ID and display name. Claims retain the selected category name as a snapshot. Include a Custom option that stores the entered category on the claim without adding a global catalog option.
- Offer an optional Receipt / Bill Number text field for printed invoice references; preserve letters and leading zeros, and show a supplied value in claim details.
- Preserve user input after validation or network errors. Show inline errors next to fields and focus the first invalid field on submit.
- Explain the amount in INR and accept at most two decimal places. Parse decimal input exactly; do not silently round.
- Use a review/confirm step only if it stays lightweight; at minimum keep the entered values visible before submission.

### Claim detail and activity

- Put current status, claimed amount, approved amount if applicable, and available next action near the top.
- Clearly distinguish claimed and approved amounts for partial approval.
- Show an append-only chronological activity list with actor, action, timestamp, and comment. Explain resubmissions rather than collapsing prior decisions.
- Use a distinct currency icon for the “Marked as paid” timeline event so payment is visually distinct from approval.
- Any approval or rejection comment must be saved with that decision and remain visible in the activity history.
- Keep soft-deleted draft history accessible only through the owner's read-only detail/history route; do not offer mutation controls.

### User Manager decision controls

- Show claim facts before the decision controls; don't place destructive choices next to one another without clear labels/spacing.
- Approval defaults to the full claimed amount. If partial approval is available, make the approved amount explicit and validate `0 < approved <= claimed`.
- Decision comments are optional for both approval and rejection. Explain that any comment entered is saved in activity history.
- Disable decision buttons while a request is pending. On success, confirm the outcome and update the queue. On a conflict, preserve context and offer a reload/review action.

### Feedback and loading states

- **Loading:** use a small labeled spinner or skeleton matching the content shape. Avoid indefinite full-page loaders for local form actions.
- **Empty:** explain why the list is empty and offer the most relevant action (“Create your first claim” or “No claims are waiting for review”).
- **Success:** use a concise inline confirmation or toast with the completed action; keep the new status visible.
- **Validation:** explain exactly what needs correction, near the affected control.
- **Network/server error:** say the action did not complete and whether entered data was retained. Never show a success state after failure.
- **Conflict/stale data:** explain that the claim changed elsewhere, reload the latest version, and require a fresh user decision.
- Don't rely on toast alone for errors that require a decision or correction.

## 7. Interaction, accessibility, and responsive requirements

- All actions work with keyboard alone; preserve logical tab order and use native buttons, links, forms, and inputs.
- Show a clear `:focus-visible` outline with sufficient contrast; never remove focus styling.
- Use accessible names for icon-only buttons. Associate errors with controls (`aria-describedby`) and announce asynchronous results appropriately (`role="status"`/live region where suitable).
- Use an appropriate dialog pattern for deletion confirmation, including focus management and Escape handling; prefer a simple native confirmation only if it remains accessible and clear.
- Minimum touch target should be 44×44 CSS pixels where practical. Do not make primary actions depend on hover.
- Respect `prefers-reduced-motion`; transitions are brief and optional. Avoid animated backgrounds and distracting effects.
- At narrow viewport widths, forms become one column, actions wrap/stack, detail content remains readable, and list items become cards. Prevent horizontal overflow.
- Test browser zoom/reflow at 200% and keyboard-visible focus in the main employee and user manager journeys.

## 8. Content and localization

- Use short, specific actions: “Save draft”, “Submit for approval”, “Approve claim”, “Reject claim”, “Reopen and edit”, “Mark as paid”.
- Confirmation copy should state the consequence, e.g. “Delete this draft? This removes it from your claim list, but its history is retained.”
- Avoid ambiguous “Done”, “Process”, or “Complete” buttons when the actual action can be named.
- Use “claim” consistently; don't alternate between “expense”, “request”, and “reimbursement” for the same object.
- Use `en-IN`/INR formatting for currency and a consistent human-readable date format. Keep API dates ISO formatted.
- Never expose internal IDs, exception text, or backend details as ordinary user-facing copy.

## 9. Frontend implementation rules

Before any frontend change:

1. Read this file and identify the flow/page/component affected.
2. Reuse existing tokens, components, and patterns; do not introduce a parallel design system.
3. Keep business permissions/state transitions server-enforced; hiding a button is not authorization.
4. Add or update React Testing Library tests for changed user-visible behavior and states.
5. Check keyboard behavior and narrow-screen layout as part of the change.
6. If the design requirement must change, edit this guide in the same change and explain why.

Technical conventions:

- Keep UI components focused and reuse a typed API client rather than calling `fetch` throughout the component tree.
- Treat API data as server state; refresh/invalidate the relevant list/detail after mutations.
- Do not duplicate domain rules in frontend logic as the only validation. Frontend validation improves usability; backend validation is authoritative.
- Use semantic status values and user-facing labels mapped centrally.
- Keep demo mode conspicuous; never describe its selector as secure login.
- Avoid unnecessary packages, charts, animation frameworks, global state libraries, and abstractions for this small application.

## 10. Design review checklist

- [ ] Follows the employee/user manager journey and exposes only valid next actions.
- [ ] Uses the near-black/emerald token palette and maintains WCAG AA contrast.
- [ ] Status is communicated through label/icon as well as color.
- [ ] Forms have persistent labels, inline validation, retained input, and sensible focus behavior.
- [ ] Loading, empty, success, error, and stale-conflict states are covered.
- [ ] Important actions are explicit; destructive actions are confirmed.
- [ ] Keyboard, screen-reader semantics, focus-visible, reduced-motion, and 44px targets are considered.
- [ ] Mobile/narrow layouts do not create page-level horizontal scrolling.
- [ ] Frontend tests cover changed interactions and critical UI states.
- [ ] No irrelevant dashboard, chart, drag-and-drop, or decorative UI was added.

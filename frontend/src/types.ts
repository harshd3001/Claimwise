export type Role = 'employee' | 'user_manager';
export type ClaimStatus = 'draft' | 'submitted' | 'approved' | 'rejected' | 'paid';
export type EventAction = 'created' | 'updated' | 'submitted' | 'reopened' | 'approved' | 'rejected' | 'deleted' | 'paid';

export interface DemoUser {
  id: string;
  name: string;
  email: string;
  role: Role;
}

export interface Claim {
  id: string;
  employee_id: string;
  merchant: string;
  category: string;
  receipt_number: string | null;
  description: string;
  expense_date: string;
  amount_paise: number;
  approved_amount_paise: number | null;
  status: ClaimStatus;
  version: number;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface ClaimEvent {
  id: string;
  actor_id: string;
  actor_name: string;
  action: EventAction;
  from_status: ClaimStatus | null;
  to_status: ClaimStatus | null;
  comment: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface ClaimDetail {
  claim: Claim;
  events: ClaimEvent[];
}

export interface ClaimList {
  items: Claim[];
  total: number;
}

export interface ClaimFields {
  merchant: string;
  category: string;
  receipt_number?: string | null;
  description: string;
  expense_date: string;
  amount_paise: number;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  fields?: Record<string, string>;
}

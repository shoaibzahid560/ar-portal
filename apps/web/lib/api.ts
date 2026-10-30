/**
 * Calls the API through the /api rewrite. The session cookie travels automatically.
 * Errors carry the API's own message, ready to show to the person.
 */

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

type Detail =
  string | { msg?: string; loc?: (string | number)[] }[] | undefined;

function messageFrom(detail: Detail, status: number): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    // FastAPI validation errors: show the first one in plain words.
    const first = detail[0];
    const field = first.loc?.at(-1);
    const text = (first.msg ?? "Invalid value").replace(/^Value error, /, "");
    return field && typeof field === "string"
      ? `${field.replace(/_/g, " ")}: ${text}`
      : text;
  }
  if (status === 403) return "You don’t have permission to do that.";
  return "Something went wrong. Please try again.";
}

/** For file uploads: sends multipart form data (the browser sets the boundary header itself). */
export async function apiForm<T>(path: string, form: FormData): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: "POST",
    body: form,
    cache: "no-store",
  });
  if (response.status === 401) {
    window.location.replace("/login");
    throw new ApiError("Sign-in required.", 401);
  }
  if (!response.ok) {
    let detail: Detail;
    try {
      detail = ((await response.json()) as { detail?: Detail }).detail;
    } catch {
      detail = undefined;
    }
    throw new ApiError(messageFrom(detail, response.status), response.status);
  }
  return (await response.json()) as T;
}

export async function api<T>(
  path: string,
  options: { method?: string; body?: unknown } = {},
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: options.method ?? "GET",
    headers:
      options.body === undefined
        ? undefined
        : { "Content-Type": "application/json" },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    cache: "no-store",
  });
  if (response.status === 401) {
    window.location.replace("/login");
    throw new ApiError("Sign-in required.", 401);
  }
  if (!response.ok) {
    let detail: Detail;
    try {
      detail = ((await response.json()) as { detail?: Detail }).detail;
    } catch {
      detail = undefined;
    }
    throw new ApiError(messageFrom(detail, response.status), response.status);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

/* ---- Shapes returned by the API ---- */

export type NamedRef = { id: string; name: string };
export type RoleRef = { key: string; name: string };

export type User = {
  id: string;
  email: string;
  full_name: string;
  employee_code: string | null;
  phone: string | null;
  status: "active" | "paused" | "deactivated";
  role: RoleRef;
  practices: NamedRef[];
  teams: NamedRef[];
  last_login_at: string | null;
  created_at: string;
};

export type Practice = {
  id: string;
  name: string;
  status: "active" | "paused";
  notes: string;
  user_count: number;
  team_count: number;
  created_at: string;
};

export type Team = {
  id: string;
  name: string;
  practice_id: string | null;
  practice_name: string | null;
  manager_user_id: string | null;
  manager_name: string | null;
  member_count: number;
  created_at: string;
};

export type Role = {
  id: number;
  key: string;
  name: string;
  description: string;
  permissions: string[];
};
export type Permission = { key: string; module: string; description: string };
export type RolesResponse = { roles: Role[]; permissions: Permission[] };

export type AuditEvent = {
  id: number;
  occurred_at: string;
  actor: { id: string; name: string; email: string } | null;
  action: string;
  entity_type: string;
  entity_id: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
};
export type AuditPage = { events: AuditEvent[]; next_before_id: number | null };

export type PersonRef = { id: string; name: string; role: string | null };

export type ClaimListItem = {
  id: string;
  number: string;
  practice: NamedRef;
  patient_name: string;
  service_date: string;
  subscriber_id: string;
  insurance_carrier: string;
  billed: string;
  claim_status: string | null;
  action_taken: string | null;
  followup_date: string | null;
  assigned_to: PersonRef | null;
  aging_days: number;
  aging_bucket: string;
  needs_review: boolean;
};
export type ClaimPage = { claims: ClaimListItem[]; total: number };

export type ClaimNote = {
  id: number;
  body: string;
  created_at: string;
  author: PersonRef;
};

export type ClaimDetail = ClaimListItem & {
  upload: { id: string; number: string };
  patient_dob: string | null;
  subscriber_name: string | null;
  subscriber_dob: string | null;
  allowed_amount: string | null;
  recovered_amount: string | null;
  patient_responsibility: string | null;
  pay_status: string | null;
  check_status: string | null;
  cashed_date: string | null;
  payment_posted_date: string | null;
  eob: { file_name: string; uploaded_at: string } | null;
  review_reason: string | null;
  notes: ClaimNote[];
  can_work: boolean;
  created_at: string;
  updated_at: string;
};

export type Assignee = { id: string; name: string; role: string };

export type ClaimSummary = {
  total: number;
  unassigned: number;
  due_today: number;
  overdue: number;
  needs_review: number;
  billed_total: string;
  by_status: { status: string; count: number; billed: string }[];
};

export type ListOption = { id: number; value: string; active: boolean };
export type ListKey =
  "claim_status" | "pay_status" | "check_status" | "action_taken";
export type Lists = Record<ListKey, ListOption[]>;

export type Upload = {
  id: string;
  number: string;
  practice: NamedRef;
  uploaded_by: NamedRef;
  file_name: string;
  file_size: number;
  status: "processing" | "completed" | "failed";
  failure_reason: string | null;
  total_rows: number;
  created_claims: number;
  duplicate_rows: number;
  error_rows: number;
  review_rows: number;
  created_at: string;
  completed_at: string | null;
};
export type UploadDetail = Upload & {
  errors: { row_number: number; column: string; message: string }[];
};

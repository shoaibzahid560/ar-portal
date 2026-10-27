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

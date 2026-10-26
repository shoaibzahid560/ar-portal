/** Visual tone of a status pill. */
export type Tone = "neutral" | "info" | "ok" | "warn" | "danger";

/**
 * Claim statuses used by the template. The final list depends on management
 * decision #3 (which fields and statuses associates may change) and is fixed in M3.
 */
export const CLAIM_STATUSES = {
  unassigned: { label: "Unassigned", tone: "info" },
  assigned: { label: "Assigned", tone: "info" },
  in_progress: { label: "In progress", tone: "warn" },
  followup_scheduled: { label: "Follow-up scheduled", tone: "warn" },
  pending_review: { label: "Pending review", tone: "warn" },
  returned: { label: "Returned", tone: "danger" },
  resolved: { label: "Resolved", tone: "ok" },
  closed: { label: "Closed", tone: "neutral" },
} as const satisfies Record<string, { label: string; tone: Tone }>;

export type ClaimStatus = keyof typeof CLAIM_STATUSES;

export const UPLOAD_STATUSES = {
  processing: { label: "Processing", tone: "warn" },
  completed: { label: "Completed", tone: "ok" },
  needs_review: { label: "Needs review", tone: "warn" },
  failed: { label: "Failed", tone: "danger" },
} as const satisfies Record<string, { label: string; tone: Tone }>;

export type UploadStatus = keyof typeof UPLOAD_STATUSES;

export const CLOSED_CLAIM_STATUSES: ClaimStatus[] = ["resolved", "closed"];

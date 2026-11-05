/** Visual tone of a status pill. */
export type Tone = "neutral" | "info" | "ok" | "warn" | "danger";

/**
 * Colour for a Claim Status value from the AR sheet's dropdown. Values added later in Settings
 * fall back to a neutral colour.
 */
const CLAIM_STATUS_TONES: Record<string, Tone> = {
  "Approved to pay": "ok",
  Paid: "ok",
  "Paid Under Capitation": "ok",
  Adjusted: "ok",
  "In- Process": "warn",
  Pending: "warn",
  "Partially Paid": "warn",
  "Claim re-submitted": "warn",
  "Patient Responsblity": "warn",
  "Claim Status": "info",
  Denied: "danger",
  "Claim not found": "danger",
  Problem: "danger",
};

export function claimStatusTone(status: string | null): Tone {
  return status ? (CLAIM_STATUS_TONES[status] ?? "info") : "neutral";
}

export const UPLOAD_STATUSES = {
  processing: { label: "Processing", tone: "warn" },
  preview: { label: "Preview: not submitted", tone: "info" },
  submitted: { label: "Waiting for approval", tone: "warn" },
  committed: { label: "Committed", tone: "ok" },
  rejected: { label: "Turned down", tone: "neutral" },
  discarded: { label: "Discarded", tone: "neutral" },
  reversed: { label: "Reversed", tone: "danger" },
  failed: { label: "Failed", tone: "danger" },
} as const satisfies Record<string, { label: string; tone: Tone }>;

/** Where the work on a claim stands (separate from the payer-facing Claim Status). */
export const WORK_STATES = {
  open: { label: "Open", tone: "info" },
  pending_completion: { label: "Awaiting completion", tone: "warn" },
  closed: { label: "Closed", tone: "neutral" },
} as const satisfies Record<string, { label: string; tone: Tone }>;

export const PRIORITIES = {
  low: { label: "Low", tone: "neutral" },
  normal: { label: "Normal", tone: "neutral" },
  high: { label: "High", tone: "warn" },
  urgent: { label: "Urgent", tone: "danger" },
} as const satisfies Record<string, { label: string; tone: Tone }>;

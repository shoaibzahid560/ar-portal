/**
 * Fake records for the UI template only. They are replaced by API calls from M1 onward.
 * Never put real patient data in this file or anywhere outside production.
 */
import { CLOSED_CLAIM_STATUSES, type ClaimStatus, type Tone, type UploadStatus } from "./status";

export const SAMPLE_TODAY = "2026-10-26";

export const CURRENT_USER = {
  name: "Sara Ahmed",
  email: "sara.ahmed@example.com",
  role: "AR Manager",
};

export type Claim = {
  id: string;
  patient: string;
  practice: string;
  payer: string;
  dateOfService: string;
  balance: number;
  assignedTo: string | null;
  followUp: string | null;
  status: ClaimStatus;
};

export const SAMPLE_CLAIMS: Claim[] = [
  { id: "CLM-100231", patient: "Alex Sample", practice: "Riverside Family Dental", payer: "Delta Dental", dateOfService: "2026-08-14", balance: 1240, assignedTo: "Sara Ahmed", followUp: "2026-10-26", status: "followup_scheduled" },
  { id: "CLM-100232", patient: "Jordan Test", practice: "Northgate Dental Group", payer: "MetLife", dateOfService: "2026-08-02", balance: 860, assignedTo: "Bilal Raza", followUp: "2026-10-22", status: "in_progress" },
  { id: "CLM-100233", patient: "Casey Demo", practice: "Lakeview Smiles", payer: "Cigna Dental", dateOfService: "2026-09-03", balance: 2310, assignedTo: null, followUp: null, status: "unassigned" },
  { id: "CLM-100234", patient: "Riley Example", practice: "Riverside Family Dental", payer: "Aetna Dental", dateOfService: "2026-07-19", balance: 455, assignedTo: "Hina Malik", followUp: "2026-10-20", status: "returned" },
  { id: "CLM-100235", patient: "Morgan Sample", practice: "Northgate Dental Group", payer: "Guardian", dateOfService: "2026-09-11", balance: 1785, assignedTo: "Sara Ahmed", followUp: "2026-10-29", status: "assigned" },
  { id: "CLM-100236", patient: "Taylor Test", practice: "Lakeview Smiles", payer: "Delta Dental", dateOfService: "2026-06-30", balance: 640, assignedTo: "Usman Tariq", followUp: "2026-10-24", status: "pending_review" },
  { id: "CLM-100237", patient: "Jamie Demo", practice: "Riverside Family Dental", payer: "MetLife", dateOfService: "2026-08-27", balance: 975, assignedTo: null, followUp: null, status: "unassigned" },
  { id: "CLM-100238", patient: "Avery Example", practice: "Northgate Dental Group", payer: "Cigna Dental", dateOfService: "2026-05-21", balance: 2890, assignedTo: "Bilal Raza", followUp: null, status: "resolved" },
  { id: "CLM-100239", patient: "Quinn Sample", practice: "Lakeview Smiles", payer: "Aetna Dental", dateOfService: "2026-09-18", balance: 1120, assignedTo: "Hina Malik", followUp: "2026-10-26", status: "followup_scheduled" },
  { id: "CLM-100240", patient: "Drew Test", practice: "Riverside Family Dental", payer: "Guardian", dateOfService: "2026-04-08", balance: 390, assignedTo: "Usman Tariq", followUp: null, status: "closed" },
  { id: "CLM-100241", patient: "Skyler Demo", practice: "Northgate Dental Group", payer: "Delta Dental", dateOfService: "2026-08-09", balance: 1560, assignedTo: "Sara Ahmed", followUp: "2026-10-18", status: "in_progress" },
  { id: "CLM-100242", patient: "Rowan Example", practice: "Lakeview Smiles", payer: "MetLife", dateOfService: "2026-09-25", balance: 720, assignedTo: null, followUp: null, status: "unassigned" },
];

export const SAMPLE_PRACTICES = ["Riverside Family Dental", "Northgate Dental Group", "Lakeview Smiles"];

export function isOpen(claim: Claim): boolean {
  return !CLOSED_CLAIM_STATUSES.includes(claim.status);
}

export function isOverdue(claim: Claim, today = SAMPLE_TODAY): boolean {
  return isOpen(claim) && claim.followUp !== null && claim.followUp < today;
}

/** Mirrors the Claims views in lib/navigation.ts. In M3 this filtering moves to the API. */
export function claimMatchesView(claim: Claim, view: string, today = SAMPLE_TODAY): boolean {
  switch (view) {
    case "mine":
      return claim.assignedTo === CURRENT_USER.name;
    case "unassigned":
      return claim.status === "unassigned";
    case "followup-due":
      return isOpen(claim) && claim.followUp === today;
    case "overdue":
      return isOverdue(claim, today);
    case "returned":
      return claim.status === "returned";
    case "pending-review":
      return claim.status === "pending_review";
    case "closed":
      return !isOpen(claim);
    default:
      return true;
  }
}

export type Upload = {
  id: string;
  practice: string;
  fileName: string;
  rows: number;
  uploadedBy: string;
  uploadedOn: string;
  status: UploadStatus;
};

export const SAMPLE_UPLOADS: Upload[] = [
  { id: "UPL-0142", practice: "Riverside Family Dental", fileName: "riverside_ar_2026-10-26.xlsx", rows: 214, uploadedBy: "Bilal Raza", uploadedOn: "2026-10-26", status: "completed" },
  { id: "UPL-0141", practice: "Lakeview Smiles", fileName: "lakeview_ar_october.xlsx", rows: 188, uploadedBy: "Hina Malik", uploadedOn: "2026-10-25", status: "failed" },
  { id: "UPL-0140", practice: "Northgate Dental Group", fileName: "northgate_aging_report.xlsx", rows: 302, uploadedBy: "Bilal Raza", uploadedOn: "2026-10-24", status: "needs_review" },
  { id: "UPL-0139", practice: "Riverside Family Dental", fileName: "riverside_ar_2026-10-19.xlsx", rows: 197, uploadedBy: "Usman Tariq", uploadedOn: "2026-10-19", status: "completed" },
];

export type ActivityItem = {
  id: string;
  title: string;
  detail: string;
  when: string;
  pill: { label: string; tone: Tone };
};

export const SAMPLE_ACTIVITY: ActivityItem[] = [
  { id: "a1", title: "Upload completed", detail: "UPL-0142 · Riverside Family Dental", when: "26 Oct 2026, 9:12 pm", pill: { label: "Upload", tone: "ok" } },
  { id: "a2", title: "Claim assigned", detail: "CLM-100235 to Sara Ahmed", when: "26 Oct 2026, 6:40 pm", pill: { label: "Assignment", tone: "info" } },
  { id: "a3", title: "Follow-up logged", detail: "CLM-100239 · called payer, resubmission pending", when: "26 Oct 2026, 4:05 pm", pill: { label: "Follow-up", tone: "info" } },
  { id: "a4", title: "Claim returned for correction", detail: "CLM-100234 by Sara Ahmed", when: "25 Oct 2026, 8:31 pm", pill: { label: "Review", tone: "danger" } },
  { id: "a5", title: "Upload failed validation", detail: "UPL-0141 · 12 rows with invalid dates", when: "25 Oct 2026, 2:02 pm", pill: { label: "Upload", tone: "danger" } },
  { id: "a6", title: "Claim resolved", detail: "CLM-100238 · payment posted", when: "24 Oct 2026, 7:47 pm", pill: { label: "Resolved", tone: "ok" } },
];

export type NotificationItem = { id: string; title: string; message: string; when: string; unread: boolean };

export const SAMPLE_NOTIFICATIONS: NotificationItem[] = [
  { id: "n1", title: "Claim returned", message: "CLM-100234 was returned for correction.", when: "25 Oct 2026, 8:31 pm", unread: true },
  { id: "n2", title: "Upload needs review", message: "UPL-0140 has 6 possible duplicates to check.", when: "24 Oct 2026, 5:10 pm", unread: true },
  { id: "n3", title: "Follow-ups overdue", message: "3 follow-ups in your team are past due.", when: "24 Oct 2026, 9:00 am", unread: false },
];

/** Badge counts for the secondary panel. From M0 these come from a /counts endpoint per module. */
export function sampleViewCount(moduleKey: string, viewSlug: string): number | null {
  if (moduleKey === "claims") {
    return SAMPLE_CLAIMS.filter((c) => claimMatchesView(c, viewSlug)).length;
  }
  if (moduleKey === "uploads") {
    const byView: Record<string, (u: Upload) => boolean> = {
      all: () => true,
      processing: (u) => u.status === "processing",
      "needs-review": (u) => u.status === "needs_review",
      failed: (u) => u.status === "failed",
    };
    const match = byView[viewSlug];
    return match ? SAMPLE_UPLOADS.filter(match).length : null;
  }
  return null;
}

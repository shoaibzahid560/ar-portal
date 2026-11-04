"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { EmptyState } from "@/components/data/empty-state";
import { Panel } from "@/components/data/panel";
import { StatusPill } from "@/components/data/status-pill";
import { Table, Td, Th } from "@/components/data/table";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import {
  Field,
  FormError,
  inputClass,
  selectClass,
} from "@/components/ui/form";
import {
  apiForm,
  type Practice,
  type Upload,
  type UploadDetail,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";
import { getModule, resolveView } from "@/lib/navigation";
import { UPLOAD_STATUSES } from "@/lib/status";
import { useApi } from "@/lib/use-api";

export function UploadsView() {
  const router = useRouter();
  const view = resolveView(
    getModule("uploads"),
    useSearchParams().get("view"),
  ).slug;
  const { permissions } = useAuth();
  const canUpload = permissions.includes("uploads.create");
  const uploads = useApi<Upload[]>(`/uploads?view=${view}`);
  const [open, setOpen] = useState(false);

  return (
    <>
      {canUpload && (
        <div className="mb-3 flex">
          <Button
            variant="primary"
            className="ml-auto"
            onClick={() => setOpen(true)}
          >
            New upload
          </Button>
        </div>
      )}
      <Panel flush>
        {uploads.error ? (
          <EmptyState
            title="Uploads could not be loaded"
            description={uploads.error}
          />
        ) : uploads.loading ? (
          <p className="p-6 text-muted">Loading uploads…</p>
        ) : uploads.data?.length === 0 ? (
          <EmptyState
            title="No uploads in this view"
            description={
              canUpload
                ? "Upload a practice’s AR sheet to create its claims."
                : undefined
            }
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th className="pl-[15px]">Upload</Th>
                <Th>Practice</Th>
                <Th>File</Th>
                <Th className="text-right">Rows</Th>
                <Th className="text-right">New claims</Th>
                <Th className="text-right">Already in system</Th>
                <Th className="text-right">Rows with errors</Th>
                <Th className="text-right">Needs review</Th>
                <Th>Uploaded by</Th>
                <Th>Date</Th>
                <Th className="pr-[15px]">Status</Th>
              </tr>
            </thead>
            <tbody>
              {uploads.data?.map((u) => (
                <tr
                  key={u.id}
                  className="cursor-pointer hover:bg-[#fafbfc]"
                  onClick={() => router.push(`/uploads/${u.id}`)}
                >
                  <Td className="pl-[15px] font-bold">
                    <Link
                      href={`/uploads/${u.id}`}
                      onClick={(e) => e.stopPropagation()}
                      className="hover:text-brand"
                    >
                      {u.number}
                    </Link>
                  </Td>
                  <Td>{u.practice.name}</Td>
                  <Td className="max-w-[220px] truncate text-muted">
                    {u.file_name}
                  </Td>
                  <Td className="text-right">{u.total_rows}</Td>
                  <Td className="text-right">{u.created_claims}</Td>
                  <Td className="text-right">{u.duplicate_rows}</Td>
                  <Td
                    className={cn(
                      "text-right",
                      u.error_rows > 0 && "font-bold text-danger-ink",
                    )}
                  >
                    {u.error_rows}
                  </Td>
                  <Td
                    className={cn(
                      "text-right",
                      u.review_rows > 0 && "font-bold text-warn-ink",
                    )}
                  >
                    {u.review_rows}
                  </Td>
                  <Td>{u.uploaded_by.name}</Td>
                  <Td className="whitespace-nowrap">
                    {formatDateTime(u.created_at)}
                  </Td>
                  <Td className="pr-[15px]">
                    <StatusPill
                      label={UPLOAD_STATUSES[u.status].label}
                      tone={UPLOAD_STATUSES[u.status].tone}
                    />
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>
      {open && (
        <NewUploadDialog
          onClose={() => setOpen(false)}
          onDone={(id) => router.push(`/uploads/${id}`)}
        />
      )}
    </>
  );
}

function NewUploadDialog({
  onClose,
  onDone,
}: {
  onClose: () => void;
  onDone: (uploadId: string) => void;
}) {
  const practices = useApi<Practice[]>("/practices?status=active");
  const [practiceId, setPracticeId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!practiceId)
      return setError("Choose the practice this sheet belongs to.");
    if (!file) return setError("Choose the AR sheet to upload.");
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("practice_id", practiceId);
    form.append("file", file);
    try {
      const upload = await apiForm<UploadDetail>("/uploads", form);
      onDone(upload.id);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "The upload didn’t complete.",
      );
      setBusy(false);
    }
  }

  return (
    <Dialog
      open
      title="New upload"
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={() => void submit()}
            disabled={busy}
          >
            {busy ? "Checking the file…" : "Upload"}
          </Button>
        </>
      }
    >
      <fieldset disabled={busy} className="grid gap-3">
        <Field
          label="Practice"
          hint={
            practices.data && practices.data.length === 0
              ? "No active practices are available to you. Add one under Practices, set a paused one back to Active, or ask an administrator to assign you a practice."
              : "You can choose from the active practices assigned to you."
          }
        >
          <select
            className={cn(selectClass, "w-full")}
            value={practiceId}
            onChange={(e) => setPracticeId(e.target.value)}
          >
            <option value="">Choose a practice…</option>
            {(practices.data ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </Field>
        <Field
          label="AR sheet"
          hint="The practice’s AR sheet as .xlsx or .csv, up to 4 MB. Lines already in the system are skipped."
        >
          <input
            type="file"
            accept=".xlsx,.csv"
            className={cn(inputClass, "w-full py-1.5")}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </Field>
      </fieldset>
      <FormError message={error} />
    </Dialog>
  );
}

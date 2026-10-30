"use client";

import { X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";

/**
 * A modal built on the browser's own <dialog>: it traps focus, closes on Escape,
 * and returns focus to the button that opened it.
 */
export function Dialog({
  open,
  title,
  onClose,
  children,
  footer,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      className="m-auto max-h-[88vh] w-[min(720px,92vw)] overflow-hidden rounded-xl bg-white p-0 text-ink shadow-[0_20px_60px_rgba(0,0,0,0.2)] backdrop:bg-[rgba(19,22,30,0.45)]"
    >
      {open && (
        <div className="flex max-h-[88vh] flex-col">
          <div className="flex items-center border-b border-line px-[18px] py-4">
            <h2 className="text-[16px] font-bold">{title}</h2>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="ml-auto rounded-md p-1 text-[#7a808b] hover:bg-hover"
            >
              <X size={18} />
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-auto p-[18px]">
            {children}
          </div>
          {footer && (
            <div className="flex justify-end gap-2 border-t border-line px-[18px] py-3">
              {footer}
            </div>
          )}
        </div>
      )}
    </dialog>
  );
}

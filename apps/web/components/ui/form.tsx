"use client";

import { cloneElement, useId, type ReactElement, type ReactNode } from "react";

/** Shared field styles so every toolbar and dialog looks the same. */
export const inputClass =
  "h-9 rounded-[7px] border border-line bg-white px-2.5 text-[13px] text-ink outline-none placeholder:text-muted focus:border-brand disabled:bg-[#f7f8fa] disabled:text-muted";

export const selectClass = inputClass;

/**
 * A labelled control. The label is tied to the control by id, and the hint is announced with it,
 * so screen readers read "Practice, Leave as All practices…" rather than everything in the box.
 */
export function Field({
  label,
  hint,
  children,
  wide = false,
}: {
  label: string;
  hint?: string;
  children: ReactElement<{ id?: string; "aria-describedby"?: string }>;
  wide?: boolean;
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  return (
    <div className={wide ? "col-span-full" : undefined}>
      <label
        htmlFor={id}
        className="mb-1.5 block text-[11px] font-semibold text-[#6d7480]"
      >
        {label}
      </label>
      {cloneElement(children, {
        id,
        "aria-describedby": hint ? hintId : undefined,
      })}
      {hint && (
        <p id={hintId} className="mt-1 text-[11px] text-muted">
          {hint}
        </p>
      )}
    </div>
  );
}

/** A labelled group of controls, such as a grid of checkboxes. */
export function FieldGroup({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <fieldset className="col-span-full">
      <legend className="mb-1.5 text-[11px] font-semibold text-[#6d7480]">
        {label}
      </legend>
      {children}
    </fieldset>
  );
}

/** A grid of checkboxes for choosing several items, such as practices or teams. */
export function CheckboxGrid({
  items,
  selected,
  onChange,
  disabled = false,
  empty,
}: {
  items: { id: string; name: string }[];
  selected: string[];
  onChange: (ids: string[]) => void;
  disabled?: boolean;
  empty: string;
}) {
  if (items.length === 0)
    return <p className="text-[12px] text-muted">{empty}</p>;
  return (
    <div className="grid grid-cols-2 gap-2 max-[560px]:grid-cols-1">
      {items.map((item) => (
        <label
          key={item.id}
          className="flex items-center gap-2 rounded-[7px] border border-line bg-[#fafbfc] px-2.5 py-2 text-[12px]"
        >
          <input
            type="checkbox"
            disabled={disabled}
            checked={selected.includes(item.id)}
            onChange={(event) =>
              onChange(
                event.target.checked
                  ? [...selected, item.id]
                  : selected.filter((id) => id !== item.id),
              )
            }
          />
          {item.name}
        </label>
      ))}
    </div>
  );
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p
      role="alert"
      className="mt-3 rounded-[9px] bg-danger-soft px-3 py-2.5 text-[12px] text-danger-ink"
    >
      {message}
    </p>
  );
}

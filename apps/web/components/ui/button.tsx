import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

type Variant = "default" | "primary";

const VARIANTS: Record<Variant, string> = {
  default: "border-line bg-white text-[#3d4450] hover:bg-[#f7f8fa]",
  primary: "border-brand bg-brand text-white hover:bg-[#2a73b5]",
};

export function buttonClass(variant: Variant = "default"): string {
  return cn(
    "inline-flex items-center gap-1.5 whitespace-nowrap rounded-[7px] border px-3 py-2 text-[12px] font-semibold",
    VARIANTS[variant],
  );
}

export function Button({
  variant = "default",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return <button className={cn(buttonClass(variant), className)} {...props} />;
}

export function LinkButton({
  href,
  variant = "default",
  children,
}: {
  href: string;
  variant?: Variant;
  children: ReactNode;
}) {
  return (
    <Link href={href} className={buttonClass(variant)}>
      {children}
    </Link>
  );
}

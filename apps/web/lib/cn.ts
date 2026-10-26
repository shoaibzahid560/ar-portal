/** Joins class names, skipping empty values: cn("a", isActive && "b") */
export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-bold tracking-wide",
  {
    variants: {
      variant: {
        default:
          "border-[color-mix(in_srgb,var(--coral)_40%,transparent)] bg-[color-mix(in_srgb,var(--coral)_14%,transparent)] text-[var(--coral)]",
        secondary: "border-border bg-surface-muted text-muted-foreground",
        outline: "border-border bg-transparent text-foreground",
        warning:
          "border-[color-mix(in_srgb,var(--danger)_40%,transparent)] bg-[color-mix(in_srgb,var(--danger)_12%,transparent)] text-[var(--danger)]",
        online:
          "border-[color-mix(in_srgb,var(--coral)_40%,transparent)] bg-[color-mix(in_srgb,var(--coral)_12%,transparent)] text-[var(--coral)]",
        local: "border-border bg-surface-muted text-foreground",
        success:
          "border-[color-mix(in_srgb,var(--volt)_45%,transparent)] bg-[color-mix(in_srgb,var(--volt)_14%,transparent)] text-[var(--volt)]",
        pending:
          "border-[color-mix(in_srgb,var(--gold)_40%,transparent)] bg-[color-mix(in_srgb,var(--gold)_12%,transparent)] text-[var(--gold)]",
        activity:
          "border-[color-mix(in_srgb,var(--coral)_40%,transparent)] bg-[color-mix(in_srgb,var(--coral)_12%,transparent)] text-[var(--coral)]",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };

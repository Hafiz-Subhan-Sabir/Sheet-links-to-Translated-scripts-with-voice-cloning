import * as React from "react";
import { cn } from "@/lib/utils";
import {
  type CyberColor,
  cyberThemeVars,
} from "@/lib/cyber-theme";

export type { CyberColor } from "@/lib/cyber-theme";
export { CYBER_COLORS, cyberColorForIndex, CYBER_THEME } from "@/lib/cyber-theme";

interface CyberFrameProps extends React.HTMLAttributes<HTMLDivElement> {
  color: CyberColor;
  size?: "sm" | "md";
  interactive?: boolean;
  children: React.ReactNode;
}

export function CyberFrame({
  color,
  size = "md",
  interactive = false,
  className,
  style,
  children,
  ...props
}: CyberFrameProps) {
  return (
    <div
      className={cn(
        "cyber-frame",
        size === "sm" && "cyber-frame--sm",
        interactive && "card-interactive",
        className
      )}
      style={{ ...cyberThemeVars(color), ...style }}
      data-cyber-color={color}
      {...props}
    >
      <span className="cyber-frame__accent cyber-frame__accent--tl" aria-hidden />
      <span className="cyber-frame__accent cyber-frame__accent--br" aria-hidden />
      <span className="cyber-frame__trace cyber-frame__trace--tl" aria-hidden />
      <span className="cyber-frame__trace cyber-frame__trace--br" aria-hidden />
      <div className="cyber-frame__body">{children}</div>
    </div>
  );
}

"use client";

import { useToast, TOAST_DEFAULT_DURATION } from "@/hooks/use-toast";
import { Toast, ToastClose, ToastDescription, ToastProvider, ToastTitle, ToastViewport } from "@/components/ui/toast";

export function Toaster() {
  const { toasts, dismiss } = useToast();

  return (
    <ToastProvider duration={TOAST_DEFAULT_DURATION}>
      {toasts.map(({ id, title, description, action, variant, open, ...props }) => (
        <Toast
          key={id}
          variant={variant}
          open={open}
          onOpenChange={(isOpen) => {
            if (!isOpen) dismiss(id);
          }}
          {...props}
        >
          <div className="grid gap-1">
            {title && <ToastTitle>{title}</ToastTitle>}
            {description && <ToastDescription>{description}</ToastDescription>}
          </div>
          {action}
          <ToastClose />
        </Toast>
      ))}
      <ToastViewport />
    </ToastProvider>
  );
}

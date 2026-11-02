import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

type Toast = { id: number; message: string };

const ToastContext = createContext<(message: string) => void>(() => {});

export const useToast = () => useContext(ToastContext);

const VISIBLE_MS = 4000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(0);
  const stack = useRef<HTMLDivElement>(null);

  // A modal dialog sits in the browser's top layer, above everything else on the page.
  // Re-showing this popover whenever a toast arrives puts the toasts above the dialog.
  useEffect(() => {
    const element = stack.current;
    if (!element || !toasts.length) return;
    if (element.matches(":popover-open")) element.hidePopover();
    element.showPopover();
  }, [toasts.length]);

  const show = useCallback((message: string) => {
    const id = nextId.current++;
    setToasts((current) => [...current, { id, message }]);
    setTimeout(() => setToasts((current) => current.filter((toast) => toast.id !== id)), VISIBLE_MS);
  }, []);

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className="lv-toasts" ref={stack} popover="manual" role="status" aria-live="polite">
        {toasts.map((toast) => (
          <div className="lv-toast" key={toast.id}>
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

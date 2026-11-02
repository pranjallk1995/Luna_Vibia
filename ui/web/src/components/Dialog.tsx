import { X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";

/** Opens the browser's native dialog for as long as the component is mounted. */
export function useModal() {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
    return () => dialog?.close();
  }, []);

  return ref;
}

type Props = {
  title: string;
  size?: "small" | "large";
  onClose: () => void;
  children: ReactNode;
};

/** A modal on the browser's native dialog, which traps focus and closes on Escape. */
export function Dialog({ title, size = "small", onClose, children }: Props) {
  const ref = useModal();

  return (
    <dialog
      ref={ref}
      className={`lv-dialog lv-dialog-${size}`}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === ref.current) onClose();
      }}
    >
      <div className="lv-dialog-body">
        <header className="lv-dialog-header">
          <h2 title={title}>{title}</h2>
          <button className="lv-icon-button" type="button" aria-label="Close" onClick={onClose}>
            <X size={18} />
          </button>
        </header>
        {children}
      </div>
    </dialog>
  );
}

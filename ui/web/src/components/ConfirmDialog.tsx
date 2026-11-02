import type { LucideIcon } from "lucide-react";
import { useState } from "react";

import { messageOf } from "../lib";
import { Dialog } from "./Dialog";

type Props = {
  title: string;
  message: string;
  subject: string;
  action: string;
  icon: LucideIcon;
  run: () => Promise<unknown>;
  onClose: () => void;
};

/** Ask before a change, and stay open with the reason if it fails. */
export function ConfirmDialog({ title, message, subject, action, icon: Icon, run, onClose }: Props) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const confirm = async () => {
    setBusy(true);
    setError("");
    try {
      await run();
      onClose();
    } catch (failure) {
      setError(messageOf(failure, "That did not work. Please try again."));
      setBusy(false);
    }
  };

  return (
    <Dialog title={title} onClose={onClose}>
      <p className="lv-confirm-text">
        {message} <strong>{subject}</strong>
      </p>
      {error && <p className="lv-alert lv-alert-error">{error}</p>}
      <div className="lv-confirm-actions">
        <button className="lv-button" type="button" onClick={onClose}>
          Cancel
        </button>
        <button className="lv-button lv-button-primary" type="button" disabled={busy} onClick={confirm} autoFocus>
          <Icon size={17} />
          {action}
        </button>
      </div>
    </Dialog>
  );
}

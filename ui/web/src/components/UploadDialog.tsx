import { RefreshCw, UploadCloud } from "lucide-react";
import { useState, type DragEvent } from "react";

import type { Settings } from "../api";
import { displayName } from "../lib";
import type { Uploads } from "../uploads";
import { Dialog } from "./Dialog";
import { useToast } from "./Toasts";

type Props = {
  uploads: Uploads;
  settings: Settings;
  onClose: () => void;
};

export function UploadDialog({ uploads, settings, onClose }: Props) {
  const toast = useToast();
  const [dragging, setDragging] = useState(false);
  const { results, failed, progress } = uploads;

  const accept = (files: File[]) => {
    const supported = files.filter((file) =>
      settings.upload_types.includes(file.name.split(".").pop()?.toLowerCase() ?? ""),
    );
    if (supported.length < files.length) {
      toast(`Only ${settings.upload_types.join(", ")} tracks can be uploaded.`);
    }
    if (supported.length) uploads.add(supported);
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    accept(Array.from(event.dataTransfer.files));
  };

  return (
    <Dialog title="Upload tracks" size="large" onClose={onClose}>
      <label
        className={`lv-dropzone${dragging ? " lv-dropzone-active" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <UploadCloud size={26} />
        <span>Drag and drop track files, or click to choose</span>
        <small>{settings.upload_types.join(", ").toUpperCase()}</small>
        <input
          type="file"
          multiple
          accept={settings.upload_types.map((type) => `.${type}`).join(",")}
          onChange={(event) => {
            accept(Array.from(event.target.files ?? []));
            event.target.value = "";
          }}
        />
      </label>

      {progress && (
        <div className="lv-progress" role="status">
          <div className="lv-progress-text">
            Listening to {progress.name} and writing its caption. Time: {progress.elapsed}s elapsed
            {progress.remaining > 0 && `, ${progress.remaining} more waiting`}
          </div>
          <div className="lv-progress-track">
            <div className="lv-progress-bar" style={{ width: `${Math.max(progress.fraction * 100, 4)}%` }} />
          </div>
        </div>
      )}

      {failed.map((upload) => (
        <div className="lv-alert lv-alert-error lv-upload-failed" key={upload.id}>
          <span>
            Could not upload {upload.file.name}: {upload.message}
          </span>
          <button className="lv-button" type="button" onClick={() => uploads.retry(upload)}>
            Retry
          </button>
        </div>
      ))}

      {results.map((result) => (
        <article className="lv-upload-result" key={result.id}>
          <div className="lv-card-name">{displayName(result.name)}</div>
          <p>{result.caption}</p>
          <small>{result.tags.map((tag) => `#${tag}`).join("  ")}</small>
        </article>
      ))}

      {results.length > 0 && (
        <button className="lv-button lv-button-wide" type="button" onClick={uploads.clear}>
          <RefreshCw size={16} />
          Clear
        </button>
      )}
    </Dialog>
  );
}

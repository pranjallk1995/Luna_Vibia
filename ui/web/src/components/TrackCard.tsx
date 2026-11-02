import { Download, Eye, EyeOff, Heart, MoreVertical, Trash2 } from "lucide-react";
import { memo, useEffect, useRef, useState } from "react";

import { coverUrl, downloadUrl, type TrackRecord, type Section } from "../api";
import { displayName, durationLabel, sizeLabel } from "../lib";

export type CardAction = "open" | "favorite" | "delete" | "hide" | "restore";

type Props = {
  track: TrackRecord;
  section: Section;
  layout: "grid" | "list";
  onAction: (action: CardAction, track: TrackRecord) => void;
};

function CardMenu({ track, section, onAction }: Pick<Props, "track" | "section" | "onAction">) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const name = displayName(track.name);

  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  const act = (action: CardAction) => {
    setOpen(false);
    onAction(action, track);
  };

  return (
    <div className="lv-menu" ref={ref}>
      <button
        className="lv-menu-trigger"
        type="button"
        aria-label={`Actions for ${name}`}
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <MoreVertical size={18} />
      </button>
      {open && (
        <div className="lv-menu-items">
          <a className="lv-icon-button" href={downloadUrl(track, name)} aria-label="Download" title="Download">
            <Download size={17} />
          </a>
          <button className="lv-icon-button" type="button" aria-label="Delete" title="Delete" onClick={() => act("delete")}>
            <Trash2 size={17} />
          </button>
          {section === "view" && (
            <button className="lv-icon-button" type="button" aria-label="Hide" title="Hide" onClick={() => act("hide")}>
              <EyeOff size={17} />
            </button>
          )}
          {section === "hidden" && (
            <button className="lv-icon-button" type="button" aria-label="Restore" title="Restore" onClick={() => act("restore")}>
              <Eye size={17} />
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function TrackCardBase({ track, section, layout, onAction }: Props) {
  const name = displayName(track.name);
  return (
    <article className={`lv-card lv-card-${layout}`}>
      <div className="lv-thumbnail">
        <button className="lv-thumbnail-open" type="button" aria-label={`Open ${name}`} onClick={() => onAction("open", track)}>
          <img src={coverUrl(track, "card")} alt="" width={420} height={248} loading="lazy" decoding="async" />
        </button>
        {section !== "hidden" && (
          <button
            className={`lv-favorite${track.favorite ? " lv-favorite-active" : ""}`}
            type="button"
            aria-label={track.favorite ? `Remove ${name} from favorites` : `Add ${name} to favorites`}
            aria-pressed={Boolean(track.favorite)}
            onClick={() => onAction("favorite", track)}
          >
            <Heart size={16} fill={track.favorite ? "currentColor" : "none"} />
          </button>
        )}
      </div>
      <div className="lv-card-details">
        <div className="lv-card-title">
          <span className="lv-card-name" title={name}>
            {name}
          </span>
          <CardMenu track={track} section={section} onAction={onAction} />
        </div>
        <div className="lv-card-tags">
          {(track.tags ?? []).map((tag, index) => (
            <span className={`lv-tag lv-tag-${index % 6}`} key={tag}>
              {tag}
            </span>
          ))}
        </div>
        <div className="lv-card-facts">
          <span>{durationLabel(track.duration_seconds)}</span>
          <span>·</span>
          {Boolean(track.tempo_bpm) && (
            <>
              <span>{Math.round(track.tempo_bpm!)} BPM</span>
              <span>·</span>
            </>
          )}
          <span>{sizeLabel(track.size_bytes)}</span>
        </div>
      </div>
    </article>
  );
}

// Memoized so typing in search or toggling one favorite re-renders only what changed.
export const TrackCard = memo(TrackCardBase);

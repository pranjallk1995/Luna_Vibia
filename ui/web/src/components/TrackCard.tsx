import { Check, Download, Eye, EyeOff, Heart, MoreVertical, Trash2 } from "lucide-react";
import { memo, useEffect, useRef, useState } from "react";

import { coverUrl, downloadUrl, type TrackRecord, type Section } from "../api";
import { displayName, durationLabel, readableName, sizeLabel, visibleTags } from "../lib";

export type CardAction = "open" | "favorite" | "delete" | "hide" | "restore";

const TAGS_SHOWN = { grid: 3, list: 8 };

type Props = {
  track: TrackRecord;
  section: Section;
  layout: "grid" | "list";
  onAction: (action: CardAction, track: TrackRecord) => void;
  /** Whether clicking the card selects it, rather than opening it. */
  selecting: boolean;
  selected: boolean;
  onSelect: (track: TrackRecord, extend: boolean) => void;
};

function CardMenu({ track, section, onAction }: Pick<Props, "track" | "section" | "onAction">) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const name = readableName(track.name);

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
        className="lv-more"
        type="button"
        aria-label={`Actions for ${name}`}
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <MoreVertical size={18} />
      </button>
      {open && (
        <div className="lv-menu-items">
          <a
            className="lv-icon-button"
            href={downloadUrl(track, displayName(track.name))}
            aria-label="Download"
            title="Download"
          >
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

function TrackCardBase({ track, section, layout, onAction, selecting, selected, onSelect }: Props) {
  const name = readableName(track.name);
  const tags = visibleTags(track.tags);
  const hiddenTags = tags.length - TAGS_SHOWN[layout];
  const facts = [
    durationLabel(track.duration_seconds),
    track.tempo_bpm ? `${Math.round(track.tempo_bpm)} BPM` : null,
    sizeLabel(track.size_bytes),
  ].filter(Boolean);
  const stateClass = `${selecting ? " lv-card-selecting" : ""}${selected ? " lv-card-selected" : ""}`;
  return (
    // The whole card is the target while selecting; its button gives keyboards the same click.
    <article
      className={`lv-card lv-card-${layout}${stateClass}`}
      onClick={selecting ? (event) => onSelect(track, event.shiftKey) : undefined}
    >
      <div className="lv-thumbnail">
        <button
          className="lv-thumbnail-open"
          type="button"
          role={selecting ? "checkbox" : undefined}
          aria-checked={selecting ? selected : undefined}
          aria-label={selecting ? `Select ${name}` : `Open ${name}`}
          onClick={selecting ? undefined : () => onAction("open", track)}
        >
          <img src={coverUrl(track, "card")} alt="" width={420} height={280} loading="lazy" decoding="async" />
        </button>
        {selecting && <span className="lv-check">{selected && <Check size={15} strokeWidth={3} />}</span>}
        {!selecting && section !== "hidden" && (
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
        <p className="lv-card-name" title={name}>
          {name}
        </p>
        <div className="lv-card-tags">
          {tags.slice(0, TAGS_SHOWN[layout]).map((tag) => (
            <span className="lv-tag lv-tag-quiet" key={tag}>
              {tag}
            </span>
          ))}
          {hiddenTags > 0 && <span className="lv-tag lv-tag-more lv-tag-more-wide">+{hiddenTags}</span>}
          {/* Phones show one tag in a grid card, so they need their own count. */}
          {layout === "grid" && tags.length > 1 && (
            <span className="lv-tag lv-tag-more lv-tag-more-phone">+{tags.length - 1}</span>
          )}
        </div>
        <div className="lv-card-foot">
          <p className="lv-card-facts">
            {facts.join(" · ")}
          </p>
          {!selecting && <CardMenu track={track} section={section} onAction={onAction} />}
        </div>
      </div>
    </article>
  );
}

// Memoized so typing in search or toggling one favorite re-renders only what changed.
export const TrackCard = memo(TrackCardBase);

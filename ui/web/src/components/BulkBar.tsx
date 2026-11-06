import { Eye, EyeOff, Heart, HeartOff, Pencil, Trash2, type LucideIcon } from "lucide-react";

import type { TrackRecord, Section } from "../api";
import { itemCount } from "../lib";

export type BulkAction = "favorite" | "unfavorite" | "hide" | "restore" | "edit" | "delete";

const LABELS: Record<BulkAction, { label: string; icon: LucideIcon }> = {
  favorite: { label: "Favorite", icon: Heart },
  unfavorite: { label: "Unfavorite", icon: HeartOff },
  hide: { label: "Hide", icon: EyeOff },
  restore: { label: "Restore", icon: Eye },
  edit: { label: "Edit tags & text", icon: Pencil },
  delete: { label: "Delete", icon: Trash2 },
};

// The same choices each section's cards offer.
const ACTIONS: Record<Section, BulkAction[]> = {
  view: ["favorite", "unfavorite", "hide", "edit", "delete"],
  favorites: ["unfavorite", "edit", "delete"],
  hidden: ["restore", "edit", "delete"],
};

type Props = {
  section: Section;
  selected: TrackRecord[];
  /** How many selected tracks the current search is not showing. */
  outside: number;
  /** How many tracks "Select all" would pick: everything matching the search. */
  matching: number;
  onSelectAll: () => void;
  onClear: () => void;
  onAction: (action: BulkAction) => void;
};

/** The actions for the selected tracks; it stays in view while scrolling and paging. */
export function BulkBar({ section, selected, outside, matching, onSelectAll, onClear, onAction }: Props) {
  // An action that would change nothing on the selection is not offered.
  const available = (action: BulkAction) => {
    if (!selected.length) return false;
    if (action === "favorite") return selected.some((track) => !track.favorite);
    if (action === "unfavorite") return selected.some((track) => track.favorite);
    return true;
  };

  return (
    <div className="lv-bulk" role="toolbar" aria-label="Actions for selected tracks">
      <div className="lv-bulk-selection">
        <span className="lv-bulk-count" role="status">
          {selected.length} selected
          {outside > 0 && <small> ({itemCount(outside)} outside this search)</small>}
        </span>
        <button className="lv-button" type="button" disabled={!matching} onClick={onSelectAll}>
          Select all {matching}
        </button>
        <button className="lv-button" type="button" disabled={!selected.length} onClick={onClear}>
          Clear
        </button>
      </div>
      <div className="lv-bulk-actions">
        {ACTIONS[section].map((action) => {
          const { label, icon: Icon } = LABELS[action];
          return (
            <button
              className="lv-button"
              type="button"
              key={action}
              title={label}
              disabled={!available(action)}
              onClick={() => onAction(action)}
            >
              <Icon size={17} />
              <span>{label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

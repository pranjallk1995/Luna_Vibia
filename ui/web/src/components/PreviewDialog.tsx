import { Bot, Check, FileAudio, ImageIcon, Pencil, Plus, Tag, Text, X } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";

import { coverUrl, fileUrl, type TrackActions, type TrackRecord, type Section, type Settings } from "../api";
import { displayName, durationLabel, messageOf, normalizedTag, splitName } from "../lib";
import { Dialog } from "./Dialog";
import { useToast } from "./Toasts";

function DetailRow({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <div className="lv-detail">
      <span className="lv-detail-icon">{icon}</span>
      <div className="lv-detail-content">{children}</div>
    </div>
  );
}

type EditableProps = {
  label: string;
  value: string;
  maxLength: number;
  placeholder?: string;
  /** Resolve to close the editor; reject to keep it open with the error. */
  save: (draft: string) => Promise<unknown>;
};

/** Text with a pencil: Enter or the checkmark saves, Escape cancels. */
function EditableText({ label, value, maxLength, placeholder, save }: EditableProps) {
  const [draft, setDraft] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await save(draft ?? "");
      setDraft(null);
    } catch (failure) {
      setError(messageOf(failure, `Could not update ${label.toLowerCase()}.`));
    } finally {
      setBusy(false);
    }
  };

  if (draft === null) {
    return (
      <div className="lv-detail-line">
        <span className="lv-detail-text">{value}</span>
        <button className="lv-icon-button" type="button" aria-label={`Edit ${label.toLowerCase()}`} onClick={() => setDraft(value)}>
          <Pencil size={15} />
        </button>
      </div>
    );
  }
  return (
    <form onSubmit={submit}>
      <div className="lv-detail-line">
        <input
          className="lv-input"
          aria-label={label}
          autoFocus
          value={draft}
          maxLength={maxLength}
          placeholder={placeholder}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              // Cancel only this edit, not the whole dialog.
              event.preventDefault();
              event.stopPropagation();
              setDraft(null);
              setError("");
            }
          }}
        />
        <button className="lv-icon-button" type="submit" aria-label={`Save ${label.toLowerCase()}`} disabled={busy}>
          <Check size={16} />
        </button>
      </div>
      {error && <p className="lv-alert lv-alert-error">{error}</p>}
    </form>
  );
}

type TagsProps = {
  track: TrackRecord;
  maxTags: number;
  actions: TrackActions;
};

function TagEditor({ track, maxTags, actions }: TagsProps) {
  const toast = useToast();
  const [draft, setDraft] = useState<string | null>(null);
  const tags = track.tags ?? [];

  const removeTag = (tag: string) =>
    actions.updateMetadata.mutate(
      { name: track.name, change: { remove_tags: [tag] } },
      { onError: (failure) => toast(messageOf(failure, "Could not remove the tag.")) },
    );

  const addTag = (event: FormEvent) => {
    event.preventDefault();
    const tag = (draft ?? "").trim();
    if (!tag) return toast("Enter a tag name before adding it.");
    if (tags.some((existing) => normalizedTag(existing) === normalizedTag(tag))) {
      return toast("That tag is already on this track.");
    }
    if (tags.length >= maxTags) {
      return toast(`Maximum of ${maxTags} tags reached. Remove a tag before adding another.`);
    }
    actions.updateMetadata.mutate(
      { name: track.name, change: { add_tags: [tag] } },
      {
        onSuccess: () => setDraft(null),
        onError: () => toast("The tag could not be saved. Please try again."),
      },
    );
  };

  return (
    <div className="lv-detail-line lv-detail-line-top">
      <div className="lv-preview-tags">
        {tags.map((tag, index) => (
          <button
            className={`lv-tag lv-tag-${index % 6} lv-tag-removable`}
            type="button"
            key={tag}
            aria-label={`Remove tag ${tag}`}
            onClick={() => removeTag(tag)}
          >
            {tag}
            <X size={12} />
          </button>
        ))}
      </div>
      {draft === null ? (
        <button className="lv-icon-button" type="button" aria-label="Add a tag" onClick={() => setDraft("")}>
          <Plus size={16} />
        </button>
      ) : (
        <form className="lv-tag-form" onSubmit={addTag}>
          <input
            className="lv-input"
            aria-label="New tag"
            autoFocus
            placeholder="Tag name"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                event.preventDefault();
                event.stopPropagation();
                setDraft(null);
              }
            }}
          />
          <button className="lv-icon-button" type="submit" aria-label="Save tag">
            <Check size={16} />
          </button>
        </form>
      )}
    </div>
  );
}

function Player({ track, section, actions }: { track: TrackRecord; section: Section; actions: TrackActions }) {
  const [editing, setEditing] = useState(false);
  const [url, setUrl] = useState(track.cover_url ?? "");
  const [error, setError] = useState("");
  const labels = [track.title, track.artist].filter(Boolean);
  const facts = [
    durationLabel(track.duration_seconds),
    track.tempo_bpm ? `${Math.round(track.tempo_bpm)} BPM` : null,
    track.musical_key,
    track.energy !== null && track.energy !== undefined ? `energy ${Math.round(track.energy * 100)}%` : null,
  ].filter(Boolean);

  const saveCover = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      await actions.setCover.mutateAsync({ name: track.name, coverUrl: url.trim() || null });
      setEditing(false);
    } catch (failure) {
      setError(messageOf(failure, "Could not set the cover."));
    }
  };

  return (
    <div className="lv-player">
      <img className="lv-player-cover" src={coverUrl(track, "large")} alt="" width={360} height={240} />
      <div className="lv-player-body">
        {labels.map((label) => (
          <div className="lv-detail-text" key={label}>
            {label}
          </div>
        ))}
        <audio controls preload="metadata" src={fileUrl(track)} />
        <p className="lv-caption">{facts.join(" · ")}</p>
        {section !== "hidden" &&
          (editing ? (
            <form className="lv-cover-form" onSubmit={saveCover}>
              <p className="lv-caption">Paste a Luna Visia image link (…/api/public/images/&lt;id&gt;), or clear it.</p>
              <div className="lv-detail-line">
                <input className="lv-input" aria-label="Visia image URL" autoFocus value={url} onChange={(event) => setUrl(event.target.value)} />
                <button className="lv-button" type="submit">
                  Save cover
                </button>
              </div>
              {error && <p className="lv-alert lv-alert-error">{error}</p>}
            </form>
          ) : (
            <button className="lv-button" type="button" onClick={() => setEditing(true)}>
              <ImageIcon size={16} />
              Cover art
            </button>
          ))}
      </div>
    </div>
  );
}

type Props = {
  track: TrackRecord;
  section: Section;
  settings: Settings;
  actions: TrackActions;
  onClose: () => void;
};

/** One track full size, with its name, caption, and tags editable in place. */
export function PreviewDialog({ track, section, settings, actions, onClose }: Props) {
  const toast = useToast();
  const shownName = displayName(track.name);
  const { stem: shownStem } = splitName(shownName);
  const { suffix } = splitName(track.name);

  const rename = async (draft: string) => {
    const stem = draft.trim();
    if (stem === shownStem) return;
    const newName = `${stem}${suffix}`;
    await actions.rename.mutateAsync({ name: track.name, newName });
    toast(`Renamed to ${newName}.`);
    // The file moved, so this dialog's track no longer exists under its old name.
    onClose();
  };

  return (
    <Dialog title={shownName} size="large" onClose={onClose}>
      <Player track={track} section={section} actions={actions} />
      {section !== "hidden" && (
        <DetailRow icon={<FileAudio size={16} />}>
          <EditableText
            key={shownStem}
            label="Name"
            value={shownStem}
            maxLength={settings.name_max_chars}
            placeholder={`Letters, numbers, and underscores (${suffix} is kept)`}
            save={rename}
          />
        </DetailRow>
      )}
      <DetailRow icon={<Text size={16} />}>
        <EditableText
          label="Description"
          value={track.caption ?? ""}
          maxLength={settings.caption_max_chars}
          save={(caption) => actions.updateMetadata.mutateAsync({ name: track.name, change: { caption } })}
        />
      </DetailRow>
      <DetailRow icon={<Tag size={16} />}>
        <TagEditor track={track} maxTags={settings.max_tags} actions={actions} />
      </DetailRow>
      {track.analysis_model && (
        <DetailRow icon={<Bot size={16} />}>
          <span className="lv-detail-text">Analyzed by {track.analysis_model}</span>
        </DetailRow>
      )}
    </Dialog>
  );
}

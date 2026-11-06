import { ArrowLeft, ArrowRight, Check, Download, Eye, EyeOff, Heart, ImageIcon, Pencil, Plus, Trash2, X } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { coverUrl, downloadUrl, fileUrl, type TrackActions, type TrackRecord, type Section, type Settings } from "../api";
import { displayName, durationLabel, messageOf, normalizedTag, readableName, sizeLabel, splitName, tagSlot, visibleTags } from "../lib";
import { useNowPlaying } from "../nowPlaying";
import { RepeatButton, useRepeat } from "../repeat";
import { BrowserVolume, useSharedVolume } from "../volume";
import { useModal } from "./Dialog";
import type { CardAction } from "./TrackCard";
import { useToast } from "./Toasts";

type EditableProps = {
  label: string;
  value: string;
  /** What to show while not editing, when it differs from the text being edited. */
  shown?: string;
  maxLength: number;
  placeholder?: string;
  /** Resolve to close the editor; reject to keep it open with the error. */
  save: (draft: string) => Promise<unknown>;
};

/** Text with a pencil: Enter or the checkmark saves, Escape cancels. */
function EditableText({ label, value, shown, maxLength, placeholder, save }: EditableProps) {
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
      <div className="lv-detail-line lv-detail-line-top">
        <span className="lv-detail-text">{shown ?? value}</span>
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
    <div className="lv-preview-tags">
      {visibleTags(tags).map((tag) => (
        <button
          className={`lv-tag lv-tag-${tagSlot(tag)} lv-tag-removable`}
          type="button"
          key={tag}
          aria-label={`Remove tag ${tag}`}
          onClick={() => removeTag(tag)}
        >
          {tag}
          <X size={12} />
        </button>
      ))}
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

type Props = {
  track: TrackRecord;
  /** Where this track sits in the gallery being browsed, from 1. */
  position: number;
  total: number;
  /** The track the next-arrow leads to, fetched ahead so stepping forward is immediate. */
  next: TrackRecord;
  section: Section;
  settings: Settings;
  actions: TrackActions;
  /** The tracks being browsed, in order: what plays next once this view closes. */
  names: string[];
  onStep: (delta: number) => void;
  onAction: (action: CardAction, track: TrackRecord) => void;
  onClose: () => void;
};

function CoverEditor({ track, actions }: { track: TrackRecord; actions: TrackActions }) {
  const [editing, setEditing] = useState(false);
  const [url, setUrl] = useState(track.cover_url ?? "");
  const [error, setError] = useState("");

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      await actions.setCover.mutateAsync({ name: track.name, coverUrl: url.trim() || null });
      setEditing(false);
    } catch (failure) {
      setError(messageOf(failure, "Could not set the cover."));
    }
  };

  if (!editing) {
    return (
      <button className="lv-button lv-button-wide" type="button" onClick={() => setEditing(true)}>
        <ImageIcon size={16} />
        Cover art
      </button>
    );
  }
  return (
    <form className="lv-cover-form" onSubmit={save}>
      <p className="lv-caption">Paste a Luna Visia image link (…/api/public/images/&lt;id&gt;), or clear it.</p>
      <input className="lv-input" aria-label="Visia image URL" autoFocus value={url} onChange={(event) => setUrl(event.target.value)} />
      {error && <p className="lv-alert lv-alert-error">{error}</p>}
      <button className="lv-button" type="submit">
        Save cover
      </button>
    </form>
  );
}

/** One track filling the window, with its player on the stage and its details and actions in a side panel. */
export function PreviewDialog({ track, position, total, next, section, settings, actions, names, onStep, onAction, onClose }: Props) {
  const ref = useModal();
  const toast = useToast();
  const shownName = readableName(track.name);
  const { stem: storedStem } = splitName(displayName(track.name));
  const { suffix } = splitName(track.name);

  useEffect(() => {
    new Image().src = coverUrl(next, "large");
  }, [next]);

  // Repeat all carries on to the next track (and round to the first); repeat one plays this one again.
  const repeat = useRepeat("lv-repeat-track");
  const [continuing, setContinuing] = useState(false);
  const step = (delta: number) => {
    setContinuing(false);
    onStep(delta);
  };
  const ended = () => {
    playing.current = false;
    if (repeat.mode !== "all" || total < 2) return;
    setContinuing(true);
    onStep(1);
  };

  // Closing the view hands a playing song to the page's player, which carries on from the
  // same second with the rest of the list after it. Hidden tracks stop instead, so nothing
  // hidden plays on once their tab is left.
  const nowPlaying = useNowPlaying();
  const audio = useRef<HTMLAudioElement | null>(null);
  const volume = useSharedVolume();
  const playing = useRef(false);
  const latest = useRef({ track, names, section });
  latest.current = { track, names, section };
  useLayoutEffect(
    () => () => {
      const { track: current, names: list, section: from } = latest.current;
      if (!playing.current || !audio.current || from === "hidden") return;
      const index = list.indexOf(current.name);
      if (index < 0) return;
      nowPlaying.play({
        playlist: from === "favorites" ? "Favorites" : "Library",
        names: list,
        index,
        startAt: audio.current.currentTime,
      });
    },
    [nowPlaying],
  );

  const rename = async (draft: string) => {
    const stem = draft.trim();
    if (stem === storedStem) return;
    const newName = `${stem}${suffix}`;
    await actions.rename.mutateAsync({ name: track.name, newName });
    toast(`Renamed to ${newName}.`);
    // The file moved, so this dialog's track no longer exists under its old name.
    onClose();
  };

  const stepWithArrowKeys = (event: KeyboardEvent) => {
    if (event.target instanceof HTMLInputElement || event.target instanceof HTMLAudioElement) return;
    if (event.key === "ArrowLeft") step(-1);
    if (event.key === "ArrowRight") step(1);
  };

  return (
    <dialog
      ref={ref}
      className="lv-viewer"
      aria-label={shownName}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onKeyDown={stepWithArrowKeys}
    >
      <div className="lv-viewer-body">
        <div
          className="lv-stage"
          onClick={(event) => {
            if (event.target === event.currentTarget) onClose();
          }}
        >
          <div className="lv-player">
            <img src={coverUrl(track, "large")} alt="" width={720} height={480} />
            {/* Keyed so stepping to another track never keeps playing the last one. */}
            <audio
              key={track.name}
              controls
              preload="metadata"
              src={fileUrl(track)}
              autoPlay={continuing}
              loop={repeat.mode === "one" || (repeat.mode === "all" && total < 2)}
              ref={(element) => {
                if (element) audio.current = element;
                volume.ref(element);
              }}
              onVolumeChange={volume.onVolumeChange}
              // Playing here takes over from the page's player, so two songs never play at once.
              onPlay={() => {
                playing.current = true;
                nowPlaying.stop();
              }}
              onPause={() => (playing.current = false)}
              onEnded={ended}
            />
            <div className="lv-player-controls">
              <RepeatButton mode={repeat.mode} onCycle={repeat.cycle} />
              <BrowserVolume />
            </div>
          </div>
          {total > 1 && (
            <>
              <button className="lv-step lv-step-prev" type="button" aria-label="Previous track" onClick={() => step(-1)}>
                <ArrowLeft size={18} />
              </button>
              <button className="lv-step lv-step-next" type="button" aria-label="Next track" onClick={() => step(1)}>
                <ArrowRight size={18} />
              </button>
            </>
          )}
        </div>
        {/* Keyed so a half-finished edit never carries over to the next track. */}
        <aside className="lv-panel" aria-label="Track details" key={track.name}>
          <div className="lv-panel-top">
            <span>
              {position} of {total}
            </span>
            <button className="lv-icon-button" type="button" aria-label="Close" onClick={onClose}>
              <X size={18} />
            </button>
          </div>
          <div className="lv-viewer-name">
            {section === "hidden" ? (
              <span className="lv-detail-text">{shownName}</span>
            ) : (
              <EditableText
                key={storedStem}
                label="Name"
                value={storedStem}
                shown={shownName}
                maxLength={settings.name_max_chars}
                placeholder={`Letters, numbers, and underscores (${suffix} is kept)`}
                save={rename}
              />
            )}
          </div>
          <section>
            <h3 className="lv-section">Description</h3>
            <EditableText
              label="Description"
              value={track.caption ?? ""}
              maxLength={settings.caption_max_chars}
              save={(caption) => actions.updateMetadata.mutateAsync({ name: track.name, change: { caption } })}
            />
          </section>
          <section>
            <h3 className="lv-section">Tags</h3>
            <TagEditor track={track} maxTags={settings.max_tags} actions={actions} />
          </section>
          <section>
            <h3 className="lv-section">Details</h3>
            <dl className="lv-facts">
              {track.title && (
                <>
                  <dt>Title</dt>
                  <dd>{track.title}</dd>
                </>
              )}
              {track.artist && (
                <>
                  <dt>Artist</dt>
                  <dd>{track.artist}</dd>
                </>
              )}
              <dt>Length</dt>
              <dd>{durationLabel(track.duration_seconds)}</dd>
              {Boolean(track.tempo_bpm) && (
                <>
                  <dt>Tempo</dt>
                  <dd>{Math.round(track.tempo_bpm!)} BPM</dd>
                </>
              )}
              {track.musical_key && (
                <>
                  <dt>Key</dt>
                  <dd>{track.musical_key}</dd>
                </>
              )}
              {track.energy !== null && track.energy !== undefined && (
                <>
                  <dt>Energy</dt>
                  <dd>{Math.round(track.energy * 100)}%</dd>
                </>
              )}
              <dt>Size</dt>
              <dd>{sizeLabel(track.size_bytes)}</dd>
              {suffix && (
                <>
                  <dt>Format</dt>
                  <dd>{suffix.slice(1).toUpperCase()}</dd>
                </>
              )}
              {track.analysis_model && (
                <>
                  <dt>Analyzed by</dt>
                  <dd>{track.analysis_model}</dd>
                </>
              )}
            </dl>
          </section>
          {section !== "hidden" && <CoverEditor key={track.cover_url ?? ""} track={track} actions={actions} />}
          <div className="lv-panel-actions">
            {section !== "hidden" && (
              <button
                className={`lv-icon-button${track.favorite ? " lv-favorite-active" : ""}`}
                type="button"
                aria-label={track.favorite ? "Remove from favorites" : "Add to favorites"}
                aria-pressed={Boolean(track.favorite)}
                title={track.favorite ? "Remove from favorites" : "Add to favorites"}
                onClick={() => onAction("favorite", track)}
              >
                <Heart size={18} fill={track.favorite ? "currentColor" : "none"} />
              </button>
            )}
            <a className="lv-icon-button" href={downloadUrl(track, displayName(track.name))} aria-label="Download" title="Download">
              <Download size={18} />
            </a>
            {section === "view" && (
              <button className="lv-icon-button" type="button" aria-label="Hide" title="Hide" onClick={() => onAction("hide", track)}>
                <EyeOff size={18} />
              </button>
            )}
            {section === "hidden" && (
              <button className="lv-icon-button" type="button" aria-label="Restore" title="Restore" onClick={() => onAction("restore", track)}>
                <Eye size={18} />
              </button>
            )}
            <button className="lv-icon-button" type="button" aria-label="Delete" title="Delete" onClick={() => onAction("delete", track)}>
              <Trash2 size={18} />
            </button>
          </div>
        </aside>
      </div>
    </dialog>
  );
}

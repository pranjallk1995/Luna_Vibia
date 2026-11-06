/** The Playlists tab: saved playlists, their order, and a player that shuffles and repeats. */

import {
  ChevronDown,
  ChevronUp,
  ListMusic,
  Pencil,
  Play,
  Plus,
  Shuffle,
  SkipBack,
  SkipForward,
  Square,
  Trash2,
  X,
} from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";

import {
  coverUrl,
  fileUrl,
  usePlaylist,
  usePlaylistActions,
  usePlaylists,
  useTracks,
  type PlaylistTrack,
  type TrackRecord,
} from "../api";
import { durationLabel, matching, messageOf, readableName, remember, remembered } from "../lib";
import { RepeatButton, useRepeat, type RepeatMode } from "../repeat";
import { ConfirmDialog } from "./ConfirmDialog";
import { Dialog } from "./Dialog";
import { useToast } from "./Toasts";

const minutes = (seconds: number) => `${Math.max(1, Math.round(seconds / 60))} min`;

/** Shuffling only changes what plays next: the saved order stays. */
function shuffled<T>(items: T[]): T[] {
  const copy = [...items];
  for (let index = copy.length - 1; index > 0; index -= 1) {
    const other = Math.floor(Math.random() * (index + 1));
    [copy[index], copy[other]] = [copy[other], copy[index]];
  }
  return copy;
}

type Queue = { playlist: string; names: string[]; index: number };

/** What plays now: a playlist's tracks in an order, moving on (or not) as repeat says. */
function Player({
  queue,
  library,
  repeat,
  onRepeat,
  onMove,
  onStop,
}: {
  queue: Queue;
  library: Map<string, TrackRecord>;
  repeat: RepeatMode;
  onRepeat: () => void;
  onMove: (index: number) => void;
  onStop: () => void;
}) {
  const name = queue.names[queue.index];
  const track = library.get(name);
  const last = queue.index === queue.names.length - 1;
  const step = (delta: number) => {
    const target = queue.index + delta;
    if (target >= 0 && target < queue.names.length) onMove(target);
    else if (repeat === "all") onMove((target + queue.names.length) % queue.names.length);
  };
  const ended = () => {
    if (last && repeat !== "all") return onStop();
    step(1);
  };
  if (!track) return null;
  return (
    <section className="lv-queue-player" aria-label="Now playing">
      <img src={coverUrl(track, "card")} alt="" width={96} height={64} />
      <div className="lv-queue-now">
        <strong>{readableName(name)}</strong>
        <span className="lv-caption">
          {queue.playlist} · {queue.index + 1} of {queue.names.length}
        </span>
        <audio
          key={`${queue.index}-${name}`}
          controls
          autoPlay
          src={fileUrl(track)}
          loop={repeat === "one"}
          onEnded={ended}
        />
      </div>
      <div className="lv-queue-buttons">
        <button className="lv-icon-button" type="button" aria-label="Previous track" onClick={() => step(-1)}>
          <SkipBack size={18} />
        </button>
        <button className="lv-icon-button" type="button" aria-label="Next track" onClick={() => step(1)}>
          <SkipForward size={18} />
        </button>
        <RepeatButton mode={repeat} onCycle={onRepeat} />
        <button className="lv-icon-button" type="button" aria-label="Stop" onClick={onStop}>
          <Square size={16} />
        </button>
      </div>
    </section>
  );
}

/** Pick library tracks to add, searching by name or tag. */
function AddTracksDialog({
  playlist,
  present,
  library,
  onClose,
}: {
  playlist: string;
  present: Set<string>;
  library: TrackRecord[];
  onClose: () => void;
}) {
  const { add } = usePlaylistActions();
  const [query, setQuery] = useState("");
  const [chosen, setChosen] = useState<string[]>([]);
  const [error, setError] = useState("");
  const options = matching(library.filter((track) => !present.has(track.name)), query);

  const toggle = (name: string) =>
    setChosen((current) => (current.includes(name) ? current.filter((item) => item !== name) : [...current, name]));

  const submit = async () => {
    setError("");
    try {
      await add.mutateAsync({ name: playlist, tracks: chosen });
      onClose();
    } catch (failure) {
      setError(messageOf(failure, "Could not add those tracks."));
    }
  };

  return (
    <Dialog title={`Add to ${playlist}`} onClose={onClose}>
      <input
        className="lv-input"
        type="search"
        placeholder="Search by filename or tag"
        aria-label="Search tracks to add"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        autoFocus
      />
      <ul className="lv-pick-list">
        {options.map((track) => (
          <li key={track.name}>
            <label>
              <input type="checkbox" checked={chosen.includes(track.name)} onChange={() => toggle(track.name)} />
              <span>{readableName(track.name)}</span>
              <span className="lv-caption">{durationLabel(track.duration_seconds)}</span>
            </label>
          </li>
        ))}
        {!options.length && <li className="lv-caption">No other tracks match.</li>}
      </ul>
      {error && <p className="lv-alert lv-alert-error">{error}</p>}
      <div className="lv-confirm-actions">
        <button className="lv-button" type="button" onClick={onClose}>
          Cancel
        </button>
        <button className="lv-button lv-button-primary" type="button" disabled={!chosen.length || add.isPending} onClick={submit}>
          <Plus size={17} />
          Add {chosen.length || ""} {chosen.length === 1 ? "track" : "tracks"}
        </button>
      </div>
    </Dialog>
  );
}

function RenameForm({ name, onDone }: { name: string; onDone: (renamed?: string) => void }) {
  const { update } = usePlaylistActions();
  const [draft, setDraft] = useState(name);
  const [error, setError] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (draft.trim() === name) return onDone();
    try {
      const saved = await update.mutateAsync({ name, newName: draft });
      onDone(saved.name);
    } catch (failure) {
      setError(messageOf(failure, "Could not rename the playlist."));
    }
  };
  return (
    <form className="lv-playlist-rename" onSubmit={submit}>
      <input className="lv-input" aria-label="Playlist name" value={draft} maxLength={100} autoFocus onChange={(event) => setDraft(event.target.value)} />
      <button className="lv-button lv-button-primary" type="submit" disabled={update.isPending}>
        Save
      </button>
      <button className="lv-icon-button" type="button" aria-label="Cancel" onClick={() => onDone()}>
        <X size={16} />
      </button>
      {error && <p className="lv-alert lv-alert-error">{error}</p>}
    </form>
  );
}

export function Playlists() {
  const toast = useToast();
  const playlists = usePlaylists();
  const libraryQuery = useTracks("view");
  const library = useMemo(
    () => new Map((libraryQuery.data ?? []).map((track) => [track.name, track] as const)),
    [libraryQuery.data],
  );
  const actions = usePlaylistActions();
  const [selected, setSelected] = useState<string | null>(() => {
    try {
      return localStorage.getItem("lv-playlist");
    } catch {
      return null;
    }
  });
  const names = (playlists.data ?? []).map((playlist) => playlist.name);
  const current = selected && names.includes(selected) ? selected : (names[0] ?? null);
  const playlist = usePlaylist(current);
  const [newName, setNewName] = useState("");
  const [adding, setAdding] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [shuffle, setShuffle] = useState(() => remembered("lv-shuffle", ["on", "off"] as const, "off") === "on");
  const repeat = useRepeat("lv-repeat-playlist");
  const [queue, setQueue] = useState<Queue | null>(null);

  const choose = (name: string) => {
    setSelected(name);
    setRenaming(false);
    try {
      localStorage.setItem("lv-playlist", name);
    } catch {
      // Storage may be refused; the choice lasts until reload.
    }
  };

  const toggleShuffle = () => {
    setShuffle((on) => {
      remember("lv-shuffle", on ? "off" : "on");
      return !on;
    });
  };

  const create = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const saved = await actions.create.mutateAsync({ name: newName });
      setNewName("");
      choose(saved.name);
    } catch (failure) {
      toast(messageOf(failure, "Could not create the playlist."));
    }
  };

  const tracks: PlaylistTrack[] = playlist.data?.tracks ?? [];
  const play = (from?: string) => {
    if (!current || !tracks.length) return;
    let order = tracks.map((track) => track.name);
    if (shuffle) order = from ? [from, ...shuffled(order.filter((name) => name !== from))] : shuffled(order);
    setQueue({ playlist: current, names: order, index: from && !shuffle ? order.indexOf(from) : 0 });
  };

  const run = (work: Promise<unknown>, failed: string) => work.catch((failure) => toast(messageOf(failure, failed)));
  const move = (track: string, position: number) => {
    if (current) void run(actions.move.mutateAsync({ name: current, track, position }), "Could not move the track.");
  };
  const takeOut = (track: string) => {
    if (current) void run(actions.removeTracks.mutateAsync({ name: current, tracks: [track] }), "Could not remove the track.");
  };

  return (
    <div className="lv-playlists">
      <aside className="lv-playlist-list" aria-label="Playlists">
        <form className="lv-playlist-new" onSubmit={create}>
          <input
            className="lv-input"
            aria-label="New playlist name"
            placeholder="New playlist"
            maxLength={100}
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
          />
          <button className="lv-button lv-button-primary" type="submit" aria-label="Create playlist" disabled={!newName.trim() || actions.create.isPending}>
            <Plus size={17} />
          </button>
        </form>
        {playlists.error && <p className="lv-alert lv-alert-error">{playlists.error.message}</p>}
        {playlists.data && !playlists.data.length && (
          <p className="lv-caption">No playlists yet. Name one above, or ask an assistant to make one from a mood.</p>
        )}
        {(playlists.data ?? []).map((item) => (
          <button
            key={item.name}
            type="button"
            className={item.name === current ? "lv-playlist-item lv-playlist-active" : "lv-playlist-item"}
            aria-current={item.name === current ? "true" : undefined}
            onClick={() => choose(item.name)}
          >
            <ListMusic size={17} />
            <span>
              <strong>{item.name}</strong>
              <small>
                {item.track_count} {item.track_count === 1 ? "track" : "tracks"}
                {item.track_count > 0 && ` · ${minutes(item.duration_seconds)}`}
              </small>
            </span>
          </button>
        ))}
      </aside>

      <section className="lv-playlist-detail" aria-label={current ?? "Playlist"}>
        {queue && (
          <Player
            queue={queue}
            library={library}
            repeat={repeat.mode}
            onRepeat={repeat.cycle}
            onMove={(index) => setQueue({ ...queue, index })}
            onStop={() => setQueue(null)}
          />
        )}
        {current && playlist.data && (
          <>
            <header className="lv-playlist-head">
              {renaming ? (
                <RenameForm
                  name={current}
                  onDone={(renamed) => {
                    setRenaming(false);
                    if (renamed) choose(renamed);
                  }}
                />
              ) : (
                <h2>
                  {playlist.data.name}
                  <button className="lv-icon-button" type="button" aria-label="Rename playlist" onClick={() => setRenaming(true)}>
                    <Pencil size={15} />
                  </button>
                </h2>
              )}
              {playlist.data.description && <p className="lv-caption">{playlist.data.description}</p>}
              <div className="lv-playlist-actions">
                <button className="lv-button lv-button-primary" type="button" disabled={!tracks.length} onClick={() => play()}>
                  <Play size={17} />
                  Play
                </button>
                <button
                  className={`lv-button${shuffle ? " lv-button-active" : ""}`}
                  type="button"
                  aria-pressed={shuffle}
                  onClick={toggleShuffle}
                  title="Play in a random order; the saved order stays"
                >
                  <Shuffle size={17} />
                  Shuffle
                </button>
                <RepeatButton mode={repeat.mode} onCycle={repeat.cycle} />
                <button className="lv-button" type="button" onClick={() => setAdding(true)}>
                  <Plus size={17} />
                  Add tracks
                </button>
                <button className="lv-button" type="button" aria-label="Delete playlist" onClick={() => setDeleting(true)}>
                  <Trash2 size={17} />
                </button>
              </div>
            </header>
            {!tracks.length && <p className="lv-alert">This playlist is empty. Add tracks from your library.</p>}
            <ol className="lv-playlist-tracks">
              {tracks.map((track, index) => {
                const record = library.get(track.name);
                const playing = queue?.playlist === current && queue.names[queue.index] === track.name;
                return (
                  <li key={track.name} className={playing ? "lv-playlist-track lv-playlist-playing" : "lv-playlist-track"}>
                    <button className="lv-playlist-play" type="button" aria-label={`Play ${readableName(track.name)}`} onClick={() => play(track.name)}>
                      {record ? <img src={coverUrl(record, "card")} alt="" width={60} height={40} /> : <Play size={16} />}
                    </button>
                    <span className="lv-playlist-name">
                      <strong>{readableName(track.name)}</strong>
                      {track.artist && <small>{track.artist}</small>}
                    </span>
                    <span className="lv-caption">{durationLabel(track.duration_seconds)}</span>
                    <span className="lv-playlist-row-actions">
                      <button className="lv-icon-button" type="button" aria-label="Move up" disabled={index === 0} onClick={() => move(track.name, index)}>
                        <ChevronUp size={16} />
                      </button>
                      <button
                        className="lv-icon-button"
                        type="button"
                        aria-label="Move down"
                        disabled={index === tracks.length - 1}
                        onClick={() => move(track.name, index + 2)}
                      >
                        <ChevronDown size={16} />
                      </button>
                      <button className="lv-icon-button" type="button" aria-label="Remove from playlist" onClick={() => takeOut(track.name)}>
                        <X size={16} />
                      </button>
                    </span>
                  </li>
                );
              })}
            </ol>
          </>
        )}
        {playlist.error && <p className="lv-alert lv-alert-error">{playlist.error.message}</p>}
      </section>

      {adding && current && (
        <AddTracksDialog
          playlist={current}
          present={new Set(tracks.map((track) => track.name))}
          library={libraryQuery.data ?? []}
          onClose={() => setAdding(false)}
        />
      )}
      {deleting && current && (
        <ConfirmDialog
          title="Delete playlist?"
          message="Delete the playlist (its tracks stay in your library):"
          subject={current}
          action="Delete"
          icon={Trash2}
          run={async () => {
            await actions.remove.mutateAsync(current);
            if (queue?.playlist === current) setQueue(null);
          }}
          onClose={() => setDeleting(false)}
        />
      )}
    </div>
  );
}

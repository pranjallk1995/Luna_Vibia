import { CheckSquare, EyeOff, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  coverUrl,
  useTrackActions,
  useTracks,
  type TrackRecord,
  type NamedMetadataChange,
  type Section,
  type Settings,
} from "../api";
import {
  clickedSelection,
  displayName,
  matching,
  messageOf,
  outcomeMessage,
  pageCount,
  pageOf,
  selectionLabel,
  type BatchOutcome,
} from "../lib";
import { BulkBar, type BulkAction } from "./BulkBar";
import { BulkEditDialog } from "./BulkEditDialog";
import { ConfirmDialog } from "./ConfirmDialog";
import { TrackCard, type CardAction } from "./TrackCard";
import { Pager } from "./Pager";
import { PreviewDialog } from "./PreviewDialog";
import { SearchBox } from "./SearchBox";
import { useToast } from "./Toasts";

const COPY: Record<Section, { label: string; noMatch: string }> = {
  view: { label: "Search by track name", noMatch: "No filenames or tags match your search." },
  favorites: { label: "Search Favorites by track name", noMatch: "No favorite filenames or tags match your search." },
  hidden: { label: "Search hidden vault by track name", noMatch: "No hidden filenames or tags match your search." },
};

type Pending = { kind: "delete" | "hide"; track: TrackRecord } | null;

// Kept from when the prompt opened: the selection empties on screen once the change starts.
type BulkPending = { kind: "delete" | "hide"; names: string[]; subject: string } | { kind: "edit" } | null;

type Props = {
  section: Section;
  layout: "grid" | "list";
  settings: Settings;
};

export function Gallery({ section, layout, settings }: Props) {
  const { data, isPending, error } = useTracks(section);
  const actions = useTrackActions(section, settings.batch_size);
  const toast = useToast();
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [openName, setOpenName] = useState<string | null>(null);
  const [pending, setPending] = useState<Pending>(null);
  const [selecting, setSelecting] = useState(false);
  const [selection, setSelection] = useState<ReadonlySet<string>>(() => new Set());
  const [bulkPending, setBulkPending] = useState<BulkPending>(null);

  const inThisSection = useMemo(() => section === "favorites" ? (data ?? []).filter((track) => track.favorite) : (data ?? []), [data, section]);
  const filtered = useMemo(() => matching(inThisSection, query), [inThisSection, query]);
  // Read from the section's tracks, so anything deleted or moved away drops out by itself.
  const selected = useMemo(() => inThisSection.filter((track) => selection.has(track.name)), [inThisSection, selection]);
  const selectedNames = useMemo(() => selected.map((track) => track.name), [selected]);
  const outside = selected.length - filtered.filter((track) => selection.has(track.name)).length;
  const count = pageCount(filtered.length, settings.tracks_per_page);
  const current = Math.min(page, count - 1);
  const tracks = pageOf(filtered, current, settings.tracks_per_page);
  const openIndex = filtered.findIndex((track) => track.name === openName);

  // Fetch the next page's thumbnails while idle, so paging forward shows them at once.
  useEffect(() => {
    const next = pageOf(filtered, current + 1, settings.tracks_per_page);
    const handle = setTimeout(() => next.forEach((track) => (new Image().src = coverUrl(track, "card"))), 300);
    return () => clearTimeout(handle);
  }, [filtered, current, settings.tracks_per_page]);

  const { setFavorite, restore } = actions;
  const onAction = useCallback(
    (action: CardAction, track: TrackRecord) => {
      if (action === "open") setOpenName(track.name);
      if (action === "delete" || action === "hide") setPending({ kind: action, track });
      if (action === "favorite") {
        setFavorite.mutate(
          { name: track.name, favorite: !track.favorite },
          { onError: (failure) => toast(messageOf(failure, "Could not update Favorite status.")) },
        );
      }
      if (action === "restore") {
        restore.mutate(track.name, { onError: (failure) => toast(messageOf(failure, "Could not restore the track.")) });
      }
    },
    // Mutation objects change identity as they run; their mutate functions do not.
    [setFavorite.mutate, restore.mutate, toast],
  );

  // Refs keep onSelect stable, so selecting one card does not re-render the others.
  const order = useRef<string[]>([]);
  order.current = filtered.map((track) => track.name);
  const anchor = useRef<string | null>(null);

  const onSelect = useCallback((track: TrackRecord, extend: boolean) => {
    const from = extend ? anchor.current : null;
    anchor.current = track.name;
    setSelection((current) => clickedSelection(current, order.current, track.name, from));
  }, []);

  const toggleSelecting = () => {
    setSelecting((current) => !current);
    setSelection(new Set());
    anchor.current = null;
  };

  /** Say how a bulk action went, leaving only the tracks it could not change selected. */
  const report = (outcome: BatchOutcome, action: string) => {
    toast(outcomeMessage(outcome, action));
    if (outcome.failed.length) setSelection(new Set(outcome.failed.map((failure) => failure.name)));
  };

  const setFavorites = (favorite: boolean) => {
    const names = selected.filter((track) => Boolean(track.favorite) !== favorite).map((track) => track.name);
    actions.setFavorites
      .mutateAsync({ names, favorite })
      .then((outcome) => report(outcome, favorite ? "added to Favorites" : "removed from Favorites"))
      .catch((failure) => toast(messageOf(failure, "Could not update Favorite status.")));
  };

  const onBulkAction = (action: BulkAction) => {
    if (action === "favorite" || action === "unfavorite") return setFavorites(action === "favorite");
    if (action === "restore") {
      return void actions.restoreMany
        .mutateAsync(selectedNames)
        .then((outcome) => report(outcome, "restored"))
        .catch((failure) => toast(messageOf(failure, "Could not restore the tracks.")));
    }
    if (action === "edit") return setBulkPending({ kind: "edit" });
    // A destructive prompt names what the search is not showing, so nothing goes unnoticed.
    const subject = `${selectionLabel(selectedNames)}${outside > 0 ? ` (${outside} outside this search)` : ""}`;
    setBulkPending({ kind: action, names: selectedNames, subject });
  };

  const editSelected = async (changes: NamedMetadataChange[]) =>
    report(await actions.updateMetadataMany.mutateAsync(changes), "updated");

  const changeQuery = (value: string) => {
    setQuery(value);
    setPage(0);
  };

  const changePage = (target: number) => {
    setPage(target);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // The gallery follows along behind the viewer, so closing it lands on the track last seen.
  const stepViewer = (delta: number) => {
    const index = (openIndex + delta + filtered.length) % filtered.length;
    setOpenName(filtered[index].name);
    setPage(Math.floor(index / settings.tracks_per_page));
  };

  return (
    <>
      <div className="lv-gallery-tools">
        <SearchBox label={COPY[section].label} value={query} count={data ? filtered.length : undefined} onChange={changeQuery} />
        <button
          className={`lv-button lv-select-toggle${selecting ? " lv-button-active" : ""}`}
          type="button"
          aria-pressed={selecting}
          disabled={!selecting && !filtered.length}
          onClick={toggleSelecting}
        >
          {selecting ? <X size={17} /> : <CheckSquare size={17} />}
          <span>{selecting ? "Done" : "Select"}</span>
        </button>
      </div>
      {error && <p className="lv-alert lv-alert-error">{error.message}</p>}
      {isPending && <div className="lv-skeleton-grid" aria-label="Loading tracks" />}
      {data && !filtered.length && (
        <p className="lv-alert">{query.trim() ? COPY[section].noMatch : "No tracks are currently stored in Luna Vibia."}</p>
      )}
      {tracks.length > 0 && (
        <>
          <div className={`lv-gallery lv-gallery-${layout}`} key={`${section}-${current}`}>
            {tracks.map((track) => (
              <TrackCard
                key={track.name}
                track={track}
                section={section}
                layout={layout}
                onAction={onAction}
                selecting={selecting}
                selected={selection.has(track.name)}
                onSelect={onSelect}
              />
            ))}
          </div>
          <Pager page={current} count={count} onChange={changePage} />
        </>
      )}
      {selecting && (
        <BulkBar
          section={section}
          selected={selected}
          outside={outside}
          matching={filtered.length}
          onSelectAll={() => setSelection((current) => new Set([...current, ...order.current]))}
          onClear={() => setSelection(new Set())}
          onAction={onBulkAction}
        />
      )}
      {openIndex >= 0 && (
        <PreviewDialog
          track={filtered[openIndex]}
          position={openIndex + 1}
          total={filtered.length}
          next={filtered[(openIndex + 1) % filtered.length]}
          section={section}
          settings={settings}
          actions={actions}
          onStep={stepViewer}
          onAction={onAction}
          onClose={() => setOpenName(null)}
        />
      )}
      {pending?.kind === "delete" && (
        <ConfirmDialog
          title="Delete track?"
          message="Permanently delete"
          subject={displayName(pending.track.name)}
          action="Delete"
          icon={Trash2}
          run={() => actions.remove.mutateAsync(pending.track.name)}
          onClose={() => setPending(null)}
        />
      )}
      {pending?.kind === "hide" && (
        <ConfirmDialog
          title="Hide track?"
          message="Move to Hidden Tracks:"
          subject={displayName(pending.track.name)}
          action="Hide"
          icon={EyeOff}
          run={() => actions.hide.mutateAsync(pending.track.name)}
          onClose={() => setPending(null)}
        />
      )}
      {bulkPending?.kind === "delete" && (
        <ConfirmDialog
          title="Delete tracks?"
          message="Permanently delete"
          subject={bulkPending.subject}
          action="Delete"
          icon={Trash2}
          run={async () => report(await actions.removeMany.mutateAsync(bulkPending.names), "deleted")}
          onClose={() => setBulkPending(null)}
        />
      )}
      {bulkPending?.kind === "hide" && (
        <ConfirmDialog
          title="Hide tracks?"
          message="Move to Hidden Tracks:"
          subject={bulkPending.subject}
          action="Hide"
          icon={EyeOff}
          run={async () => report(await actions.hideMany.mutateAsync(bulkPending.names), "hidden")}
          onClose={() => setBulkPending(null)}
        />
      )}
      {bulkPending?.kind === "edit" && (
        <BulkEditDialog tracks={selected} settings={settings} run={editSelected} onClose={() => setBulkPending(null)} />
      )}
    </>
  );
}

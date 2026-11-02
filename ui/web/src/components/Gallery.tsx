import { EyeOff, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { coverUrl, useTrackActions, useTracks, type TrackRecord, type Section, type Settings } from "../api";
import { displayName, matching, messageOf, pageCount, pageOf } from "../lib";
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

type Props = {
  section: Section;
  layout: "grid" | "list";
  settings: Settings;
};

export function Gallery({ section, layout, settings }: Props) {
  const { data, isPending, error } = useTracks(section);
  const actions = useTrackActions(section);
  const toast = useToast();
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [openName, setOpenName] = useState<string | null>(null);
  const [pending, setPending] = useState<Pending>(null);

  const filtered = useMemo(() => matching(section === "favorites" ? (data ?? []).filter((track) => track.favorite) : (data ?? []), query), [data, section, query]);
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
      <SearchBox label={COPY[section].label} value={query} count={data ? filtered.length : undefined} onChange={changeQuery} />
      {error && <p className="lv-alert lv-alert-error">{error.message}</p>}
      {isPending && <div className="lv-skeleton-grid" aria-label="Loading tracks" />}
      {data && !filtered.length && (
        <p className="lv-alert">{query.trim() ? COPY[section].noMatch : "No tracks are currently stored in Luna Vibia."}</p>
      )}
      {tracks.length > 0 && (
        <>
          <div className={`lv-gallery lv-gallery-${layout}`} key={`${section}-${current}`}>
            {tracks.map((track) => (
              <TrackCard key={track.name} track={track} section={section} layout={layout} onAction={onAction} />
            ))}
          </div>
          <Pager page={current} count={count} onChange={changePage} />
        </>
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
    </>
  );
}

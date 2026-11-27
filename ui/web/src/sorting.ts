/** Orders for the gallery: the library's similarity order by default, or by date, name, size, and more. */

import type { TrackRecord } from "./api";
import { displayName, remember, remembered } from "./lib";

const SORT_KEY = "lv-vibia-sort";

const text = (value?: string | null) => (value ?? "").trim();
/** A to Z, or Z to A with ``direction`` -1; either way blanks go last. */
const byText = (a: string, b: string, direction = 1) => {
  if (!a !== !b) return a ? -1 : 1;
  return direction * a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });
};
/** Low to high, or high to low with ``direction`` -1; either way unknowns go last. */
const byNumber = (a?: number | null, b?: number | null, direction = 1) => {
  if ((a == null) !== (b == null)) return a == null ? 1 : -1;
  return direction * ((a ?? 0) - (b ?? 0));
};
const time = (value?: string | null) => (value ? Date.parse(value) : NaN);
/** Earliest first, or latest first with ``direction`` -1; either way undated items go last. */
const byTime = (a?: string | null, b?: string | null, direction = 1) => {
  const [x, y] = [time(a), time(b)];
  if (Number.isNaN(x) !== Number.isNaN(y)) return Number.isNaN(x) ? 1 : -1;
  return direction * ((Number.isNaN(x) ? 0 : x) - (Number.isNaN(y) ? 0 : y));
};

type Option<T> = { id: string; label: string; compare?: (a: T, b: T) => number };

/** Items in the chosen order; similarity keeps the order the library gives. Ties keep their similarity order. */
export function sortItems<T>(items: T[], options: readonly Option<T>[], id: string): T[] {
  const compare = options.find((option) => option.id === id)?.compare;
  return compare ? [...items].sort(compare) : items;
}

export const sortIds = <T,>(options: readonly Option<T>[]) => options.map((option) => option.id);
export const rememberedSort = <T,>(options: readonly Option<T>[]) => remembered(SORT_KEY, sortIds(options), "similarity");
export const rememberSort = (id: string) => remember(SORT_KEY, id);

const title = (track: TrackRecord) => text(track.title) || displayName(track.name);

export const SORTS: readonly Option<TrackRecord>[] = [
  { id: "similarity", label: "Similarity" },
  { id: "newest", label: "Newest", compare: (a, b) => byTime(a.updated_at, b.updated_at, -1) || byNumber(a.version, b.version, -1) },
  { id: "oldest", label: "Oldest", compare: (a, b) => byTime(a.updated_at, b.updated_at) || byNumber(a.version, b.version) },
  { id: "title", label: "Title, A to Z", compare: (a, b) => byText(title(a), title(b)) },
  { id: "title-desc", label: "Title, Z to A", compare: (a, b) => byText(title(a), title(b), -1) },
  { id: "artist", label: "Artist", compare: (a, b) => byText(text(a.artist), text(b.artist)) || byText(title(a), title(b)) },
  { id: "longest", label: "Longest", compare: (a, b) => byNumber(a.duration_seconds, b.duration_seconds, -1) },
  { id: "shortest", label: "Shortest", compare: (a, b) => byNumber(a.duration_seconds, b.duration_seconds) },
  { id: "fastest", label: "Fastest tempo", compare: (a, b) => byNumber(a.tempo_bpm, b.tempo_bpm, -1) },
  { id: "slowest", label: "Slowest tempo", compare: (a, b) => byNumber(a.tempo_bpm, b.tempo_bpm) },
  { id: "largest", label: "Largest file", compare: (a, b) => byNumber(a.size_bytes, b.size_bytes, -1) },
  { id: "smallest", label: "Smallest file", compare: (a, b) => byNumber(a.size_bytes, b.size_bytes) },
];

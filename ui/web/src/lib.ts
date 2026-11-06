import type { TrackRecord, NamedMetadataChange } from "./api";

/** Small helpers shared across the app. */

/** The server's reason for a failure, or a fallback when there is none. */
export const messageOf = (failure: unknown, fallback: string): string =>
  (failure instanceof Error && failure.message) || fallback;

/** A remembered choice; the app works the same when browser storage is unavailable. */
export function remembered<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const value = localStorage.getItem(key) as T | null;
    return value && allowed.includes(value) ? value : fallback;
  } catch {
    return fallback;
  }
}

export function remember(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // A private window may refuse storage; the choice just lasts until reload.
  }
}

/** Remove the internal upload prefix from a user-facing filename. */
export function displayName(storedName: string): string {
  const separator = storedName.indexOf("_");
  if (separator === 32 && /^[0-9a-f]{32}$/i.test(storedName.slice(0, 32))) {
    const original = storedName.slice(33);
    if (original) return original;
  }
  return storedName;
}

export function sizeLabel(size: number): string {
  if (size >= 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  if (size >= 1024) return `${Math.round(size / 1024)} KB`;
  return `${size} B`;
}

export function durationLabel(seconds?: number | null): string {
  if (!seconds) return "–";
  const total = Math.round(seconds);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export function splitName(name: string): { stem: string; suffix: string } {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? { stem: name.slice(0, dot), suffix: name.slice(dot) } : { stem: name, suffix: "" };
}

/** The name people read on screen: no upload prefix, extension, or underscores. */
export function readableName(storedName: string): string {
  const { stem } = splitName(displayName(storedName));
  return stem.replace(/_+/g, " ").trim() || stem;
}

export const normalizedTag = (tag: string) => tag.toLowerCase().split(/\s+/).filter(Boolean).join(" ");

/** Tags worth showing: almost every track carries the system's "ai info" tag, so it says nothing. */
export const visibleTags = (tags: string[] | null | undefined) =>
  (tags ?? []).filter((tag) => normalizedTag(tag) !== "ai info");

/** A tag's colour slot follows its name, so one tag looks the same on every track. */
export const tagSlot = (tag: string) =>
  Array.from(normalizedTag(tag)).reduce((sum, character) => sum + character.charCodeAt(0), 0) % 6;

type Searchable = { name: string; tags?: string[] | null };

/** Keep records whose display name or any tag contains the query. */
export function matching<T extends Searchable>(records: T[], query: string): T[] {
  const wanted = query.trim().toLowerCase();
  if (!wanted) return records;
  return records.filter(
    (record) =>
      displayName(record.name).toLowerCase().includes(wanted) ||
      (record.tags ?? []).some((tag) => tag.toLowerCase().includes(wanted)),
  );
}

export const pageCount = (total: number, perPage: number) => Math.max(1, Math.ceil(total / perPage));

export const pageOf = <T,>(items: T[], page: number, perPage: number) =>
  items.slice(page * perPage, (page + 1) * perPage);

/**
 * The pages to show, with null for a gap: always seven slots once there are more than
 * seven pages, so the buttons do not shift as you move through them.
 */
export function pageSlots(page: number, count: number): (number | null)[] {
  const all = Array.from({ length: count }, (_, index) => index);
  if (count <= 7) return all;
  const last = count - 1;
  if (page <= 3) return [...all.slice(0, 5), null, last];
  if (page >= last - 3) return [0, null, ...all.slice(last - 4)];
  return [0, null, page - 1, page, page + 1, null, last];
}

/** A stored name that identical filenames can never collide on in the vault. */
export function storedName(fileName: string): string {
  const prefix = Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
  return `${prefix}_${fileName}`;
}

// Bulk selection

/**
 * The selection after clicking one track: a plain click toggles it, and a shift-click
 * from `anchor` adds everything between the two, in the order on screen.
 */
export function clickedSelection(
  selection: ReadonlySet<string>,
  order: readonly string[],
  name: string,
  anchor: string | null,
): Set<string> {
  const next = new Set(selection);
  const from = anchor === null ? -1 : order.indexOf(anchor);
  const to = order.indexOf(name);
  if (from < 0 || to < 0) {
    if (!next.delete(name)) next.add(name);
    return next;
  }
  order.slice(Math.min(from, to), Math.max(from, to) + 1).forEach((item) => next.add(item));
  return next;
}

export type BatchFailure = { name: string; error: string };
export type BatchOutcome = { done: number; failed: BatchFailure[] };

/**
 * Send items a batch at a time, collecting what each track could not do. A refused batch
 * ends the run, because the rest would fail the same way. Rejects only when nothing at all
 * succeeded, so a caller can stay open with the reason.
 */
export async function inBatches<T>(
  items: readonly T[],
  size: number,
  nameOf: (item: T) => string,
  send: (batch: T[]) => Promise<BatchFailure[]>,
): Promise<BatchOutcome> {
  const failed: BatchFailure[] = [];
  for (let start = 0; start < items.length; start += size) {
    try {
      failed.push(...(await send(items.slice(start, start + size))));
    } catch (failure) {
      const error = messageOf(failure, "The request failed. Please try again.");
      failed.push(...items.slice(start).map((item) => ({ name: nameOf(item), error })));
      break;
    }
  }
  if (failed.length && failed.length === items.length) throw new Error(failed[0].error);
  return { done: items.length - failed.length, failed };
}

export const itemCount = (count: number) => `${count} ${count === 1 ? "track" : "tracks"}`;

/** Names a selection before it is changed for good: its size and the first few tracks. */
export function selectionLabel(names: readonly string[], shown = 3): string {
  const readable = names.slice(0, shown).map(readableName).join(", ");
  const rest = names.length - shown;
  return `${itemCount(names.length)}: ${readable}${rest > 0 ? ` and ${rest} more` : ""}`;
}

/** The toast after a bulk action, such as "9 tracks deleted." with any failure's reason. */
export function outcomeMessage({ done, failed }: BatchOutcome, action: string): string {
  const summary = `${itemCount(done)} ${action}.`;
  if (!failed.length) return summary;
  return `${summary} ${itemCount(failed.length)} stayed selected: ${failed[0].error}`;
}

/** Every tag on these tracks with how many carry it, most common first. */
export function tagCounts(records: readonly TrackRecord[]): { tag: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const record of records) {
    for (const tag of visibleTags(record.tags)) counts.set(tag, (counts.get(tag) ?? 0) + 1);
  }
  return Array.from(counts, ([tag, count]) => ({ tag, count })).sort(
    (a, b) => b.count - a.count || a.tag.localeCompare(b.tag),
  );
}

export const parsedTags = (text: string) =>
  Array.from(new Set(text.split(",").map(normalizedTag).filter(Boolean)));

export type CaptionEdit =
  | { mode: "keep" }
  | { mode: "set"; text: string }
  | { mode: "replace"; find: string; replacement: string };

export type BulkEdit = { addTags: string[]; removeTags: string[]; caption: CaptionEdit };

function editedCaption(current: string, edit: CaptionEdit): string {
  if (edit.mode === "set") return edit.text.trim() || current;
  if (edit.mode === "replace" && edit.find) {
    const literal = edit.find.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    // A function, so "$1" in the replacement stays plain text.
    return current.replace(new RegExp(literal, "gi"), () => edit.replacement);
  }
  return current;
}

/** What one bulk edit changes on each track, leaving out tracks it would not change at all. */
export function bulkChanges(records: readonly TrackRecord[], edit: BulkEdit): NamedMetadataChange[] {
  const changes: NamedMetadataChange[] = [];
  for (const track of records) {
    const tags = (track.tags ?? []).map(normalizedTag);
    const removeTags = edit.removeTags.filter((tag) => tags.includes(normalizedTag(tag)));
    const addTags = edit.addTags.filter((tag) => !tags.includes(tag) && !edit.removeTags.includes(tag));
    const current = track.caption ?? "";
    const text = editedCaption(current, edit.caption);
    if (!addTags.length && !removeTags.length && text === current) continue;
    changes.push({
      name: track.name,
      ...(addTags.length && { add_tags: addTags }),
      ...(removeTags.length && { remove_tags: removeTags }),
      ...(text !== current && { caption: text }),
    });
  }
  return changes;
}

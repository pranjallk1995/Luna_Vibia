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

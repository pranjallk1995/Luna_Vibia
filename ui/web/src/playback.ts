import type { Playback } from "./api";

export type Part = { text: string; strong?: boolean };

/** The playback line, or null when there is nothing to show. */
export function describePlayback(status: Playback): Part[] | null {
  const where = status.output?.description;
  if (status.status === "playing") {
    const parts: Part[] = [{ text: "Playing " }, { text: status.now_playing ?? "", strong: true }];
    if (where) parts.push({ text: " on " }, { text: where, strong: true });
    if (status.requested_speaker) {
      parts.push({ text: ` (Windows switched from ${status.requested_speaker.description})` });
    }
    return parts;
  }
  if (status.status === "failed") return [{ text: `Playback stopped: ${status.error ?? "unknown error"}` }];
  if (where) return [{ text: "Speaker: " }, { text: where, strong: true }];
  if (status.output_error) return [{ text: `Speaker unavailable: ${status.output_error}` }];
  return null;
}

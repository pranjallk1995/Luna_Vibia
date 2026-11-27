import { describe, expect, it } from "vitest";

import type { TrackRecord } from "./api";
import { SORTS, sortItems } from "./sorting";

describe("gallery sort orders", () => {
  const item = (name: string, fields: Partial<TrackRecord>) => ({ name, size_bytes: 1, version: 0, ...fields }) as TrackRecord;
  const items = [
    item("song_b.mp3", { title: "Midnight Cafe", artist: "Luna", duration_seconds: 200, tempo_bpm: 90, updated_at: "2026-02-01T00:00:00Z" }),
    item("song_a.mp3", { title: null, artist: "Alto", duration_seconds: 120, tempo_bpm: null, updated_at: "2026-03-01T00:00:00Z" }),
    item("song_c.mp3", { title: "Aurora", artist: null, duration_seconds: null, tempo_bpm: 140, updated_at: null }),
  ];
  const names = (id: string) => sortItems(items, SORTS, id).map((track) => track.name);
  it("keeps similarity by default and sorts by date, title, artist, length, and tempo", () => {
    expect(sortItems(items, SORTS, "similarity")).toBe(items);
    expect(names("newest")).toEqual(["song_a.mp3", "song_b.mp3", "song_c.mp3"]);
    expect(names("title")).toEqual(["song_c.mp3", "song_b.mp3", "song_a.mp3"]);
    expect(names("artist")).toEqual(["song_a.mp3", "song_b.mp3", "song_c.mp3"]);
    expect(names("longest")).toEqual(["song_b.mp3", "song_a.mp3", "song_c.mp3"]);
    expect(names("shortest")).toEqual(["song_a.mp3", "song_b.mp3", "song_c.mp3"]);
    expect(names("fastest")).toEqual(["song_c.mp3", "song_b.mp3", "song_a.mp3"]);
  });
});

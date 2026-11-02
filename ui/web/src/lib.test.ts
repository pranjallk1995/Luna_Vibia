import { describe, expect, it } from "vitest";

import { displayName, durationLabel, matching, normalizedTag, pageCount, pageOf, sizeLabel, splitName, pageSlots } from "./lib";
import { describePlayback } from "./playback";

const SPINX = { name: "Stone Spinx Pro", description: "Bluetooth Speakers (Stone Spinx Pro)" };

describe("names and sizes", () => {
  it("removes the upload prefix but keeps other underscores", () => {
    expect(displayName(`${"a".repeat(32)}_my_song.mp3`)).toBe("my_song.mp3");
    expect(displayName("my_song.mp3")).toBe("my_song.mp3");
  });

  it("labels sizes and durations", () => {
    expect(sizeLabel(2 * 1024 * 1024)).toBe("2.0 MB");
    expect(sizeLabel(2048)).toBe("2 KB");
    expect(durationLabel(125.4)).toBe("2:05");
    expect(durationLabel(null)).toBe("–");
  });

  it("splits a name and normalizes tags", () => {
    expect(splitName("a.b.mp3")).toEqual({ stem: "a.b", suffix: ".mp3" });
    expect(normalizedTag("  Lo   Fi ")).toBe("lo fi");
  });
});

describe("search and paging", () => {
  const tracks = [
    { name: `${"a".repeat(32)}_rain.mp3`, tags: ["calm"] },
    { name: "storm.wav", tags: ["loud"] },
  ];

  it("matches display names and tags", () => {
    expect(matching(tracks, "RAIN")).toHaveLength(1);
    expect(matching(tracks, "loud")).toHaveLength(1);
    expect(matching(tracks, "aaaa")).toHaveLength(0);
    expect(matching(tracks, " ")).toHaveLength(2);
  });

  it("pages", () => {
    expect(pageCount(0, 12)).toBe(1);
    expect(pageCount(13, 12)).toBe(2);
    expect(pageOf([1, 2, 3], 1, 2)).toEqual([3]);
  });
});

describe("playback line", () => {
  const text = (status: Parameters<typeof describePlayback>[0]) => describePlayback(status)?.map((part) => part.text).join("");

  it("names the track and the live speaker", () => {
    expect(
      text({ status: "playing", now_playing: "rain.wav", output: SPINX, requested_speaker: { name: "Echo", description: "Speakers (Echo)" } }),
    ).toBe("Playing rain.wav on Bluetooth Speakers (Stone Spinx Pro) (Windows switched from Speakers (Echo))");
  });

  it("shows the current speaker when idle", () => {
    expect(text({ status: "idle", output: SPINX })).toBe("Speaker: Bluetooth Speakers (Stone Spinx Pro)");
  });

  it("explains why speakers cannot be reached, or stays quiet", () => {
    expect(text({ status: "idle", output: null, output_error: "helper down" })).toBe("Speaker unavailable: helper down");
    expect(describePlayback({ status: "idle", output: null })).toBeNull();
    expect(text({ status: "failed", error: "no device" })).toBe("Playback stopped: no device");
  });
});

describe("pageSlots", () => {
  it("shows every page when they fit", () => {
    expect(pageSlots(0, 1)).toEqual([0]);
    expect(pageSlots(2, 7)).toEqual([0, 1, 2, 3, 4, 5, 6]);
  });

  it("keeps seven slots with gaps around the current page", () => {
    expect(pageSlots(0, 17)).toEqual([0, 1, 2, 3, 4, null, 16]);
    expect(pageSlots(3, 17)).toEqual([0, 1, 2, 3, 4, null, 16]);
    expect(pageSlots(4, 17)).toEqual([0, null, 3, 4, 5, null, 16]);
    expect(pageSlots(12, 17)).toEqual([0, null, 11, 12, 13, null, 16]);
    expect(pageSlots(13, 17)).toEqual([0, null, 12, 13, 14, 15, 16]);
    expect(pageSlots(16, 17)).toEqual([0, null, 12, 13, 14, 15, 16]);
  });

  it("always includes the first, last, and current page", () => {
    for (let page = 0; page < 40; page += 1) {
      const slots = pageSlots(page, 40);
      expect(slots).toHaveLength(7);
      for (const wanted of [0, page, 39]) expect(slots).toContain(wanted);
    }
  });
});

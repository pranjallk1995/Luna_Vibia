import { describe, expect, it } from "vitest";

import type { TrackRecord } from "./api";
import { bulkChanges, clickedSelection, inBatches, outcomeMessage, parsedTags, selectionLabel, tagCounts } from "./lib";

const item = (name: string, tags: string[]): TrackRecord => ({ name, tags, size_bytes: 1, version: 1 });

describe("clickedSelection", () => {
  const order = ["a", "b", "c", "d", "e"];

  it("toggles one track on a plain click", () => {
    expect([...clickedSelection(new Set(), order, "b", null)]).toEqual(["b"]);
    expect([...clickedSelection(new Set(["b"]), order, "b", null)]).toEqual([]);
  });

  it("adds the range from the anchor in either direction, keeping what was selected", () => {
    expect([...clickedSelection(new Set(["a"]), order, "d", "b")].sort()).toEqual(["a", "b", "c", "d"]);
    expect([...clickedSelection(new Set(), order, "b", "d")].sort()).toEqual(["b", "c", "d"]);
  });

  it("falls back to a toggle when the anchor is no longer in the search", () => {
    expect([...clickedSelection(new Set(), order, "b", "gone")]).toEqual(["b"]);
  });
});

describe("inBatches", () => {
  it("splits items into batches and collects each failure", async () => {
    const log: string[][] = [];
    const outcome = await inBatches(["a", "b", "c"], 2, (name) => name, async (batch) => {
      log.push(batch);
      return batch.includes("c") ? [{ name: "c", error: "missing" }] : [];
    });
    expect(log).toEqual([["a", "b"], ["c"]]);
    expect(outcome).toEqual({ done: 2, failed: [{ name: "c", error: "missing" }] });
  });

  it("stops at a refused batch and counts the rest as failed", async () => {
    const outcome = await inBatches(["a", "b", "c"], 1, (name) => name, async ([name]) => {
      if (name === "b") throw new Error("backend down");
      return [];
    });
    expect(outcome.done).toBe(1);
    expect(outcome.failed.map((failure) => failure.name)).toEqual(["b", "c"]);
  });

  it("rejects with the reason when nothing succeeded", async () => {
    await expect(inBatches(["a"], 1, (name) => name, async ([name]) => [{ name, error: "not allowed" }])).rejects.toThrow(
      "not allowed",
    );
  });
});

describe("selection messages", () => {
  it("names the first few tracks and counts the rest", () => {
    expect(selectionLabel(["a_cat.wav"])).toBe("1 track: a cat");
    expect(selectionLabel(["a.wav", "b.wav", "c.wav", "d.wav", "e.wav"])).toBe("5 tracks: a, b, c and 2 more");
  });

  it("gives the outcome, with the first reason for any failure", () => {
    expect(outcomeMessage({ done: 2, failed: [] }, "deleted")).toBe("2 tracks deleted.");
    expect(outcomeMessage({ done: 1, failed: [{ name: "b", error: "Not found." }] }, "hidden")).toBe(
      "1 track hidden. 1 track stayed selected: Not found.",
    );
  });
});

describe("tag helpers", () => {
  it("counts visible tags, most common first", () => {
    expect(tagCounts([item("a", ["tax", "ai info"]), item("b", ["tax", "bank"])])).toEqual([
      { tag: "tax", count: 2 },
      { tag: "bank", count: 1 },
    ]);
  });

  it("parses a comma-separated list into normalized, unique tags", () => {
    expect(parsedTags(" Holiday , big   DOG,,holiday")).toEqual(["holiday", "big dog"]);
  });
});

describe("bulkChanges", () => {
  const keep = { mode: "keep" } as const;
  const written = (name: string, text: string) => ({ ...item(name, []), caption: text });

  it("adds a tag only where it is missing and removes one only where present", () => {
    const records = [item("a", ["tax"]), item("b", ["bank"])];
    expect(bulkChanges(records, { addTags: ["tax"], removeTags: [], caption: keep })).toEqual([{ name: "b", add_tags: ["tax"] }]);
    expect(bulkChanges(records, { addTags: [], removeTags: ["tax"], caption: keep })).toEqual([{ name: "a", remove_tags: ["tax"] }]);
  });

  it("finds text in any capitalization and treats both sides literally", () => {
    const records = [written("a", "A cost of $5 (paris) in PARIS"), written("b", "Berlin")];
    const change = (find: string, replacement: string) =>
      bulkChanges(records, { addTags: [], removeTags: [], caption: { mode: "replace", find, replacement } });
    expect(change("paris", "$1")).toEqual([{ name: "a", caption: "A cost of $5 ($1) in $1" }]);
    expect(change("", "x")).toEqual([]);
  });

  it("sets one text, skipping blank text and tracks that already have it", () => {
    const records = [written("a", "Old text"), written("b", "New text")];
    const change = (text: string) => bulkChanges(records, { addTags: [], removeTags: [], caption: { mode: "set", text } });
    expect(change("  New text ")).toEqual([{ name: "a", caption: "New text" }]);
    expect(change("   ")).toEqual([]);
  });
});

/** Repeat for the browser players: off, the whole list, or one track. Remembered between visits. */

import { Repeat, Repeat1 } from "lucide-react";
import { useState } from "react";

import { remember, remembered } from "./lib";

export const REPEATS = ["off", "all", "one"] as const;
export type RepeatMode = (typeof REPEATS)[number];

const LABELS: Record<RepeatMode, string> = {
  off: "Repeat is off",
  all: "Repeating all",
  one: "Repeating one track",
};

export function useRepeat(key: string) {
  const [mode, setMode] = useState<RepeatMode>(() => remembered(key, REPEATS, "off"));
  const cycle = () =>
    setMode((current) => {
      const next = REPEATS[(REPEATS.indexOf(current) + 1) % REPEATS.length];
      remember(key, next);
      return next;
    });
  return { mode, cycle };
}

/** One button that cycles off, all, and one. */
export function RepeatButton({ mode, onCycle }: { mode: RepeatMode; onCycle: () => void }) {
  const Icon = mode === "one" ? Repeat1 : Repeat;
  return (
    <button
      className={`lv-button${mode === "off" ? "" : " lv-button-active"}`}
      type="button"
      aria-label={`${LABELS[mode]}. Change repeat`}
      aria-pressed={mode !== "off"}
      title={LABELS[mode]}
      onClick={onCycle}
    >
      <Icon size={17} />
      <span className="lv-repeat-label">{mode === "off" ? "Repeat" : mode === "all" ? "Repeat all" : "Repeat one"}</span>
    </button>
  );
}

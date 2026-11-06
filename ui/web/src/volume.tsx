/** Volume: one remembered level for the browser players, and the host speakers' for the owner. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Volume1, Volume2, VolumeX } from "lucide-react";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import { post, request } from "./http";

const KEY = "lv-volume";
const listeners = new Set<() => void>();

function stored(): number {
  try {
    const value = Number(localStorage.getItem(KEY));
    return localStorage.getItem(KEY) !== null && value >= 0 && value <= 1 ? value : 1;
  } catch {
    return 1;
  }
}

let level = stored();

/** Set the browser players' volume (0 to 1); every player follows, and it is remembered. */
export function setVolume(value: number) {
  const next = Math.min(1, Math.max(0, value));
  if (Math.abs(next - level) < 0.005) return;
  level = next;
  try {
    localStorage.setItem(KEY, String(next));
  } catch {
    // Storage may be refused; the level just lasts until reload.
  }
  listeners.forEach((listener) => listener());
}

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

export const useVolume = () => useSyncExternalStore(subscribe, () => level);

/**
 * Props for an <audio> element so it plays at the shared volume, and so its own volume
 * control (where the browser shows one) moves the shared level too.
 */
export function useSharedVolume() {
  const volume = useVolume();
  const element = useRef<HTMLAudioElement | null>(null);
  useEffect(() => {
    if (element.current) element.current.volume = volume;
  }, [volume]);
  return {
    ref: (audio: HTMLAudioElement | null) => {
      if (audio) {
        audio.volume = level;
        element.current = audio;
      }
    },
    onVolumeChange: (event: React.SyntheticEvent<HTMLAudioElement>) => setVolume(event.currentTarget.volume),
  };
}

const iconFor = (percent: number, muted?: boolean) => (muted || percent === 0 ? VolumeX : percent < 50 ? Volume1 : Volume2);

/** A volume slider with a mute button; `label` says what it controls. */
function Slider({
  label,
  percent,
  muted,
  onChange,
  onMute,
}: {
  label: string;
  percent: number;
  muted?: boolean;
  onChange: (percent: number) => void;
  onMute: () => void;
}) {
  const Icon = iconFor(percent, muted);
  return (
    <span className="lv-volume">
      <button className="lv-icon-button" type="button" aria-label={muted || percent === 0 ? `Unmute ${label}` : `Mute ${label}`} onClick={onMute}>
        <Icon size={17} />
      </button>
      <input
        type="range"
        min={0}
        max={100}
        step={1}
        value={muted ? 0 : percent}
        aria-label={`${label} volume`}
        aria-valuetext={muted ? "Muted" : `${percent}%`}
        onChange={(event) => onChange(Number(event.target.value))}
      />
      <span className="lv-volume-value" aria-hidden="true">
        {muted ? "Muted" : `${percent}%`}
      </span>
    </span>
  );
}

/** The browser players' volume, shared by the page player and the track view. */
export function BrowserVolume() {
  const volume = useVolume();
  const before = useRef(1);
  const percent = Math.round(volume * 100);
  return (
    <Slider
      label="Player"
      percent={percent}
      onChange={(value) => setVolume(value / 100)}
      onMute={() => {
        if (volume > 0) {
          before.current = volume;
          setVolume(0);
        } else setVolume(before.current || 1);
      }}
    />
  );
}

type SpeakerVolumeState = { volume: number; muted: boolean };

/** The host speakers' volume, for the owner; it changes everything playing on that speaker. */
export function SpeakerVolume() {
  const client = useQueryClient();
  const current = useQuery({
    queryKey: ["speaker-volume"],
    queryFn: () => request<SpeakerVolumeState>("/api/volume"),
    retry: false,
    refetchInterval: 15_000,
  });
  const change = useMutation({
    mutationFn: (body: { percent?: number; muted?: boolean }) => post<SpeakerVolumeState>("/api/volume", body),
    onSuccess: (saved) => client.setQueryData(["speaker-volume"], saved),
  });
  // The slider moves at once; the speaker is told once it stops moving.
  const [draft, setDraft] = useState<number | null>(null);
  useEffect(() => {
    if (draft === null) return;
    const handle = setTimeout(() => {
      change.mutate({ percent: draft, muted: false }, { onSettled: () => setDraft(null) });
    }, 250);
    return () => clearTimeout(handle);
    // change.mutate keeps its identity; draft is the only trigger.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft]);
  if (!current.data) return null;
  const { volume, muted } = current.data;
  return (
    <Slider
      label="Speaker"
      percent={draft ?? volume}
      muted={draft === null && muted}
      onChange={setDraft}
      onMute={() => change.mutate({ muted: !muted })}
    />
  );
}

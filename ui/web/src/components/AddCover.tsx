import { ImagePlus } from "lucide-react";
import { useRef, useState } from "react";

import type { Settings, TrackActions, TrackRecord } from "../api";
import { messageOf, readableName } from "../lib";
import { useToast } from "./Toasts";

/** Fit a chosen picture to the cover's 3:2 shape, as a JPEG data URL. */
export async function fittedCover(file: File, [width, height]: [number, number], quality = 0.9): Promise<string> {
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    throw new Error("Choose a valid JPG, PNG, or WebP picture.");
  }
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d")!;
  const scale = Math.max(width / bitmap.width, height / bitmap.height);
  const [drawnWidth, drawnHeight] = [bitmap.width * scale, bitmap.height * scale];
  context.drawImage(bitmap, (width - drawnWidth) / 2, (height - drawnHeight) / 2, drawnWidth, drawnHeight);
  bitmap.close();
  return canvas.toDataURL("image/jpeg", quality);
}

/** Whether a track still shows the placeholder, or nothing, instead of its own cover art. */
export const needsCover = (track: TrackRecord) => track.cover === "placeholder" || track.cover === "none";

type Props = { track: TrackRecord; actions: TrackActions; settings: Settings; className: string; label?: string };

/** Pick a picture for a track's cover; it is stored in Luna Visia, then shown on the track. */
export function AddCover({ track, actions, settings, className, label }: Props) {
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const name = readableName(track.name);

  const store = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    toast(`Storing the cover of ${name} in Luna Visia…`);
    try {
      const dataUrl = await fittedCover(file, settings.cover_upload_size);
      await actions.storeCover.mutateAsync({ name: track.name, dataUrl });
      toast(`${name} has its new cover, saved in Luna Visia`);
    } catch (failure) {
      toast(messageOf(failure, `The cover of ${name} could not be stored in Luna Visia.`));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button className={className} type="button" disabled={busy} aria-busy={busy}
        aria-label={`Add cover art for ${name}`} title="Add cover art; it is stored in Luna Visia"
        onClick={(event) => { event.stopPropagation(); input.current?.click(); }}>
        {busy ? <span className="lv-busy-dot" /> : <ImagePlus size={16} />}
        {label && <span>{busy ? "Storing…" : label}</span>}
      </button>
      <input ref={input} type="file" hidden accept={settings.cover_upload_types.map((type) => `.${type}`).join(",")}
        onChange={(event) => { store(event.target.files?.[0]); event.target.value = ""; }} />
    </>
  );
}

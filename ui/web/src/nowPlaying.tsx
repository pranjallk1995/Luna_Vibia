/** What the page plays outside any dialog or tab: a playlist, or a song carried on from its view. */

import { createContext, useContext } from "react";

/** `label` names where the tracks came from; `startAt` resumes the first track at that second. */
export type Queue = { playlist: string; names: string[]; index: number; startAt?: number };

export type NowPlaying = { play: (queue: Queue) => void; stop: () => void };

export const NowPlayingContext = createContext<NowPlaying>({ play: () => undefined, stop: () => undefined });

export const useNowPlaying = () => useContext(NowPlayingContext);

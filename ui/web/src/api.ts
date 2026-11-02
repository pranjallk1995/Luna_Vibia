/** The gateway's routes, and React Query hooks that keep galleries in step with them. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { post, remove, request } from "./http";

export type Section = "view" | "favorites" | "hidden";

export type TrackRecord = {
  name: string;
  caption?: string | null;
  tags?: string[] | null;
  favorite?: boolean;
  analysis_model?: string | null;
  title?: string | null;
  artist?: string | null;
  duration_seconds?: number | null;
  tempo_bpm?: number | null;
  musical_key?: string | null;
  energy?: number | null;
  cover_url?: string | null;
  size_bytes: number;
  version: number;
};

export type Settings = {
  tracks_per_page: number;
  playback_refresh_seconds: number;
  max_tags: number;
  name_max_chars: number;
  caption_max_chars: number;
  upload_types: string[];
};

export type MetadataChange = {
  caption?: string;
  add_tags?: string[];
  remove_tags?: string[];
};

export type Speaker = { name: string; description: string };

export type Playback = {
  status?: string;
  now_playing?: string | null;
  output?: Speaker | null;
  requested_speaker?: Speaker | null;
  error?: string | null;
  output_error?: string | null;
};

const segment = encodeURIComponent;

export function coverUrl(track: TrackRecord, size: "card" | "large") {
  const cover = track.cover_url ? `&cover=${segment(track.cover_url)}` : "";
  // Browsers keep covers for a year, so a new shape needs a new URL: change `shape` with COVER_SIZES.
  return `/app/covers/${segment(track.name)}?size=${size}&shape=3x2${cover}`;
}

export const fileUrl = (track: TrackRecord) => `/app/files/${segment(track.name)}?v=${track.version}`;

export const downloadUrl = (track: TrackRecord, fileName: string) =>
  `${fileUrl(track)}&download=${segment(fileName)}`;

export const uploadTrack = (name: string, contentBase64: string) =>
  post<TrackRecord>("/api/tracks", { name, content_base64: contentBase64 });

export function usePlayback(refreshSeconds: number) {
  return useQuery({
    queryKey: ["playback"],
    queryFn: () => request<Playback>("/api/playback"),
    refetchInterval: refreshSeconds * 1000,
    staleTime: 0,
    retry: false,
  });
}

type Collection = "visible" | "hidden";

const collectionOf = (section: Section): Collection => (section === "hidden" ? "hidden" : "visible");

export function useTracks(section: Section) {
  const collection = collectionOf(section);
  return useQuery({
    queryKey: ["tracks", collection],
    queryFn: async () => {
      const { tracks } = await request<{ tracks: TrackRecord[] }>(collection === "hidden" ? "/app/hidden" : "/app/tracks");
      return tracks;
    },
  });
}

/** Every change to one collection: applied on screen first, undone if the server refuses it. */
export function useTrackActions(section: Section) {
  const collection = collectionOf(section);
  const client = useQueryClient();
  const key = ["tracks", collection];
  const metadataPrefix = collection === "hidden" ? "/api/hidden/tracks" : "/api/tracks";

  const refresh = () => client.invalidateQueries({ queryKey: ["tracks"] });

  const change = <V,>(
    run: (variables: V) => Promise<unknown>,
    apply: (tracks: TrackRecord[], variables: V) => TrackRecord[],
  ) => ({
    mutationFn: run,
    onMutate: async (variables: V) => {
      await client.cancelQueries({ queryKey: key });
      const previous = client.getQueryData<TrackRecord[]>(key);
      if (previous) client.setQueryData(key, apply(previous, variables));
      return { previous };
    },
    onError: (_error: unknown, _variables: V, context?: { previous?: TrackRecord[] }) => {
      if (context?.previous) client.setQueryData(key, context.previous);
    },
    onSettled: refresh,
  });

  const without = (tracks: TrackRecord[], name: string) => tracks.filter((track) => track.name !== name);

  const setFavorite = useMutation(
    change(
      ({ name, favorite }: { name: string; favorite: boolean }) => post("/api/favorites", { names: [name], favorite }),
      (tracks, { name, favorite }) => tracks.map((track) => (track.name === name ? { ...track, favorite } : track)),
    ),
  );

  const removeTrack = useMutation(
    change(
      (name: string) =>
        collection === "hidden" ? post("/api/hidden/delete", { names: [name] }) : remove(`/api/tracks/${segment(name)}`),
      without,
    ),
  );

  const hide = useMutation(change((name: string) => post("/api/hidden/hide", { names: [name] }), without));

  const restore = useMutation(change((name: string) => post("/api/hidden/restore", { names: [name] }), without));

  const rename = useMutation({
    mutationFn: ({ name, newName }: { name: string; newName: string }) =>
      post(`/api/tracks/${segment(name)}/rename`, { new_name: newName }),
    onSuccess: refresh,
  });

  const merge = (name: string, saved: Partial<TrackRecord>) =>
    client.setQueryData<TrackRecord[]>(key, (tracks) =>
      tracks?.map((track) => (track.name === name ? { ...track, ...saved } : track)),
    );

  const updateMetadata = useMutation({
    mutationFn: ({ name, change: edit }: { name: string; change: MetadataChange }) =>
      post<TrackRecord>(`${metadataPrefix}/${segment(name)}/metadata`, edit),
    // Only the edited fields: size and version come from the file.
    onSuccess: (saved, { name }) => merge(name, { caption: saved.caption, tags: saved.tags }),
  });

  const setCover = useMutation({
    mutationFn: ({ name, coverUrl: cover }: { name: string; coverUrl: string | null }) =>
      post<TrackRecord>(`/api/tracks/${segment(name)}/cover`, { cover_url: cover }),
    onSuccess: (saved, { name }) => merge(name, { cover_url: saved.cover_url }),
  });

  return { setFavorite, remove: removeTrack, hide, restore, rename, updateMetadata, setCover };
}

export type TrackActions = ReturnType<typeof useTrackActions>;

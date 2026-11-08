import { Eye, Heart, LayoutGrid, List, ListMusic, Lock, LogOut, Upload, Volume2, type LucideIcon } from "lucide-react";
import { useMemo, useState } from "react";

import { usePlayback, useTracks, type Section, type Settings } from "./api";
import { Gallery } from "./components/Gallery";
import { HiddenGate } from "./components/HiddenGate";
import { Player, Playlists } from "./components/Playlists";
import { Brand, ForbiddenPage, SignInPage, UnreachablePage } from "./components/Gate";
import { UploadDialog } from "./components/UploadDialog";
import { useSession } from "./http";
import { remember, remembered } from "./lib";
import { describePlayback } from "./playback";
import { NowPlayingContext, type Queue } from "./nowPlaying";
import { useRepeat } from "./repeat";
import { SpeakerVolume } from "./volume";
import { useUploads } from "./uploads";

// The library's sections, plus the Playlists tab.
type Tab = Section | "playlists";
const TABS = ["view", "favorites", "playlists", "hidden"] as const;

const SECTIONS: { id: Tab; label: string; icon: LucideIcon }[] = [
  { id: "view", label: "View Tracks", icon: Eye },
  { id: "favorites", label: "Favorite Tracks", icon: Heart },
  { id: "playlists", label: "Playlists", icon: ListMusic },
  { id: "hidden", label: "Hidden Tracks", icon: Lock },
];

const LAYOUTS = ["grid", "list"] as const;
type Layout = (typeof LAYOUTS)[number];

/** What Vibia plays on the host's speakers, and where; Windows can switch them on its own. */
function PlaybackBar({ refreshSeconds }: { refreshSeconds: number }) {
  const { data } = usePlayback(refreshSeconds);
  const parts = data && describePlayback(data);
  if (!parts) return null;
  return (
    <p className="lv-playback">
      <Volume2 size={16} aria-hidden="true" />
      <span>
        {parts.map(({ text, strong }, index) => (strong ? <strong key={index}>{text}</strong> : text))}
      </span>
      {data?.output && <SpeakerVolume />}
    </p>
  );
}

function Workspace({ logoutUrl, settings }: { logoutUrl: string; settings: Settings }) {
  const [section, setSection] = useState<Tab>(() => remembered("lv-section", TABS, "view"));
  const [layout, setLayout] = useState<Layout>(() => remembered("lv-layout", LAYOUTS, "grid"));
  const [uploading, setUploading] = useState(false);
  // The playlist player belongs to the page, not the Playlists tab, so it keeps playing in every tab.
  const [queue, setQueue] = useState<Queue | null>(null);
  const repeat = useRepeat("lv-repeat-playlist");
  const library = useTracks("view");
  const tracksByName = useMemo(
    () => new Map((library.data ?? []).map((track) => [track.name, track] as const)),
    [library.data],
  );
  const nowPlaying = useMemo(() => ({ play: setQueue, stop: () => setQueue(null) }), []);
  const uploads = useUploads();

  const chooseSection = (id: Tab) => {
    setSection(id);
    remember("lv-section", id);
  };

  const chooseLayout = (id: Layout) => {
    setLayout(id);
    remember("lv-layout", id);
  };

  return (
    <NowPlayingContext.Provider value={nowPlaying}>
    <main className="lv-page">
      <div className="lv-header-row">
        <Brand />
        <div className="lv-header-actions">
          <button
            className={`lv-button${layout === "grid" ? " lv-button-active" : ""}`}
            type="button"
            aria-label="Grid view"
            aria-pressed={layout === "grid"}
            onClick={() => chooseLayout("grid")}
          >
            <LayoutGrid size={18} />
          </button>
          <button
            className={`lv-button${layout === "list" ? " lv-button-active" : ""}`}
            type="button"
            aria-label="List view"
            aria-pressed={layout === "list"}
            onClick={() => chooseLayout("list")}
          >
            <List size={18} />
          </button>
          <button className="lv-button lv-button-primary lv-header-main" type="button" onClick={() => setUploading(true)}>
            <Upload size={17} />
            Upload Tracks
            {uploads.progress && <span className="lv-busy-dot" aria-label="Uploading" />}
          </button>
          <a className="lv-button lv-sign-out" href={logoutUrl}>
            <LogOut size={16} />
            Sign out
          </a>
        </div>
      </div>

      <PlaybackBar refreshSeconds={settings.playback_refresh_seconds} />

      {queue && (
        <Player
          queue={queue}
          library={tracksByName}
          repeat={repeat.mode}
          onRepeat={repeat.cycle}
          onMove={(index) => setQueue({ ...queue, index, startAt: undefined })}
          onStop={() => setQueue(null)}
        />
      )}

      <nav className="lv-nav" aria-label="Gallery section">
        {SECTIONS.map(({ id, label, icon: Icon }) => (
          <button
            className={section === id ? "lv-nav-item lv-nav-active" : "lv-nav-item"}
            type="button"
            key={id}
            aria-label={label}
            aria-current={section === id ? "page" : undefined}
            onClick={() => chooseSection(id)}
          >
            <Icon size={17} />
            <span>{label}</span>
          </button>
        ))}
      </nav>

      {section === "playlists" ? (
        <Playlists queue={queue} onQueue={setQueue} repeat={repeat} />
      ) : section === "hidden" ? (
        <HiddenGate noun="tracks">
          <Gallery key={section} section={section} layout={layout} settings={settings} />
        </HiddenGate>
      ) : (
        <Gallery key={section} section={section} layout={layout} settings={settings} />
      )}

      {uploading && <UploadDialog uploads={uploads} settings={settings} onClose={() => setUploading(false)} />}
      <footer className="lv-footer">Luna Vibia · v{settings.version}</footer>
    </main>
    </NowPlayingContext.Provider>
  );
}

export function App() {
  const { data: session, error, refetch } = useSession<Settings>();

  if (error) return <UnreachablePage onRetry={() => refetch()} />;
  if (!session) return null;
  if (session.status === "signed_out") return <SignInPage url={session.login_url} />;
  if (session.status === "forbidden") return <ForbiddenPage email={session.email} logoutUrl={session.logout_url} />;
  return <Workspace logoutUrl={session.logout_url} settings={session.settings} />;
}

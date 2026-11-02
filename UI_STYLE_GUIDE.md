# Luna UI style guide

Shared visual reference for every Luna app with a UI: Visia, Vita, Lumia, Fiora,
Lexia, Vibia, and Unia. This file is identical in all seven repositories. Any
change goes into all seven copies at the same time.

Luna Visia is the reference implementation. When this guide and the code
disagree, check this guide first, fix the code to match it, and record any
intended exception under [Known deviations](#known-deviations).

## How a Luna UI is built

Each UI is a React and TypeScript app built with Vite, served by a small Starlette
gateway on port 8501. The browser talks only to the gateway.

| Part | Where | Holds |
| --- | --- | --- |
| Styles | `ui/web/src/styles.css` | The palette, type scale, shell, and app-specific rules |
| Sign-in pages and brand | `ui/web/src/App.tsx` in Visia, `ui/web/src/components/Gate.tsx` elsewhere | Logo, title, subtitle, sign-in and refusal pages |
| Shared components | `ui/web/src/components/` | `Toasts`, `Dialog`, and, where used, `ConfirmDialog` and `Pager` |
| Settings | `ui/config.py` | Limits and options; the browser app reads them from `/auth/session` and never hard-codes them |

Shared classes use the `lv-` prefix in every app. Rules for one app's own screens
use its prefix: `lu-` Unia, `ll-` Lumia, `lf-` Fiora, `lx-` Lexia, `vt-` Vita. Vita's
charts and calendar keep their descriptive names (`nutrition-card`, `workout-day`).

## Color palette

| Role | Color | Variable |
| --- | --- | --- |
| Background | `#111111` | `--lv-bg` |
| Surface / panel | `rgba(255, 255, 255, 0.055)` | `--lv-surface` |
| Control | `rgba(255, 255, 255, 0.07)` | `--lv-control` |
| Control hover | `rgba(255, 255, 255, 0.12)` | `--lv-control-hover` |
| Primary text | `#f5f5f5` | `--lv-text` |
| Muted text | `#a3a3a3` | `--lv-muted` |
| Border | `rgba(255, 255, 255, 0.14)` | `--lv-border` |
| Strong border | `rgba(255, 255, 255, 0.34)` | `--lv-strong` |
| Accent | `#f5f5f5` | `--lv-accent` |
| Accent surface | `rgba(255, 255, 255, 0.09)` | `--lv-soft` |

The page background adds a soft glow:
`radial-gradient(circle at 82% -10%, rgba(255, 255, 255, 0.07), transparent 30rem)`
over `--lv-bg`, fixed to the window.

The apps are dark only. The header subtitle uses the muted text color. Titles and
important foreground content use the primary text color.

Status colors are reserved for state, and always come with text or an icon: green
`#4ade80` for success or running, amber `#fbbf24` or `#facc15` for a warning, and rose
`#fb7185` for danger.

## Typography

| Role | Size | Variable |
| --- | --- | --- |
| App title | `clamp(1.65rem, 3vw, 2.15rem)` | `--luna-text-title` |
| Header subtitle | `0.78rem` | `--luna-text-subtitle` |
| Body text | `0.88rem` | `--luna-text-body` |
| Supporting text / labels | `0.72rem` | `--luna-text-small` |

The font is Source Code Pro, self-hosted through
`@fontsource-variable/source-code-pro` and imported in `main.tsx`, so the content
security policy needs no outside font host. It falls back to the system monospace
stack:

```css
font-family: "Source Code Pro Variable", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
```

The app title uses weight `720`, letter spacing `-.04em`, and line height `1`. The
subtitle uses weight `400` and the muted color.

## Icons

Icons come from `lucide-react`. Use the component at `size={16}` to `size={18}`, with
an `aria-label` on any button that shows only an icon. Do not load an icon font.

## Logo assets

The page and favicon both use `ui/web/public/logo.png`, a small transparent PNG. The
larger source art stays in `ui/assets/` and is not part of the built app. Never inline
a logo as a `data:` URI.

| App | Served logo | Source art |
| --- | --- | --- |
| Luna Visia | 96 x 96 px | `ui/assets/lunavisia_logo.png` |
| Luna Vita | 96 x 96 px | `ui/assets/lunavita_logo.png` |
| Luna Vibia | 96 x 96 px | `ui/assets/lunavibia_logo.png` |
| Luna Unia | 96 x 96 px | `ui/assets/lunaunia_logo.png` |
| Luna Lumia | 216 x 216 px | `ui/assets/lunalumia_logo.png` |
| Luna Fiora | 216 x 216 px | `ui/assets/lunafiora_logo.png` |
| Luna Lexia | 216 x 216 px | `ui/assets/lunalexia_logo.png` |

The logo shows at `5.75rem x 4.5rem` on desktop and `4rem x 3.4rem` on phones, with
`object-fit: contain`.

## Header

The header is the part of the shell that must look identical across apps. Only the
logo, title, subtitle, and the controls on the right change per app.

### Structure

```tsx
<main className="lv-page">
  <div className="lv-header-row">
    <div className="lv-header">
      <img className="lv-mark" src="/logo.png" alt="Luna <App> logo" />
      <div>
        <h1 className="lv-title">Luna <App></h1>
        <p className="lv-subtitle">Private AI-managed <what the app does></p>
      </div>
    </div>
    <div className="lv-header-actions">{/* controls, ending with Sign out */}</div>
  </div>
  {/* Primary navbar, directly below */}
</main>
```

The subtitle always follows the pattern "Private AI-managed …".

| App | Subtitle ends with |
| --- | --- |
| Luna Visia | image storage |
| Luna Vita | nutrition tracking |
| Luna Lumia | smart lighting |
| Luna Fiora | personal finance |
| Luna Lexia | document storage |
| Luna Vibia | music library |
| Luna Unia | home for every Luna app |

### Right-side controls

| App | Controls, left to right |
| --- | --- |
| Luna Visia | Grid view, List view, **Upload Images** (primary), Sign out |
| Luna Vita | Log date picker, Sign out |
| Luna Lumia | Check lights (icon only), **Turn all on / off** (primary), Sign out |
| Luna Fiora | From date, To date, Sign out |
| Luna Lexia | Grid view, List view, **Upload Docs** (primary), Sign out |
| Luna Vibia | Grid view, List view, **Upload Tracks** (primary), Sign out |
| Luna Unia | **Check again** (primary), Sign out |

Shared rules:

- **Sign out** is always last. It is a link to the `logout_url` from `/auth/session`,
  with the class `lv-button lv-sign-out`, `7rem` wide on desktop.
- The app's main action has `lv-button-primary lv-header-main`, and takes the free
  width.
- Every control is at least `2.625rem` tall, has a `.5rem` radius, and does not wrap
  its text.
- Do not move controls with manual offsets or spacer elements.

### Desktop geometry

Use these values unchanged:

```css
.lv-page { max-width: 1180px; margin: 0 auto; padding: 2.35rem 1rem 3rem; }

.lv-header-row {
  display: grid;
  grid-template-columns: 5fr 4fr;
  gap: 1rem;
  align-items: center;
  margin-bottom: .55rem;
}

.lv-header { display: flex; align-items: center; gap: 1rem; min-height: 4.5rem; margin-bottom: 1rem; }
.lv-mark { display: block; flex: 0 0 5.75rem; width: 5.75rem; height: 4.5rem; object-fit: contain; }
.lv-header-actions { display: flex; gap: .5rem; align-items: center; justify-content: flex-end; }
```

Keep the header row's height intrinsic. A fixed height pushes the navbar down. The
header's vertical position comes from the page's `2.35rem` top padding alone: render
nothing above it, and do not fix a position problem with `top`, `transform`, negative
margins, or spacer elements.

### Phones (max-width: 700px)

```css
.lv-page { padding: 1rem 16px 2rem; }
.lv-header-row { grid-template-columns: minmax(0, 1fr); gap: 0; }
.lv-header { gap: .65rem; min-height: 3.4rem; margin-bottom: .65rem; }
.lv-mark { flex: 0 0 4rem; width: 4rem; height: 3.4rem; }
.lv-title { font-size: clamp(1.55rem, 8vw, 1.85rem); white-space: nowrap; }
.lv-subtitle { display: none; }
.lv-sign-out { flex: 0 0 auto; font-size: 0; gap: 0; }
```

The brand stacks above the controls, the brand and the controls each stay on one line,
and Sign out collapses to its icon. The page never scrolls sideways; wide tables
scroll inside `lv-table-scroll`.

## Primary navbar

The navbar starts at the same on-screen position in every app at the same viewport
size, zoom, and root font size. It is full width with equal-width items.

```tsx
<nav className="lv-nav" aria-label="Section">
  <button className="lv-nav-item lv-nav-active" aria-current="page" aria-label="Overview">
    <Icon size={17} /><span>Overview</span>
  </button>
</nav>
```

```css
.lv-nav {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: 1fr;
  gap: .2rem;
  margin: .2rem 0 1.15rem;
  padding: .4rem;
  border: 1px solid var(--lv-border);
  border-radius: .9rem;
  background: var(--lv-surface);
}
```

Each item is at least `2.55rem` tall with a `.65rem` radius. On phones the labels are
visually hidden but stay readable by screen readers, leaving the icons.

| App | Sections |
| --- | --- |
| Luna Visia | View Images, Favorite Images, Hidden Images |
| Luna Vita | Daily Tracking, Monthly Tracking |
| Luna Lumia | Lights, Rooms, Schemes, Schedules |
| Luna Fiora | Overview, Transactions, EMIs & SIPs, Goals & reminders |
| Luna Lexia | View Documents, Favorite Documents, Hidden Documents |
| Luna Vibia | View Tracks, Favorite Tracks, Hidden Tracks |
| Luna Unia | None: a single page (see [Known deviations](#known-deviations)) |

The chosen section is remembered in browser storage, through `remember` and
`remembered` in `lib.ts`, and the app must work the same when storage is refused.

Sections within a page, such as Lumia's Library / Solid / Sequence / Transitions, use
the lighter `lv-tabs` underline, never a second navbar.

### States

Labels and icons stay muted in every state. State is shown through the surface and
border only.

- **Default:** control background, transparent border, muted icon and label.
- **Selected:** control-hover background, `1px` strong border, and a `0 0 0 1px`
  border-colour ring.
- **Hover:** control-hover background, strong border, `translateY(-1px)`, and a
  `140ms` transition on border, background, and transform.
- **Focus:** the global `2px` accent outline for keyboard users, with no colour change.

## Shared components

- **Buttons:** `lv-button`, plus `lv-button-primary` for the main action and
  `lv-button-active` for a pressed view toggle. `lv-icon-button` is the compact form
  inside cards and dialogs.
- **Dialogs:** `Dialog` wraps the browser's native `<dialog>`, which traps focus and
  closes on Escape. Escape inside an inline edit cancels only that edit.
- **Confirmation:** `ConfirmDialog` stays open with the reason if the action fails.
  Anything that permanently deletes a stored file asks first.
- **Toasts:** `useToast` from `Toasts`. They sit in a `popover="manual"` element, so
  they show above an open dialog.
- **Messages:** `lv-alert` for information, `lv-alert-error` for a failure, placed next
  to what failed. Show the backend's reason, not a generic error.
- **Forms:** `lv-form`, `lv-form-row`, and `lv-field`, with visible labels. A refused
  form keeps what was typed.

## Behavior

- **Instant feedback.** Favorites, light controls, and similar changes show at once and
  roll back with a toast if the server refuses.
- **Finished choices.** Sliders and color pickers send one change when released, not
  one per pixel.
- **No lost typing.** Fresh server data must not overwrite a table cell someone is
  editing.
- **Motion.** Keep transitions under `200ms`, and respect `prefers-reduced-motion`.
- **Images.** Grids use small cached thumbnails from the gateway, not original files,
  with `loading="lazy"` and explicit `width` and `height`.

## Charts

Draw charts as plain SVG with no chart library. Use one y-axis per chart, thin marks,
and recessive grid lines. A chart with two or more series has a legend, and every chart
has a text alternative through `aria-label`, with values on hover. Values and labels use
text colors; only the mark carries the series color.

Fiora's `LineChart` uses `#3987e5` for income and `#d95926` for expenditure. Vita's
macro colors are protein `#4ade80`, carbs `#60a5fa`, fat `#fbbf24`, natural sugar
`#c084fc`, and added sugar `#fb7185`. A color always means the same thing within an app.

## Known deviations

These are differences in the code today. Each should either be fixed to match this
guide or deliberately accepted here.

| App | Deviation | Guide says |
| --- | --- | --- |
| Vita, Lumia, Fiora, Lexia, Vibia, Unia | Use the system monospace stack. | Self-hosted Source Code Pro. |
| Vita, Lumia, Fiora, Lexia, Vibia | Navbar gap is `.35rem` with a `1rem` bottom margin; selected and hovered labels turn to primary text, without the hover lift. | `.2rem`, `.2rem 0 1.15rem`, muted labels, and `translateY(-1px)`. |
| Visia | Navbar uses `grid-template-columns: repeat(3, 1fr)`. | `grid-auto-flow: column`, which fits any number of sections. Harmless with three. |
| Visia | In windows 1760px and wider, the page grows to `1720px` and the gallery to four columns, so the header and navbar no longer line up with the other apps at those widths. | `max-width: 1180px`. Accepted for Visia, because an image gallery wastes most of a wide window at 1180px. |
| Visia | The image dialog fills the window, with details in a side panel. Lexia and Vibia keep the earlier gallery cards and dialogs. | Accepted for Visia as the newest gallery design; the others have not adopted it. |
| Vita | Adds short aliases (`--panel`, `--text`, `--muted`, and others) for its chart and calendar rules. | `--lv-*` names. |
| Lumia | Deleting a light, room, scheme, or schedule has no confirmation. | Nothing here deletes a stored file, so this is accepted for now. Revisit if mistaken deletes happen. |
| Unia | No navbar. Its one page is a grid of app cards, and the status summary above the grid (`.lu-summary`) takes the navbar's surface and `.2rem 0 1.15rem` margin. | Full-width navbar below the header. Accepted: Unia has nothing to navigate between. |
| Unia | Checks each app at `/_stcore/health`, which every gateway keeps as an alias of `/health`. | Move to `/health` and remove the alias once every app has merged its React UI. |

## Checklists

### After any header or shell change

1. The logo and title start at the established desktop height.
2. Logo, title, subtitle, and controls stay vertically centred.
3. Nothing renders above the header.
4. On phones, the brand stays on one line, the subtitle is hidden, the control row stays
   on one line, Sign out shows only its icon, and the page does not scroll sideways.
5. A hard refresh gives the same position as moving between sections.
6. `npm run build` passes, and the browser console shows no errors.
7. Check the running container, not just the source. Compose Watch restarts the gateway
   on Python changes and rebuilds the image on changes under `ui/web/src`; without it,
   rebuild that app's UI container before reviewing.

### Before approving a shell change across apps

1. Open every app at the same viewport width and 100% zoom.
2. Measure the navbar's bounding-box `top`, `left`, and `width`; they agree to within
   one device pixel, apart from the accepted Visia and Unia deviations.
3. Check default, selected, hover, keyboard-focus, hard-refresh, and phone states. Do not
   approve from a source review alone.
4. Update this guide first, then apply the change to every app together.

### Adding a new Luna app

1. Copy `styles.css`, `main.tsx`, `http.ts`, and the shared components from the most
   recently migrated app, then the gateway, `sso.py`, and the `SSOConfig` block, which
   stay identical across apps.
2. Use the `.lv-header` markup, logo box, title, and "Private AI-managed …" subtitle.
3. Put the app's main action on the right as a primary button, followed by Sign out.
4. Use a full-width `lv-nav`; change only labels and icons.
5. Forward only the backend routes the UI uses, and put every setting in `config.py`.
6. Give the app's own rules a short class prefix, add the app to the tables in this
   guide, and copy the guide into every repo.

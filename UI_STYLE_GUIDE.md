# Luna UI style guide

Shared visual reference for Luna Vibia, Luna Vita, and Luna Lumia. This file is
identical in all three repositories. Any change goes into all three copies at
the same time.

Luna Vibia is the reference implementation. When this guide and the code
disagree, check this guide first, fix the code to match it, and record any
intended exception under [Known deviations](#known-deviations).

## Color palette

| Role | Color | Vibia / Lumia variable | Vita variable |
| --- | --- | --- | --- |
| Background | `#111111` | `--lv-bg` | `--bg` |
| Surface / panel | `rgba(255, 255, 255, 0.055)` | `--lv-surface` | `--panel` |
| Control | `rgba(255, 255, 255, 0.07)` | `--lv-control` | `--control` |
| Control hover | `rgba(255, 255, 255, 0.12)` | `--lv-control-hover` (Lumia: `--lv-hover`) | `--control-hover` |
| Primary text | `#f5f5f5` | `--lv-text` | `--text` |
| Muted text | `#a3a3a3` | `--lv-muted` | `--muted` |
| Border | `rgba(255, 255, 255, 0.14)` | `--lv-border` | `--border` |
| Strong border | `rgba(255, 255, 255, 0.34)` | `--lv-strong` | `--strong` |
| Accent | `#f5f5f5` | `--lv-accent` | `--accent` |
| Accent surface | `rgba(255, 255, 255, 0.09)` | `--lv-soft` | `--soft` |

The header subtitle uses the muted text color. Titles and important foreground
content use the primary text color. New apps use the `--lv-*` names.

Luna Vibia also has a light theme. It changes only these variables; layout and
geometry stay the same in both themes.

## Typography scale

| Role | Size | Variable |
| --- | --- | --- |
| App title | `clamp(1.65rem, 3vw, 2.15rem)` | `--luna-text-title` |
| Header subtitle | `0.78rem` | `--luna-text-subtitle` |
| Body text | `0.88rem` | `--luna-text-body` |
| Supporting text / labels | `0.72rem` | `--luna-text-small` |

The app title uses weight `720`, letter spacing `-.04em` and line height `1`.
The subtitle uses weight `400` and the muted color. Luna typography variables
use the `--luna-text-*` prefix to avoid clashing with Streamlit's theme
variables.

## Logo assets

| App | Asset | Format | Resolution | File size | Desktop display | Mobile display |
| --- | --- | --- | --- | --- | --- | --- |
| Luna Vibia | `ui/assets/lunavibia_logo.png` | PNG, 8-bit RGBA | 1254 x 1254 px | 619,255 bytes | 5.75rem x 4.5rem | 4rem x 3.4rem |
| Luna Vita | `ui/assets/lunavita_logo.png` | PNG, 8-bit RGBA | 1254 x 1254 px | 637,054 bytes | 5.75rem x 4.5rem | 4.25rem x 3.5rem |
| Luna Lumia | `ui/assets/lunalumia_logo.png` | PNG, 8-bit RGBA | 1254 x 1254 px | 577,562 bytes | 5.75rem x 4.5rem | 4.25rem x 3.5rem |

Logos are embedded as base64 `data:` URIs in an `<img class="lv-mark">` and
render with `object-fit: contain`, so the square source keeps its aspect ratio
inside the header box. If a logo file is missing, Lumia renders a
`.lv-placeholder` of the same size instead; other apps should do the same rather
than collapse the header.

## Header

The header is the part of the shell that must look identical across apps. Only
the logo, title, subtitle, and the controls in the right column change per app.

### Structure

Every app renders, in this order and with nothing in between:

1. **Style injection** with `st.html(...)`. It creates no visible layout block.
2. **Header row:** `st.columns([5, 4], vertical_alignment="center", gap="medium")`.
3. **Left column:** exactly one `.lv-header` block:

   ```html
   <div class="lv-header">
       <img class="lv-mark" src="data:image/png;base64,..." alt="Luna <App> logo">
       <div>
           <h1 class="lv-title">Luna <App></h1>
           <p class="lv-subtitle">Private AI-managed <what the app does></p>
       </div>
   </div>
   ```

   The subtitle always follows the pattern "Private AI-managed …" (image
   storage, nutrition tracking, smart lighting).

4. **Right column:** the app's header controls (see below).
5. **Primary navbar,** full width, directly below the header row.

### Right-column controls

The right column holds the app's main controls, ending with **Sign out**:

| App | Controls, left to right |
| --- | --- |
| Luna Vibia | Grid view, List view, **Upload Images** (primary), Sign out. Nested columns `[1, 1, 3, 2]`. |
| Luna Vita | Log date picker, Sign out. Nested columns `[3, 2]`. |
| Luna Lumia | Refresh lights (icon only), **Turn all on / off** (primary), Sign out. Horizontal container `header_actions`. |

Shared rules:

- **Sign out** is always the last control. It is `st.button("Sign out",
  icon=":material/logout:", key="header_sign_out", on_click=LunaSingleSignOn.sign_out)`. The key
  must be exactly `header_sign_out`, because the mobile CSS targets it.
- The app's main action is the widest control and uses `type="primary"`.
- Icon-only buttons (view toggles, refresh) use a Material icon and no label.
- Every control is at least `2.625rem` tall, uses the control background, a
  `.65rem` radius, and `white-space: nowrap`. Buttons in the header row stretch
  to their column (`width="stretch"` or `use_container_width=True`).
- Do not move controls with manual offsets or spacer elements.

### Desktop geometry

Use these values unchanged:

```css
.block-container {
    max-width: 1180px;
    padding-top: 2.35rem;
    padding-bottom: 3rem;
}

div[data-testid="stHorizontalBlock"]:has(.lv-header) {
    align-items: center;
    margin-bottom: .55rem;
}

.lv-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    min-height: 4.5rem;
    margin-bottom: 1rem;
}

.lv-mark {
    display: block;
    flex: 0 0 5.75rem;
    width: 5.75rem;
    height: 4.5rem;
    object-fit: contain;
    object-position: center;
}

.lv-title {
    margin: 0;
    color: var(--lv-text);
    font-size: var(--luna-text-title);
    font-weight: 720;
    letter-spacing: -.04em;
    line-height: 1;
}

.stApp .lv-subtitle {
    margin: .32rem 0 0;
    color: var(--lv-muted);
    font-size: var(--luna-text-subtitle);
    font-weight: 400;
}
```

Keep the header row's height intrinsic. A fixed row height pushes the navbar
down. The logo, title, subtitle and right-column controls stay vertically
centred as one row.

Hide Streamlit's own chrome in every app: a transparent
`header[data-testid="stHeader"]`, and `display: none` on `#MainMenu`, `footer`
and `div[data-testid="stDecoration"]`.

### Mobile geometry (max-width: 700px)

```css
.block-container { padding: .85rem .8rem 2rem; }

/* Header columns stack: brand on top, controls below, both full width. */
div[data-testid="stHorizontalBlock"]:has(.lv-header) { flex-wrap: wrap !important; }
div[data-testid="stHorizontalBlock"]:has(.lv-header) > div[data-testid="stColumn"] {
    flex: 1 1 100% !important;
    width: 100% !important;
}

/* Brand stays on one line; the subtitle is hidden. */
.lv-header { flex-wrap: nowrap !important; gap: .65rem; min-width: 0; }
.lv-header > div { min-width: 0; flex: 1 1 auto; }
.lv-title { white-space: nowrap; }
.lv-subtitle { display: none; }

/* Sign out collapses to an icon-only square. */
.st-key-header_sign_out,
.st-key-header_sign_out .stButton { width: 2.625rem !important; min-width: 2.625rem !important; }
.st-key-header_sign_out button { width: 2.625rem !important; min-width: 2.625rem !important; padding: 0 !important; }
.st-key-header_sign_out button p { display: none !important; }
.st-key-header_sign_out button span[data-testid="stIconMaterial"] { margin: 0 !important; }
```

The control row below the brand stays on a single line
(`flex-wrap: nowrap`): the main control flexes to fill the space, icon-only
buttons keep a fixed width, and Sign out is a fixed `2.625rem` square on the
right. The mobile logo size and title clamp are listed per app under
[Logo assets](#logo-assets) and [Known deviations](#known-deviations).

### Header-position invariant

The header's vertical position is fixed by the `2.35rem` top padding alone.

Streamlit wraps components in layout blocks even when their height is zero. A
hidden `component_html` script once rendered before the Vibia header and
pushed the logo, title and controls down on every rerun. Removing it made the
header position predictable again. To keep it that way:

- Before the header renders, inject CSS only with `st.html(...)`.
- Never place `st.container`, `st.markdown`, `st.empty`, `component_html` or any
  other layout-producing element before the header.
- Do not add invisible anchors (date, power, navigation markers) inside the
  header columns. Streamlit still adds vertical gaps around their wrappers.
- If JavaScript is needed, mount it after the visible page content.
- Do not fix a position regression by nudging margins or padding, or with
  `top`, `transform`, negative margins or spacer elements. First look for an
  unexpected element rendered before the header.

## Primary navbar

The navbar starts at the same on-screen position in every app at the same
viewport size, zoom and root font size. It is full width with equal-width items.

Canonical surface:

```css
gap: .2rem;
margin: .2rem 0 1.15rem;
padding: .4rem;
border: 1px solid var(--lv-border);
border-radius: .9rem;
background: var(--lv-surface);
```

Each item is at least `2.55rem` tall, has a `.65rem` radius and no default
Streamlit shadow, and shows a Material icon followed by its label. On mobile,
labels are hidden and icons are shown at `1.25rem`.

| App | Widget | Container key |
| --- | --- | --- |
| Luna Vibia | `st.segmented_control` | `gallery_navigation` |
| Luna Vita | `st.segmented_control` | `nutrition_navigation` |
| Luna Lumia | `st.tabs` | (none) |

Prefer the segmented control. Tabs use different internal wrappers, so Lumia's
tab list uses a `1.2rem` top margin instead of `.2rem` to land on the same
on-screen baseline. Do not move a navbar with `top`, `transform`, negative
margins or invisible anchors.

### States

Labels and icons stay muted in every state. State is shown through the surface
and border only.

- **Default:** control background, transparent border, muted icon and label.
- **Selected:** control-hover background, `1px` strong border, a `0 0 0 1px`
  border-colour ring, muted icon and label.
- **Hover:** control-hover background, strong border, `translateY(-1px)`, and a
  `140ms` transition on border, background and transform. Icon and label stay
  muted.
- **Focus:** a visible outline for keyboard users, with no colour change.

Apply the muted colour to the item and to every nested `p`, `span`, Material
icon and `svg`, with `-webkit-text-fill-color` as well. Streamlit sets its own
colour on nested nodes, so styling only the outer element is not enough.

## Known deviations

These are differences in the code today. Each should either be fixed to match
this guide or deliberately accepted here.

| App | Deviation | Guide says |
| --- | --- | --- |
| Vibia, Vita | Selected and hovered navbar labels turn to primary text (`--lv-text` / `--text`). | Labels stay muted in every state. |
| Lumia | Header row has a fixed `height: 5.5rem` (and `min-height`). | Header row height is intrinsic. |
| Lumia | Sign out is a fixed `7rem` wide on desktop instead of stretching to a column. | Header buttons stretch to their column. |
| Lumia | Navbar item gap is `.35rem`. | `.2rem`. |
| Vita, Lumia | Mobile logo `4.25rem x 3.5rem`, title `clamp(1.55rem, 8vw, 2rem)`. | Vibia uses `4rem x 3.4rem`, `clamp(1.55rem, 8vw, 1.85rem)`. Pick one for all three. |
| Vita | Colour variables use short names (`--text`, `--panel` …). | `--lv-*` names. |
| Lumia | Control-hover variable is `--lv-hover`. | `--lv-control-hover`. |

## Checklists

### After any header or shell change

1. The logo and title start at the established desktop height.
2. Logo, title, subtitle and right-column controls stay vertically centred.
3. Nothing (empty element, iframe) renders above the header.
4. On mobile, the brand stays on one line, the subtitle is hidden, the control
   row stays on one line, and Sign out is an icon-only square.
5. A hard refresh gives the same position as a normal Streamlit rerun.
6. Check both the source and the running container. Compose Watch must be
   running for changes to reach the container; otherwise rebuild that app's UI
   container before reviewing.

### Before approving a shell change across apps

1. Open all three apps at the same viewport width and 100% zoom.
2. Measure the navbar's bounding-box `top`, `left` and `width`; they agree to
   within one device pixel.
3. Check default, selected, hover, keyboard-focus, rerun, hard-refresh and
   mobile states. Do not approve from a source review alone.
4. Update this guide first, then apply the change to all three apps together.

### Adding a new Luna app

1. Copy the shell variables and structural CSS from Vibia before building
   product pages.
2. Use the `[5, 4]` header columns, `.lv-header` markup, logo box, title and
   "Private AI-managed …" subtitle.
3. Put the app's main action in the right column as a primary button, followed
   by Sign out with key `header_sign_out`.
4. Use a full-width segmented control for the navbar; change only labels,
   icons and keys.
5. Keep shell CSS in one style module, injected with `st.html(...)` before the
   header.
6. Add the app to the tables in this guide and copy the guide into every repo.

"""Shared visual styling for the Luna Vibia Streamlit application."""

import streamlit as st


class LunaStyle:
    """Apply the Luna Vibia presentation layer through a scoped API."""

    @staticmethod
    def apply(theme: str = "dark") -> None:
        """Apply the selected Luna Vibia palette without altering widget behavior."""
        palette = (
            "--lv-bg:#f5f7fb;--lv-surface:#ffffff;--lv-control:#eef2f8;"
            "--lv-control-hover:#e2e8f0;--lv-text:#111827;--lv-muted:#64748b;"
            "--lv-border:rgba(71,85,105,.20);--lv-strong:rgba(99,102,241,.48);"
            "--lv-accent:#6366f1;--lv-soft:rgba(99,102,241,.12);"
            "--luna-text-title:clamp(1.65rem,3vw,2.15rem);--luna-text-subtitle:.78rem;--luna-text-body:.88rem;--luna-text-small:.72rem;"
            if theme == "light"
            else "--lv-bg:#111111;--lv-surface:rgba(255,255,255,.055);--lv-control:rgba(255,255,255,.07);"
            "--lv-control-hover:rgba(255,255,255,.12);--lv-text:#f5f5f5;--lv-muted:#a3a3a3;"
            "--lv-border:rgba(255,255,255,.14);--lv-strong:rgba(255,255,255,.34);"
            "--lv-accent:#f5f5f5;--lv-soft:rgba(255,255,255,.09);"
            "--luna-text-title:clamp(1.65rem,3vw,2.15rem);--luna-text-subtitle:.78rem;--luna-text-body:.88rem;--luna-text-small:.72rem;"
        )
        st.html(
            f"<style>:root {{{palette}}}</style>",
        )
        st.html(
            """
            <style>
            .stApp { color:var(--lv-text); background:radial-gradient(circle at 82% -10%,rgba(255,255,255,.07),transparent 30rem),var(--lv-bg); }
            .block-container { max-width:1180px; padding-top:2.35rem; padding-bottom:3rem; }
            .stApp p,.stApp label,.stApp [data-testid="stMarkdownContainer"] { color:var(--lv-text); }
            div[data-testid="stHorizontalBlock"]:has(.lv-header) { align-items:center; margin-bottom:.55rem; }
            .st-key-header_sign_out,.st-key-header_sign_out .stButton { display:flex; justify-content:flex-end; width:7rem!important; min-width:7rem!important; margin-left:auto; }
            .st-key-header_sign_out button { width:7rem!important; min-width:7rem!important; min-height:2.625rem!important; }
            div[data-testid="stHorizontalBlock"]:has(.lv-header) .stButton > button {
                min-height:2.625rem!important; height:2.625rem;
                padding:.45rem .9rem!important;
                border:1px solid var(--lv-border)!important;
                border-radius:.5rem!important;
                background:var(--lv-control)!important;
                color:var(--lv-text)!important;
                box-shadow:0 1px 0 rgba(255,255,255,.03) inset;
                white-space:nowrap;
            }
            div[data-testid="stHorizontalBlock"]:has(.lv-header) .stButton > button p,
            div[data-testid="stHorizontalBlock"]:has(.lv-header) .stButton > button span,
            div[data-testid="stHorizontalBlock"]:has(.lv-header) .stButton > button svg {
                color:var(--lv-text)!important;
                fill:currentColor!important;
                -webkit-text-fill-color:var(--lv-text)!important;
            }
            div[data-testid="stHorizontalBlock"]:has(.lv-header) .stButton > button:hover {
                border-color:var(--lv-strong)!important;
                background:var(--lv-control-hover)!important;
                color:var(--lv-text)!important;
            }
            div[data-testid="stHorizontalBlock"]:has(.lv-header) .stButton > button[data-testid="stBaseButton-primary"] {
                border-color:var(--lv-strong)!important;
                background:var(--lv-soft)!important;
                color:var(--lv-text)!important;
            }
            .st-key-use_grid_view button,
            .st-key-use_list_view button {
                border:1px solid var(--lv-border)!important;
                background:var(--lv-control)!important;
                color:var(--lv-text)!important;
            }
            .st-key-use_grid_view button p,
            .st-key-use_grid_view button span,
            .st-key-use_list_view button p,
            .st-key-use_list_view button span {
                color:var(--lv-text)!important;
                -webkit-text-fill-color:var(--lv-text)!important;
            }
            .st-key-use_grid_view button:is([kind="primary"],[data-testid="stBaseButton-primary"]),
            .st-key-use_list_view button:is([kind="primary"],[data-testid="stBaseButton-primary"]) {
                border-color:var(--lv-strong)!important;
                background:var(--lv-soft)!important;
                color:var(--lv-text)!important;
            }
            .st-key-use_grid_view button:hover,
            .st-key-use_list_view button:hover {
                border-color:var(--lv-strong)!important;
                background:var(--lv-control-hover)!important;
            }
            header[data-testid="stHeader"] { background:transparent; }
            #MainMenu,footer,div[data-testid="stDecoration"] { display:none; }
            .lv-header { display:flex; align-items:center; gap:1rem; min-height:4.5rem; margin-bottom:1rem; }
            .lv-mark { display:block; flex:0 0 5.75rem; width:5.75rem; height:4.5rem; border:0; border-radius:0; object-fit:contain; object-position:center; box-shadow:none; }
            .lv-title { margin:0; color:var(--lv-text); font-family:inherit; font-size:var(--luna-text-title); font-weight:720; letter-spacing:-.04em; line-height:1; }
            .stApp .lv-subtitle { margin:.32rem 0 0; color:var(--lv-muted); font-size:var(--luna-text-subtitle); font-weight:400; }
            div[data-testid="stTabs"] [data-baseweb="tab-list"] { gap:.35rem; padding:.28rem; border:1px solid var(--lv-border); border-radius:.9rem; background:var(--lv-surface); }
            div[data-testid="stTabs"] [data-baseweb="tab"] { height:2.55rem; padding:0 1rem; border-radius:.65rem; color:var(--lv-muted); }
            div[data-testid="stTabs"] [aria-selected="true"] { background:var(--lv-soft); color:var(--lv-text); }
            div[data-testid="stTabs"] [data-baseweb="tab-highlight"] { display:none; }
            div[data-testid="stButtonGroup"] { gap:.2rem; padding:.4rem; border:1px solid var(--lv-border); border-radius:.9rem; background:var(--lv-surface); }
            div[data-testid="stButtonGroup"] button { min-height:2.55rem!important; border:0!important; border-radius:.65rem!important; box-shadow:none!important; }
            div[data-testid="stPopover"] > button[data-testid] {
                width:1.75rem!important; min-width:1.75rem!important;
                height:2rem!important; min-height:2rem!important; padding:0!important;
                border:0!important; border-radius:.35rem!important;
                background:transparent!important; box-shadow:none!important;
            }
            div[data-testid="stPopover"] > button[data-testid]:hover,
            div[data-testid="stPopover"] > button[data-testid]:focus {
                border:0!important; background:transparent!important;
                box-shadow:none!important; transform:none!important; outline:0!important;
            }
            div[data-testid="stPopover"] > button[data-testid] svg:last-child {
                display:none!important;
            }
            div[data-testid="stVerticalBlockBorderWrapper"] > div { border-color:var(--lv-border); border-radius:14px; background:var(--lv-surface); box-shadow:0 10px 30px rgba(0,0,0,.12); }
            div[data-testid="stFileUploader"] section { min-height:10rem; border:1px dashed rgba(255,255,255,.30); border-radius:14px; background:linear-gradient(145deg,rgba(255,255,255,.08),rgba(255,255,255,.025)); }
            div[data-testid="stFileUploader"] section:hover { border-color:rgba(255,255,255,.48); background:rgba(255,255,255,.11); }
            div[data-baseweb="input"],div[data-baseweb="select"] > div { border:1px solid var(--lv-border)!important; border-radius:.75rem!important; background:var(--lv-surface)!important; box-shadow:none!important; }
            div[data-baseweb="input"]:focus-within { border-color:var(--lv-strong)!important; }
            div[data-baseweb="input"] > div { border:0!important; border-radius:0!important; background:transparent!important; box-shadow:none!important; }
            .stApp input,.stApp textarea,
            div[data-baseweb="select"] [role="combobox"],
            div[data-baseweb="select"] [aria-selected] {
                color:var(--lv-text)!important; -webkit-text-fill-color:var(--lv-text)!important;
                caret-color:var(--lv-text)!important;
            }
            .stApp input::placeholder,.stApp textarea::placeholder {
                color:var(--lv-muted)!important; -webkit-text-fill-color:var(--lv-muted)!important;
                opacity:1!important;
            }
            div[data-baseweb="input"] svg {
                color:var(--lv-text)!important; fill:none!important;
                stroke:var(--lv-text)!important; opacity:.8!important;
            }
            div[data-baseweb="input"] svg path,div[data-baseweb="input"] svg circle {
                stroke:var(--lv-text)!important;
            }
            div[data-baseweb="select"] svg { fill:var(--lv-muted)!important; color:var(--lv-muted)!important; }
            div[data-testid="stTrack"] img { border-radius:.8rem; }
            div[data-testid="stElementContainer"]:has(> div[data-testid="stCustomComponentV1"]),
            div[data-testid="stColumn"]:has(.lv-thumbnail-shell) {
                overflow:visible!important;
            }
            div[data-testid="stCustomComponentV1"] {
                position:relative; z-index:1; border-radius:.8rem;
                transition:transform 180ms cubic-bezier(.2,.8,.2,1),filter 180ms ease;
                transform-origin:center;
                will-change:transform,filter;
            }
            div[data-testid="stCustomComponentV1"] iframe {
                border-radius:.8rem!important;
                clip-path:inset(0 round .8rem);
            }
            div[data-testid="stCustomComponentV1"]:hover {
                z-index:20; transform:translateY(-8px) scale(1.045);
                filter:drop-shadow(0 18px 24px rgba(0,0,0,.52)) drop-shadow(0 0 2px rgba(255,255,255,.42));
            }
            div[data-testid="stColumn"]:has(.lv-thumbnail-shell) { position:relative; }
            div[data-testid="stColumn"]:has(.lv-thumbnail-shell) > div[data-testid="stVerticalBlock"] { gap:.3rem!important; }
            div[data-testid="stElementContainer"]:has(.lv-thumbnail-shell),
            div[data-testid="stElementContainer"]:has(.lv-favorite-overlay) { display:none!important; }
            div[data-testid="stHorizontalBlock"]:has(.lv-favorite-overlay):not(:has(.lv-thumbnail-shell)) {
                position:absolute!important; top:.45rem; left:.45rem; right:.45rem;
                z-index:5; width:auto!important; align-items:start!important;
                opacity:0; transition:opacity 120ms ease;
            }
            div[data-testid="stColumn"]:has(.lv-thumbnail-shell):hover div[data-testid="stHorizontalBlock"]:has(.lv-favorite-overlay):not(:has(.lv-thumbnail-shell)),
            div[data-testid="stHorizontalBlock"]:has(.lv-favorite-overlay):not(:has(.lv-thumbnail-shell)):has(button[data-testid="stBaseButton-primary"]) {
                opacity:1;
            }
            div[data-testid="stHorizontalBlock"]:has(.lv-favorite-overlay):not(:has(.lv-thumbnail-shell)) .stButton > button {
                width:2rem!important; min-width:2rem!important; height:2rem!important; min-height:2rem!important;
                padding:0!important; border:0!important; border-radius:0!important;
                background:transparent!important; color:#f8fafc!important;
                box-shadow:none!important; transform:none!important;
            }
            div[data-testid="stHorizontalBlock"]:has(.lv-favorite-overlay):not(:has(.lv-thumbnail-shell)) div[data-testid="stColumn"]:has(.lv-favorite-active) .stButton > button {
                color:#fb4b68!important;
            }
            .lv-card-tags { display:flex; align-items:flex-start; flex-wrap:wrap; gap:.3rem; height:1.7rem; padding:.05rem 0 .15rem; margin:.1rem 0 .3rem; overflow:hidden; }
            .lv-tag { flex:0 0 auto; padding:.12rem .48rem; border:1px solid transparent; border-radius:999px; font-size:.68rem; line-height:1.1rem; }
            .lv-tag-0 { color:#93c5fd; background:rgba(37,99,235,.18); border-color:rgba(96,165,250,.22); }
            .lv-tag-1 { color:#6ee7b7; background:rgba(5,150,105,.18); border-color:rgba(52,211,153,.22); }
            .lv-tag-2 { color:#fcd34d; background:rgba(217,119,6,.18); border-color:rgba(251,191,36,.22); }
            .lv-tag-3 { color:#d8b4fe; background:rgba(147,51,234,.18); border-color:rgba(192,132,252,.22); }
            .lv-tag-4 { color:#fda4af; background:rgba(225,29,72,.18); border-color:rgba(251,113,133,.22); }
            .lv-tag-5 { color:#67e8f9; background:rgba(8,145,178,.18); border-color:rgba(34,211,238,.22); }
            .lv-card-facts { display:flex; align-items:center; gap:.35rem; margin-bottom:1.5rem; color:var(--lv-muted); font-size:.7rem; white-space:nowrap; }
            div[data-testid="stElementContainer"]:has(.lv-preview-details) { display:none!important; }
            div[data-testid="stVerticalBlockBorderWrapper"]:has(.lv-preview-details),
            div[data-testid="stVerticalBlockBorderWrapper"]:has(.lv-preview-details) > div {
                border:0!important; border-radius:0!important;
                background:transparent!important; box-shadow:none!important;
            }
            div[data-testid="stVerticalBlockBorderWrapper"]:has(.lv-preview-details) > div { padding:.65rem!important; }
            .lv-preview-caption {
                display:flex; align-items:center; min-height:1.35rem;
                margin:0; color:var(--lv-text); line-height:1.35rem;
            }
            div[data-testid="stHorizontalBlock"]:has(.lv-preview-static-icon) {
                align-items:center!important;
            }
            div[data-testid="stHorizontalBlock"]:has(.lv-preview-static-icon) > div[data-testid="stColumn"] {
                display:flex!important; align-items:center!important;
            }
            .lv-preview-section-icon { display:inline-flex; align-items:center; margin-right:.55rem; color:var(--lv-muted); font-size:1.15rem; vertical-align:middle; }
            .lv-preview-heading { display:flex; align-items:center; color:var(--lv-muted); font-size:.95rem; }
            .lv-preview-tags { display:flex; flex-wrap:wrap; gap:.4rem; margin:0; padding:0 0 .45rem; }
            div[data-testid="stElementContainer"]:has(.lv-preview-removable-tags) { display:none!important; }
            div[data-testid="stColumn"]:has(.lv-preview-removable-tags) div[data-testid="stButtonGroup"],
            div[data-testid="stColumn"]:has(.lv-preview-removable-tags) [data-baseweb="button-group"] {
                padding:0!important; border:0!important; border-radius:0!important;
                background:transparent!important; box-shadow:none!important;
            }
            div[data-testid="stColumn"]:has(.lv-preview-removable-tags) div[data-testid="stButtonGroup"] button {
                position:relative; min-height:1.55rem!important; padding:.12rem .48rem!important;
                border-radius:999px!important; font-size:.68rem!important; line-height:1.1rem!important;
                overflow:visible; box-shadow:none!important;
                transition:border-color .15s ease, background-color .15s ease;
            }
            div[data-testid="stColumn"]:has(.lv-preview-removable-tags) div[data-testid="stButtonGroup"] button:nth-of-type(6n+1) {
                color:#93c5fd!important; background:rgba(37,99,235,.18)!important; border-color:rgba(96,165,250,.35)!important;
            }
            div[data-testid="stColumn"]:has(.lv-preview-removable-tags) div[data-testid="stButtonGroup"] button:nth-of-type(6n+2) {
                color:#6ee7b7!important; background:rgba(5,150,105,.18)!important; border-color:rgba(52,211,153,.35)!important;
            }
            div[data-testid="stColumn"]:has(.lv-preview-removable-tags) div[data-testid="stButtonGroup"] button:nth-of-type(6n+3) {
                color:#fcd34d!important; background:rgba(217,119,6,.18)!important; border-color:rgba(251,191,36,.35)!important;
            }
            div[data-testid="stColumn"]:has(.lv-preview-removable-tags) div[data-testid="stButtonGroup"] button:nth-of-type(6n+4) {
                color:#d8b4fe!important; background:rgba(147,51,234,.18)!important; border-color:rgba(192,132,252,.35)!important;
            }
            div[data-testid="stColumn"]:has(.lv-preview-removable-tags) div[data-testid="stButtonGroup"] button:nth-of-type(6n+5) {
                color:#fda4af!important; background:rgba(225,29,72,.18)!important; border-color:rgba(251,113,133,.35)!important;
            }
            div[data-testid="stColumn"]:has(.lv-preview-removable-tags) div[data-testid="stButtonGroup"] button:nth-of-type(6n+6) {
                color:#67e8f9!important; background:rgba(8,145,178,.18)!important; border-color:rgba(34,211,238,.35)!important;
            }
            div[data-testid="stColumn"]:has(.lv-preview-removable-tags) div[data-testid="stButtonGroup"] button::after {
                content:"×"; display:inline-block; width:0; margin-left:0; overflow:hidden;
                color:currentColor; opacity:0; transition:width .15s ease, margin-left .15s ease, opacity .15s ease;
            }
            div[data-testid="stColumn"]:has(.lv-preview-removable-tags) div[data-testid="stButtonGroup"] button:hover::after {
                width:.7rem; margin-left:.2rem; opacity:1;
            }
            div[data-testid="stElementContainer"]:has(.lv-preview-icon-action),
            div[data-testid="stElementContainer"]:has(.lv-preview-static-icon) { display:none!important; }
            div[data-testid="stHorizontalBlock"]:is(:has(.lv-preview-icon-action),:has(.lv-preview-static-icon)) .stButton > button,
            div[data-testid="stHorizontalBlock"]:is(:has(.lv-preview-icon-action),:has(.lv-preview-static-icon)) .stButton > button:hover,
            div[data-testid="stHorizontalBlock"]:is(:has(.lv-preview-icon-action),:has(.lv-preview-static-icon)) .stButton > button:focus-visible,
            div[data-testid="stHorizontalBlock"]:is(:has(.lv-preview-icon-action),:has(.lv-preview-static-icon)) .stButton > button:active {
                width:2rem!important; min-width:2rem!important; height:2rem!important; min-height:2rem!important;
                padding:0!important; border:0!important; border-radius:0!important;
                background:transparent!important; box-shadow:none!important; outline:0!important; transform:none!important;
            }
            div[data-testid="stColumn"]:has(.lv-preview-static-icon) .stButton > button:disabled {
                width:1.35rem!important; min-width:1.35rem!important;
                height:1.35rem!important; min-height:1.35rem!important;
                color:var(--lv-muted)!important; opacity:1!important;
            }
            div[data-testid="stVerticalBlockBorderWrapper"]:has(.lv-preview-details) { margin-top:.45rem; }
            div[data-testid="stExpander"] { overflow:hidden; border-color:var(--lv-border); border-radius:.35rem; background:rgba(255,255,255,.045); }
            div[data-testid="stAlert"] { border-radius:.85rem; border-color:var(--lv-border); }
            div[data-testid="stForm"] { padding:1.25rem; border-color:var(--lv-border); border-radius:14px; background:rgba(255,255,255,.055); }
            [data-testid="InputInstructions"] span:first-child { display:none!important; }
            [data-testid="InputInstructions"] span:nth-child(2)::before { display:none!important; }
            div[data-testid="stPopover"] button {
                width:1.75rem!important; min-width:1.75rem!important;
                height:2rem!important; min-height:2rem!important; padding:0!important;
                border:0!important; background:transparent!important;
                box-shadow:none!important; transform:none!important; outline:0!important;
            }
            div[data-testid="stPopover"] button:hover,
            div[data-testid="stPopover"] button:focus,
            div[data-testid="stPopover"] button:focus-visible {
                border:0!important; background:transparent!important;
                box-shadow:none!important; transform:none!important; outline:0!important;
            }
            div[data-testid="stPopover"] button svg { display:none!important; }
            div[data-testid="stPopoverBody"] {
                width:8.75rem!important; min-width:8.75rem!important; max-width:8.75rem!important;
                margin-top:-.4rem!important; margin-right:0!important; margin-bottom:0!important;
                padding:.4rem!important; border-radius:.65rem!important;
            }
            div[data-testid="stPopoverBody"] div[data-testid="stHorizontalBlock"] {
                gap:.35rem!important; align-items:center!important;
            }

            div[data-testid="stPopoverBody"] .stButton > button,
            div[data-testid="stPopoverBody"] .stDownloadButton > button,
            div[data-testid="stPopoverBody"] .stButton > button:hover,
            div[data-testid="stPopoverBody"] .stDownloadButton > button:hover,
            div[data-testid="stPopoverBody"] .stButton > button:focus-visible,
            div[data-testid="stPopoverBody"] .stDownloadButton > button:focus-visible,
            div[data-testid="stPopoverBody"] .stButton > button:active,
            div[data-testid="stPopoverBody"] .stDownloadButton > button:active {
                padding:0!important; min-width:2.5rem!important;
                border:0!important; background:transparent!important; outline:0!important; box-shadow:none!important; transform:none!important;
            }
            div[data-testid="stHorizontalBlock"]:has(.lv-favorite-overlay) .stButton > button,
            div[data-testid="stHorizontalBlock"]:has(.lv-favorite-overlay) .stButton > button:hover,
            div[data-testid="stHorizontalBlock"]:has(.lv-favorite-overlay) .stButton > button:focus-visible,
            div[data-testid="stHorizontalBlock"]:has(.lv-favorite-overlay) .stButton > button:active {
                border:0!important; background:transparent!important;
                box-shadow:none!important; outline:0!important; transform:none!important;
            }
            div[data-testid="stHorizontalBlock"]:has(.lv-favorite-overlay) button[data-testid="stBaseButton-primary"] {
                color:#ff3b5c!important;
            }
            .st-key-gallery_navigation div[data-testid="stButtonGroup"] {
                margin:.2rem 0 1.15rem!important;
                overflow:visible!important;
                border-color:var(--lv-border)!important;
                background:var(--lv-surface)!important;
            }
            .st-key-gallery_navigation div[data-testid="stButtonGroup"] button {
                position:relative;
                margin-inline:.16rem!important;
                padding-inline:1rem!important;
                border:1px solid transparent!important;
                background:var(--lv-control)!important;
                color:var(--lv-muted)!important;
                box-shadow:none!important;
                transition:border-color 140ms ease,background 140ms ease,transform 140ms ease!important;
            }
            .st-key-gallery_navigation div[data-testid="stButtonGroup"] button:not([aria-pressed="true"]):not([kind="primary"]):not([data-testid="stBaseButton-primary"]),
            .st-key-gallery_navigation div[data-testid="stButtonGroup"] button:not([aria-pressed="true"]):not([kind="primary"]):not([data-testid="stBaseButton-primary"]) p,
            .st-key-gallery_navigation div[data-testid="stButtonGroup"] button:not([aria-pressed="true"]):not([kind="primary"]):not([data-testid="stBaseButton-primary"]) span {
                color:var(--lv-muted)!important;
                -webkit-text-fill-color:var(--lv-muted)!important;
            }
            .st-key-gallery_navigation div[data-testid="stButtonGroup"] button:hover {
                border-color:var(--lv-strong)!important;
                background:var(--lv-control-hover)!important;
                color:var(--lv-text)!important;
                transform:translateY(-1px)!important;
            }
            .st-key-gallery_navigation div[data-testid="stButtonGroup"] button:is([aria-pressed="true"],[aria-checked="true"],[data-state="on"],[kind="primary"],[data-testid="stBaseButton-primary"]) {
                border:2px solid var(--lv-accent)!important;
                background:var(--lv-soft)!important;
                box-shadow:0 0 0 1px var(--lv-strong)!important;
            }
            .st-key-gallery_navigation:has(.lv-selected-view) div[data-testid="stButtonGroup"] button:nth-of-type(1),
            .st-key-gallery_navigation:has(.lv-selected-favorites) div[data-testid="stButtonGroup"] button:nth-of-type(2),
            .st-key-gallery_navigation:has(.lv-selected-hidden) div[data-testid="stButtonGroup"] button:nth-of-type(3) {
                border:1px solid var(--lv-strong)!important;
                background:var(--lv-control-hover)!important;
                color:var(--lv-text)!important;
                box-shadow:0 0 0 1px var(--lv-border)!important;
            }
            .lv-selected-view,.lv-selected-favorites,.lv-selected-hidden { display:none!important; }
            .st-key-gallery_navigation div[data-testid="stButtonGroup"] button:is([aria-pressed="true"],[kind="primary"],[data-testid="stBaseButton-primary"]),
            .st-key-gallery_navigation div[data-testid="stButtonGroup"] button:is([aria-pressed="true"],[kind="primary"],[data-testid="stBaseButton-primary"]) p,
            .st-key-gallery_navigation div[data-testid="stButtonGroup"] button:is([aria-pressed="true"],[kind="primary"],[data-testid="stBaseButton-primary"]) span,
            .st-key-gallery_navigation div[data-testid="stButtonGroup"] button:hover p,
            .st-key-gallery_navigation div[data-testid="stButtonGroup"] button:hover span {
                color:var(--lv-text)!important;
                -webkit-text-fill-color:var(--lv-text)!important;
            }
            button:disabled { opacity:.42!important; transform:none!important; cursor:not-allowed!important; }
            .st-key-confirm_view_delete button {
                border-color:#f87171!important;
                background:#fecaca!important;
                color:#7f1d1d!important;
            }
            .st-key-confirm_view_delete button p,
            .st-key-confirm_view_delete button span,
            .st-key-confirm_view_delete button svg {
                color:#7f1d1d!important;
                fill:currentColor!important;
                -webkit-text-fill-color:#7f1d1d!important;
            }
            .st-key-confirm_view_delete button:hover {
                border-color:#fb7185!important;
                background:#fda4af!important;
                color:#881337!important;
            }
            .st-key-confirm_view_hide button {
                border-color:#94a3b8!important;
                background:#e2e8f0!important;
                color:#1e293b!important;
            }
            .st-key-confirm_view_hide button p,
            .st-key-confirm_view_hide button span,
            .st-key-confirm_view_hide button svg {
                color:#1e293b!important;
                fill:currentColor!important;
                -webkit-text-fill-color:#1e293b!important;
            }
            .st-key-confirm_view_hide button:hover {
                border-color:#cbd5e1!important;
                background:#cbd5e1!important;
                color:#0f172a!important;
            }
            div[data-baseweb="input"],div[data-baseweb="select"] > div { min-height:2.625rem; border-radius:.5rem!important; }
            .lv-gallery-transition { display:none; }
            @keyframes lv-gallery-out { to { opacity:0; transform:translateY(-16px); } }
            @keyframes lv-gallery-in { from { opacity:0; transform:translateY(16px); } to { opacity:1; transform:translateY(0); } }
            div[data-testid="stElementContainer"]:has(.lv-gallery-out) ~ * {
                animation:lv-gallery-out 160ms ease-in forwards;
                pointer-events:none;
                will-change:opacity,transform;
            }
            div[data-testid="stElementContainer"]:has(.lv-gallery-in) ~ * {
                animation:lv-gallery-in 180ms ease-out both;
                will-change:opacity,transform;
            }
            div[data-testid="stElementContainer"]:has(.lv-pagination) { display:none!important; }
            div[data-testid="stHorizontalBlock"]:has(.lv-pagination) {
                width:100%!important; max-width:20rem!important; margin:1.25rem auto 0!important;
                align-items:center!important; gap:.45rem!important;
            }
            @media (prefers-reduced-motion:reduce) { div[data-testid="stElementContainer"]:has(.lv-gallery-transition) ~ * { animation:none!important; } }
            @media (max-width:700px) {
                .block-container { padding:.85rem .8rem 2rem; }
                .lv-header { flex-wrap:nowrap!important; gap:.65rem; min-width:0; }
                .lv-header > div { min-width:0; }
                .lv-mark { flex:0 0 4rem; width:4rem; height:3.4rem; }
                .lv-title { white-space:nowrap; font-size:clamp(1.55rem,8vw,1.85rem); }
                div[data-testid="stHorizontalBlock"]:has(.lv-header) { flex-wrap:wrap!important; }
                div[data-testid="stHorizontalBlock"]:has(.lv-header) > div[data-testid="stColumn"] { flex:1 1 100%!important; width:100%!important; }
                .lv-subtitle { display:none; }
                div[data-testid="stTabs"] [data-baseweb="tab-list"] { width:100%; justify-content:space-around; }
                div[data-testid="stTabs"] [data-baseweb="tab"] { flex:1 1 0; justify-content:center; padding:0 .55rem; }
                div[data-testid="stHorizontalBlock"] { flex-direction:row!important; flex-wrap:nowrap!important; gap:.5rem!important; }
                div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] { min-width:0!important; }
                .st-key-gallery_navigation div[data-testid="stButtonGroup"] button {
                    overflow:visible!important;
                    padding-inline:.55rem!important;
                }
                .st-key-gallery_navigation div[data-testid="stButtonGroup"] button p { font-size:0!important; line-height:0!important; }
                .st-key-gallery_navigation div[data-testid="stButtonGroup"] button span[data-testid="stIconMaterial"],
                .st-key-gallery_navigation div[data-testid="stButtonGroup"] button .material-symbols-rounded { font-size:1.25rem!important; line-height:1!important; }
            }
                        /* mobile-sign-out-icon */
            @media (max-width:700px) {
                .st-key-header_sign_out,.st-key-header_sign_out .stButton { width:2.625rem!important; min-width:2.625rem!important; }
                .st-key-header_sign_out button { width:2.625rem!important; min-width:2.625rem!important; padding:0!important; }
                .st-key-header_sign_out button p { display:none!important; }
                .st-key-header_sign_out button span[data-testid="stIconMaterial"] { margin:0!important; }
                /* mobile-header-action-row */
                div[data-testid="stHorizontalBlock"]:has(.st-key-header_sign_out):not(:has(.lv-header)) { flex-wrap:nowrap!important; align-items:center!important; width:100%!important; }
                div[data-testid="stHorizontalBlock"]:has(.st-key-header_sign_out):not(:has(.lv-header)) > div[data-testid="stColumn"]:nth-child(1),
                div[data-testid="stHorizontalBlock"]:has(.st-key-header_sign_out):not(:has(.lv-header)) > div[data-testid="stColumn"]:nth-child(2) { flex:0 0 4.25rem!important; width:4.25rem!important; min-width:4.25rem!important; }
                div[data-testid="stHorizontalBlock"]:has(.st-key-header_sign_out):not(:has(.lv-header)) > div[data-testid="stColumn"]:nth-child(3) { flex:1 1 auto!important; width:auto!important; min-width:0!important; }
                div[data-testid="stHorizontalBlock"]:has(.st-key-header_sign_out):not(:has(.lv-header)) > div[data-testid="stColumn"]:nth-child(4) { flex:0 0 2.625rem!important; width:2.625rem!important; min-width:2.625rem!important; }
                .st-key-open_upload_dialog,.st-key-open_upload_dialog .stButton,.st-key-open_upload_dialog button { width:100%!important; min-width:0!important; }
                /* mobile-vibia-header-columns */
                div[data-testid="stHorizontalBlock"]:has(.st-key-header_sign_out):not(:has(.lv-header)) > div[data-testid="stColumn"]:has(.st-key-use_grid_view),
                div[data-testid="stHorizontalBlock"]:has(.st-key-header_sign_out):not(:has(.lv-header)) > div[data-testid="stColumn"]:has(.st-key-use_list_view) { flex:0 0 3.25rem!important; width:3.25rem!important; min-width:3.25rem!important; max-width:3.25rem!important; }
                div[data-testid="stHorizontalBlock"]:has(.st-key-header_sign_out):not(:has(.lv-header)) > div[data-testid="stColumn"]:has(.st-key-open_upload_dialog) { flex:1 1 0!important; width:auto!important; min-width:0!important; max-width:none!important; }
                div[data-testid="stHorizontalBlock"]:has(.st-key-header_sign_out):not(:has(.lv-header)) > div[data-testid="stColumn"]:has(.st-key-header_sign_out) { flex:0 0 2.625rem!important; width:2.625rem!important; min-width:2.625rem!important; max-width:2.625rem!important; }
                .st-key-open_upload_dialog button { overflow:hidden!important; padding-inline:.55rem!important; gap:.35rem!important; }
                .st-key-open_upload_dialog button p { overflow:hidden!important; text-overflow:ellipsis!important; white-space:nowrap!important; }
                .st-key-header_sign_out button { gap:0!important; overflow:hidden!important; }
            }</style>
            """,
        )

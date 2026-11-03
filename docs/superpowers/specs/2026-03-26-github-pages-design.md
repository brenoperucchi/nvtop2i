# gnvitop GitHub Pages — Design Spec

**Date:** 2026-03-26
**Status:** Approved

## Overview

A single-page project landing page hosted on GitHub Pages for gnvitop (v0.4.0). The goal is to showcase the project to potential users with a visually impressive dark tech aesthetic, rich animations, and clear installation instructions.

## File Structure

```
docs/
  index.html         # Main page (self-contained or minimal external assets)
  assets/
    logo.svg         # Reuse existing logo from /assets/logo.svg
```

GitHub Pages will be enabled via the `docs/` directory on the `main` branch (configured in repo Settings → Pages).

## Tech Stack

All libraries loaded from CDN — no build step required.

| Library | Purpose |
|---------|---------|
| Particles.js | Background particle network animation |
| Chart.js | Animated fake GPU usage chart in Hero |
| ScrollReveal | Scroll-triggered entrance animations |
| Typed.js | Typewriter effect on hero title |

## Visual Design

**Color Palette**
```
Background:  #0a0a0f  (near-black)
Primary:     #00ff88  (terminal green)
Accent:      #7c3aed  (purple, matching existing logo)
Card bg:     #111118
Text:        #e2e8f0
```

**Font:** System monospace stack for code elements; sans-serif for body text.

## Page Sections (in order)

### 1. Hero
- **Background:** Particles.js green particle network; particles attract toward cursor on hover
- **Title:** `"Global nvitop"` — Typed.js typewriter effect, blinking cursor
- **Subtitle:** Fades in after title completes: *"Web-based GPU monitoring dashboard for all your remote servers"*
- **Live Demo Widget:** A simulated GPU monitoring card group showing 3 fake servers, each with animated usage bars and numbers that randomly fluctuate in real-time (pure JS, no real data)
- **CTA Buttons:** "View on GitHub" + "Install via pip" — green glow + hover halo effect

### 2. Features
Six feature cards arranged in a 2×3 or 3×2 grid:
1. SSH Auto-Discovery — reads `~/.ssh/config` automatically
2. Real-time Refresh — auto-refreshes every 30 seconds
3. Current User Highlight — highlights your processes
4. TUI Mode — terminal UI via `--tui` flag
5. Agent JSON Output — `--agent` flag for scripting
6. Offline Detection — shows offline servers clearly

**Animation:** Cards slide up from below with staggered delay on scroll entry. Hover: card border glows green.

### 3. How It Works
Horizontal flow diagram: `gnvitop` → `SSH` → `nvidia-smi` → `Browser`

Each arrow animates sequentially (like data flowing through), triggered when section enters viewport.

### 4. Screenshots
Full-width display of the existing screenshot/GIF from the README. Decorated with a terminal window chrome (title bar with red/yellow/green dots). Optional: simple fade-in on scroll.

### 5. Installation & Usage
Dark terminal-style code blocks with green prompt characters. Content:
```bash
pip install gnvitop
gnvitop
```
Plus the key flags from the README. Each code block has a **Copy** button; clicking shows `"Copied!"` feedback for 2 seconds.

### 6. Footer
- GitHub star button (via `github-buttons`)
- PyPI version badge
- MIT License note
- Copyright line

## Animation Summary

| Effect | Library | Trigger |
|--------|---------|---------|
| Particle network background | Particles.js | Page load |
| Typewriter title | Typed.js | Page load |
| Fake GPU stats fluctuation | Vanilla JS setInterval | Page load |
| Section card entrance | ScrollReveal | Scroll into view |
| How It Works arrow flow | CSS animation + JS IntersectionObserver | Scroll into view |
| Card hover glow | CSS :hover | Mouse |
| Copy button feedback | Vanilla JS | Click |

## Deployment

1. Place files in `docs/` directory
2. Enable GitHub Pages in repo Settings → Pages → Source: `main` branch, `/docs` folder
3. Site available at `https://linwei94.github.io/gnvitop/`

## Out of Scope

- Real GPU data (all dashboard data in Hero is simulated)
- Multi-page documentation site
- Search functionality
- i18n / localization

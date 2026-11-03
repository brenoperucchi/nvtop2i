# GitHub Pages Landing Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-file, animation-rich GitHub Pages landing page for gnvitop with dark tech aesthetic, particle background, animated GPU dashboard preview, and scroll-triggered section animations.

**Architecture:** One self-contained `docs/index.html` with all CSS in a `<style>` block and all JS at the bottom before `</body>`. CDN libraries only — no build step. Six sections built and committed incrementally.

**Tech Stack:** Particles.js 2.0, Typed.js 2.1, ScrollReveal 4.x, vanilla JS for GPU widget and copy buttons. No framework.

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `docs/index.html` | Create | Entire page — HTML structure, inline CSS, inline JS |
| `docs/assets/logo.svg` | Copy from `assets/logo.svg` | Logo reuse |

---

### Task 1: Scaffold + Base Styles + Hero Shell

**Files:**
- Create: `docs/index.html`
- Create: `docs/assets/logo.svg` (copy)

- [ ] **Step 1: Copy the logo**

```bash
cp assets/logo.svg docs/assets/logo.svg
```

- [ ] **Step 2: Create `docs/index.html` with base scaffold, CSS variables, reset, and empty Hero section**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>gnvitop — Global GPU Monitor</title>
  <meta name="description" content="Web-based GPU monitoring dashboard for all your remote servers via SSH." />

  <!-- CDN Libraries -->
  <script src="https://cdn.jsdelivr.net/npm/particles.js@2.0.0/particles.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/typed.js@2.1.0/dist/typed.umd.js"></script>
  <script src="https://unpkg.com/scrollreveal"></script>

  <style>
    /* ── Variables ─────────────────────────────────── */
    :root {
      --bg:      #0a0a0f;
      --bg2:     #111118;
      --green:   #00ff88;
      --purple:  #7c3aed;
      --text:    #e2e8f0;
      --muted:   #94a3b8;
      --border:  #1e1e2e;
      --radius:  12px;
      --mono:    'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
    }

    /* ── Reset ─────────────────────────────────────── */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html { scroll-behavior: smooth; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      line-height: 1.6;
      overflow-x: hidden;
    }
    a { color: var(--green); text-decoration: none; }
    a:hover { text-decoration: underline; }

    /* ── Section layout helper ─────────────────────── */
    section {
      padding: 96px 24px;
      max-width: 1100px;
      margin: 0 auto;
    }
    .section-label {
      font-family: var(--mono);
      font-size: 0.75rem;
      color: var(--green);
      letter-spacing: 0.15em;
      text-transform: uppercase;
      margin-bottom: 12px;
    }
    h2.section-title {
      font-size: clamp(1.8rem, 4vw, 2.8rem);
      font-weight: 700;
      margin-bottom: 48px;
    }

    /* ── Hero ──────────────────────────────────────── */
    #hero {
      position: relative;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      text-align: center;
      padding: 0 24px;
      overflow: hidden;
      max-width: 100%;
    }
    #particles-js {
      position: absolute;
      inset: 0;
      z-index: 0;
    }
    .hero-content {
      position: relative;
      z-index: 1;
    }
    .hero-logo {
      width: 72px;
      height: 72px;
      margin-bottom: 24px;
      filter: drop-shadow(0 0 16px rgba(0,255,136,0.4));
    }
    .hero-title {
      font-size: clamp(2.5rem, 7vw, 5rem);
      font-weight: 800;
      letter-spacing: -0.02em;
      line-height: 1.1;
      min-height: 1.2em;
    }
    .typed-cursor { color: var(--green); }
    .hero-subtitle {
      font-size: clamp(1rem, 2.5vw, 1.3rem);
      color: var(--muted);
      margin-top: 16px;
      max-width: 600px;
      opacity: 0;
      transition: opacity 0.8s ease 0.5s;
    }
    .hero-subtitle.visible { opacity: 1; }
    .hero-cta {
      display: flex;
      gap: 16px;
      margin-top: 40px;
      flex-wrap: wrap;
      justify-content: center;
    }
    .btn {
      padding: 14px 32px;
      border-radius: 8px;
      font-weight: 600;
      font-size: 1rem;
      cursor: pointer;
      border: none;
      transition: all 0.2s;
    }
    .btn-primary {
      background: var(--green);
      color: #000;
      box-shadow: 0 0 24px rgba(0,255,136,0.3);
    }
    .btn-primary:hover {
      box-shadow: 0 0 40px rgba(0,255,136,0.6);
      transform: translateY(-2px);
      text-decoration: none;
    }
    .btn-secondary {
      background: transparent;
      color: var(--text);
      border: 1px solid var(--border);
    }
    .btn-secondary:hover {
      border-color: var(--green);
      color: var(--green);
      text-decoration: none;
      transform: translateY(-2px);
    }
  </style>
</head>
<body>

<!-- ═══════════════════════════════ HERO ══════ -->
<div id="hero">
  <div id="particles-js"></div>
  <div class="hero-content">
    <img src="assets/logo.svg" alt="gnvitop logo" class="hero-logo" />
    <h1 class="hero-title"><span id="typed-title"></span></h1>
    <p class="hero-subtitle" id="hero-subtitle">
      Web-based GPU monitoring dashboard for all your remote servers
    </p>
    <div class="hero-cta">
      <a href="https://github.com/Linwei94/gnvitop" class="btn btn-primary" target="_blank">View on GitHub</a>
      <a href="https://pypi.org/project/gnvitop/" class="btn btn-secondary" target="_blank">Install via pip</a>
    </div>
  </div>
</div>

<!-- JS will be added in later tasks -->

<script>
// Particles.js config
particlesJS('particles-js', {
  particles: {
    number: { value: 60, density: { enable: true, value_area: 800 } },
    color: { value: '#00ff88' },
    shape: { type: 'circle' },
    opacity: { value: 0.35, random: true },
    size: { value: 2, random: true },
    line_linked: { enable: true, distance: 140, color: '#00ff88', opacity: 0.15, width: 1 },
    move: { enable: true, speed: 1.2, direction: 'none', random: true, out_mode: 'out' }
  },
  interactivity: {
    detect_on: 'canvas',
    events: { onhover: { enable: true, mode: 'grab' }, onclick: { enable: true, mode: 'push' } },
    modes: { grab: { distance: 160, line_linked: { opacity: 0.5 } }, push: { particles_nb: 3 } }
  }
});

// Typed.js
const typed = new Typed('#typed-title', {
  strings: ['gnvitop'],
  typeSpeed: 80,
  startDelay: 400,
  showCursor: true,
  cursorChar: '█',
  onComplete: () => {
    document.getElementById('hero-subtitle').classList.add('visible');
  }
});
</script>
</body>
</html>
```

- [ ] **Step 3: Verify visually — open in browser**

```bash
python3 -m http.server 9000 --directory docs
# Open http://localhost:9000 — expect: dark background, green particles, "gnvitop" typing out, subtitle fades in, two CTA buttons
```

- [ ] **Step 4: Commit**

```bash
git add docs/index.html docs/assets/logo.svg
git commit -m "feat: add GitHub Pages scaffold with hero section and particles"
```

---

### Task 2: Hero GPU Widget

Add the animated fake GPU monitoring widget below the CTA buttons inside `.hero-content`.

**Files:**
- Modify: `docs/index.html`

- [ ] **Step 1: Add CSS for the GPU widget** — insert inside the `<style>` block, after `.btn-secondary:hover { ... }`:

```css
/* ── GPU Widget ────────────────────────────────── */
.gpu-widget {
  margin-top: 56px;
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  justify-content: center;
}
.gpu-server-card {
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px 20px;
  min-width: 220px;
  text-align: left;
  transition: border-color 0.3s;
}
.gpu-server-card:hover { border-color: var(--green); }
.gpu-server-name {
  font-family: var(--mono);
  font-size: 0.8rem;
  color: var(--green);
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.gpu-server-name::before {
  content: '';
  display: inline-block;
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--green);
  box-shadow: 0 0 6px var(--green);
  animation: pulse 2s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
.gpu-row {
  margin-bottom: 10px;
}
.gpu-row-header {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  color: var(--muted);
  margin-bottom: 4px;
  font-family: var(--mono);
}
.gpu-row-header .gpu-util {
  color: var(--text);
  font-weight: 600;
}
.gpu-bar-track {
  height: 6px;
  background: var(--border);
  border-radius: 3px;
  overflow: hidden;
}
.gpu-bar-fill {
  height: 100%;
  border-radius: 3px;
  background: linear-gradient(90deg, var(--green), var(--purple));
  transition: width 1.2s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 0 8px rgba(0,255,136,0.4);
}
.gpu-mem {
  font-size: 0.7rem;
  color: var(--muted);
  margin-top: 3px;
  font-family: var(--mono);
}
```

- [ ] **Step 2: Add GPU widget HTML** — insert inside `.hero-content`, after `</div>` (the `.hero-cta` div):

```html
<!-- Simulated GPU Monitor Widget -->
<div class="gpu-widget" id="gpu-widget">
  <!-- Cards injected by JS -->
</div>
```

- [ ] **Step 3: Add GPU widget JS** — insert inside the `<script>` block, after the Typed.js code:

```javascript
// Simulated GPU servers
const servers = [
  { name: 'server-a', gpus: [{ label: 'A100 #0', mem: 40 }, { label: 'A100 #1', mem: 80 }] },
  { name: 'server-b', gpus: [{ label: 'RTX 4090 #0', mem: 24 }, { label: 'RTX 4090 #1', mem: 24 }] },
  { name: 'server-c', gpus: [{ label: 'V100 #0', mem: 16 }] },
];

// State: current utilization per GPU
const state = servers.map(s => ({
  ...s,
  gpus: s.gpus.map(g => ({ ...g, util: Math.floor(Math.random() * 80) + 10 }))
}));

function renderGpuWidget() {
  const container = document.getElementById('gpu-widget');
  container.innerHTML = state.map((server, si) => `
    <div class="gpu-server-card">
      <div class="gpu-server-name">${server.name}</div>
      ${server.gpus.map((gpu, gi) => `
        <div class="gpu-row">
          <div class="gpu-row-header">
            <span>${gpu.label}</span>
            <span class="gpu-util" id="util-${si}-${gi}">${state[si].gpus[gi].util}%</span>
          </div>
          <div class="gpu-bar-track">
            <div class="gpu-bar-fill" id="bar-${si}-${gi}" style="width:${state[si].gpus[gi].util}%"></div>
          </div>
          <div class="gpu-mem">${gpu.mem}GB VRAM</div>
        </div>
      `).join('')}
    </div>
  `).join('');
}

function updateGpuStats() {
  state.forEach((server, si) => {
    server.gpus.forEach((gpu, gi) => {
      // Random walk ±15%
      let u = state[si].gpus[gi].util + (Math.random() * 30 - 15);
      u = Math.max(5, Math.min(98, u));
      state[si].gpus[gi].util = Math.round(u);
      const bar = document.getElementById(`bar-${si}-${gi}`);
      const util = document.getElementById(`util-${si}-${gi}`);
      if (bar) bar.style.width = u + '%';
      if (util) util.textContent = Math.round(u) + '%';
    });
  });
}

renderGpuWidget();
setInterval(updateGpuStats, 2000);
```

- [ ] **Step 4: Verify visually**

```bash
# Reload http://localhost:9000
# Expect: 3 server cards below CTA buttons, GPU bars animating every 2 seconds, hover glows green
```

- [ ] **Step 5: Commit**

```bash
git add docs/index.html
git commit -m "feat: add animated fake GPU monitoring widget in hero"
```

---

### Task 3: Features Section

**Files:**
- Modify: `docs/index.html`

- [ ] **Step 1: Add Features CSS** — insert inside `<style>` after the GPU widget styles:

```css
/* ── Features ──────────────────────────────────── */
#features { border-top: 1px solid var(--border); }
.features-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 24px;
}
.feature-card {
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 28px;
  transition: border-color 0.3s, box-shadow 0.3s;
}
.feature-card:hover {
  border-color: var(--green);
  box-shadow: 0 0 20px rgba(0,255,136,0.08);
}
.feature-icon {
  font-size: 1.8rem;
  margin-bottom: 16px;
}
.feature-card h3 {
  font-size: 1.05rem;
  font-weight: 600;
  margin-bottom: 8px;
}
.feature-card p {
  color: var(--muted);
  font-size: 0.9rem;
  line-height: 1.6;
}
```

- [ ] **Step 2: Add Features HTML** — insert after the closing `</div>` of `#hero`:

```html
<!-- ═══════════════════════════ FEATURES ══════ -->
<section id="features">
  <p class="section-label">Why gnvitop</p>
  <h2 class="section-title">Everything you need to<br>monitor your GPU cluster</h2>
  <div class="features-grid">
    <div class="feature-card">
      <div class="feature-icon">🔌</div>
      <h3>SSH Auto-Discovery</h3>
      <p>Reads your <code>~/.ssh/config</code> automatically. No extra configuration — if SSH works, gnvitop works.</p>
    </div>
    <div class="feature-card">
      <div class="feature-icon">⚡</div>
      <h3>Real-time Refresh</h3>
      <p>Dashboard auto-refreshes every 30 seconds with live GPU utilization, memory, and process data.</p>
    </div>
    <div class="feature-card">
      <div class="feature-icon">👤</div>
      <h3>Current User Highlight</h3>
      <p>Your processes are highlighted so you instantly see what's yours on a shared cluster.</p>
    </div>
    <div class="feature-card">
      <div class="feature-icon">🖥️</div>
      <h3>TUI Mode</h3>
      <p>Prefer the terminal? Run <code>gnvitop --tui</code> for a full-featured terminal UI — no browser needed.</p>
    </div>
    <div class="feature-card">
      <div class="feature-icon">🤖</div>
      <h3>Agent JSON Output</h3>
      <p>Use <code>gnvitop --agent</code> to get structured JSON of GPU availability — perfect for automation scripts.</p>
    </div>
    <div class="feature-card">
      <div class="feature-icon">🔴</div>
      <h3>Offline Detection</h3>
      <p>Servers that can't be reached are clearly shown as offline — no silent failures, no confusion.</p>
    </div>
  </div>
</section>
```

- [ ] **Step 3: Add ScrollReveal initialization** — insert inside the `<script>` block, at the end:

```javascript
// ScrollReveal
ScrollReveal().reveal('.feature-card', {
  delay: 100,
  distance: '30px',
  origin: 'bottom',
  interval: 80,
  duration: 600,
  easing: 'cubic-bezier(0.4, 0, 0.2, 1)',
  reset: false
});
```

- [ ] **Step 4: Verify visually**

```bash
# Reload http://localhost:9000 and scroll down
# Expect: 6 feature cards slide up from below in staggered sequence, hover shows green glow border
```

- [ ] **Step 5: Commit**

```bash
git add docs/index.html
git commit -m "feat: add features section with ScrollReveal entrance animation"
```

---

### Task 4: How It Works Section

**Files:**
- Modify: `docs/index.html`

- [ ] **Step 1: Add How It Works CSS** — insert inside `<style>` after Features styles:

```css
/* ── How It Works ──────────────────────────────── */
#how-it-works { border-top: 1px solid var(--border); }
.flow-diagram {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 0;
  margin-top: 48px;
}
.flow-node {
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px 28px;
  text-align: center;
  min-width: 140px;
  opacity: 0;
  transform: translateY(16px);
  transition: opacity 0.5s ease, transform 0.5s ease, border-color 0.3s;
}
.flow-node.active {
  opacity: 1;
  transform: translateY(0);
}
.flow-node:hover { border-color: var(--green); }
.flow-node-icon { font-size: 2rem; margin-bottom: 8px; }
.flow-node-label {
  font-family: var(--mono);
  font-size: 0.85rem;
  color: var(--green);
  font-weight: 600;
}
.flow-node-desc {
  font-size: 0.75rem;
  color: var(--muted);
  margin-top: 4px;
}
.flow-arrow {
  width: 48px;
  height: 2px;
  background: var(--border);
  position: relative;
  flex-shrink: 0;
  overflow: hidden;
}
.flow-arrow::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, var(--green), var(--purple));
  width: 0%;
  transition: width 0.6s ease;
}
.flow-arrow.active::after { width: 100%; }
.flow-arrow-head {
  position: absolute;
  right: -1px;
  top: 50%;
  transform: translateY(-50%);
  width: 0; height: 0;
  border-top: 5px solid transparent;
  border-bottom: 5px solid transparent;
  border-left: 8px solid var(--purple);
  opacity: 0;
  transition: opacity 0.3s ease 0.5s;
}
.flow-arrow.active .flow-arrow-head { opacity: 1; }
@media (max-width: 640px) {
  .flow-diagram { flex-direction: column; }
  .flow-arrow { width: 2px; height: 32px; }
  .flow-arrow::after { width: 100%; height: 0%; transition: height 0.6s ease; }
  .flow-arrow.active::after { height: 100%; }
}
```

- [ ] **Step 2: Add How It Works HTML** — insert after the closing `</section>` of `#features`:

```html
<!-- ═══════════════════════════ HOW IT WORKS ══════ -->
<section id="how-it-works">
  <p class="section-label">Under the hood</p>
  <h2 class="section-title">How it works</h2>
  <div class="flow-diagram" id="flow-diagram">
    <div class="flow-node" data-step="0">
      <div class="flow-node-icon">⚙️</div>
      <div class="flow-node-label">gnvitop</div>
      <div class="flow-node-desc">Python process<br>on your machine</div>
    </div>
    <div class="flow-arrow" data-step="1"><div class="flow-arrow-head"></div></div>
    <div class="flow-node" data-step="2">
      <div class="flow-node-icon">🔐</div>
      <div class="flow-node-label">SSH</div>
      <div class="flow-node-desc">Reads ~/.ssh/config<br>connects to each host</div>
    </div>
    <div class="flow-arrow" data-step="3"><div class="flow-arrow-head"></div></div>
    <div class="flow-node" data-step="4">
      <div class="flow-node-icon">🖥️</div>
      <div class="flow-node-label">nvidia-smi</div>
      <div class="flow-node-desc">Runs remotely<br>collects GPU stats</div>
    </div>
    <div class="flow-arrow" data-step="5"><div class="flow-arrow-head"></div></div>
    <div class="flow-node" data-step="6">
      <div class="flow-node-icon">🌐</div>
      <div class="flow-node-label">Browser</div>
      <div class="flow-node-desc">Live dashboard<br>auto-refreshes</div>
    </div>
  </div>
</section>
```

- [ ] **Step 3: Add flow animation JS** — insert inside `<script>` at the end:

```javascript
// Flow diagram sequential animation on scroll
(function() {
  const diagram = document.getElementById('flow-diagram');
  if (!diagram) return;
  const nodes = diagram.querySelectorAll('[data-step]');
  let animated = false;

  const observer = new IntersectionObserver(entries => {
    if (entries[0].isIntersecting && !animated) {
      animated = true;
      nodes.forEach(el => {
        const step = parseInt(el.dataset.step);
        setTimeout(() => el.classList.add('active'), step * 250);
      });
    }
  }, { threshold: 0.4 });

  observer.observe(diagram);
})();
```

- [ ] **Step 4: Verify visually**

```bash
# Reload and scroll to "How it works"
# Expect: 4 nodes and 3 arrows appear sequentially left-to-right with flowing green line
```

- [ ] **Step 5: Commit**

```bash
git add docs/index.html
git commit -m "feat: add How It Works section with sequential flow animation"
```

---

### Task 5: Screenshots Section

**Files:**
- Modify: `docs/index.html`

> **Note:** The README references a GitHub-hosted image at `https://github.com/user-attachments/assets/2ca35564-c891-4af9-9b30-5ebb0949ba99`. Use that URL directly (it's already public).

- [ ] **Step 1: Add Screenshots CSS** — insert inside `<style>` after How It Works styles:

```css
/* ── Screenshots ───────────────────────────────── */
#screenshots { border-top: 1px solid var(--border); }
.terminal-window {
  background: #1a1a2e;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  box-shadow: 0 24px 80px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.04);
}
.terminal-titlebar {
  background: #16162a;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  border-bottom: 1px solid var(--border);
}
.terminal-dot {
  width: 12px; height: 12px;
  border-radius: 50%;
}
.terminal-dot.red   { background: #ff5f57; }
.terminal-dot.yellow{ background: #febc2e; }
.terminal-dot.green { background: #28c840; }
.terminal-title {
  font-family: var(--mono);
  font-size: 0.75rem;
  color: var(--muted);
  margin-left: 8px;
}
.terminal-body img {
  width: 100%;
  display: block;
}
```

- [ ] **Step 2: Add Screenshots HTML** — insert after closing `</section>` of `#how-it-works`:

```html
<!-- ═══════════════════════════ SCREENSHOTS ══════ -->
<section id="screenshots">
  <p class="section-label">See it in action</p>
  <h2 class="section-title">Beautiful dashboard,<br>zero configuration</h2>
  <div class="terminal-window">
    <div class="terminal-titlebar">
      <div class="terminal-dot red"></div>
      <div class="terminal-dot yellow"></div>
      <div class="terminal-dot green"></div>
      <span class="terminal-title">gnvitop — localhost:5000</span>
    </div>
    <div class="terminal-body">
      <img
        src="https://github.com/user-attachments/assets/2ca35564-c891-4af9-9b30-5ebb0949ba99"
        alt="gnvitop dashboard screenshot"
        loading="lazy"
      />
    </div>
  </div>
</section>
```

- [ ] **Step 3: Add ScrollReveal for terminal window** — inside `<script>`, add to the existing ScrollReveal block:

```javascript
ScrollReveal().reveal('.terminal-window', {
  delay: 100,
  distance: '40px',
  origin: 'bottom',
  duration: 700,
  easing: 'cubic-bezier(0.4, 0, 0.2, 1)',
  reset: false
});
```

- [ ] **Step 4: Verify visually**

```bash
# Reload and scroll to "See it in action"
# Expect: terminal chrome with traffic-light dots, screenshot inside, fades up on scroll
```

- [ ] **Step 5: Commit**

```bash
git add docs/index.html
git commit -m "feat: add screenshots section with terminal window decoration"
```

---

### Task 6: Installation & Usage Section

**Files:**
- Modify: `docs/index.html`

- [ ] **Step 1: Add Installation CSS** — insert inside `<style>` after Screenshots styles:

```css
/* ── Installation ──────────────────────────────── */
#installation { border-top: 1px solid var(--border); }
.install-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 32px;
}
@media (max-width: 640px) { .install-grid { grid-template-columns: 1fr; } }
.code-block {
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}
.code-block-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  background: #0d0d1a;
  border-bottom: 1px solid var(--border);
  font-family: var(--mono);
  font-size: 0.75rem;
  color: var(--muted);
}
.copy-btn {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--muted);
  border-radius: 4px;
  padding: 3px 10px;
  font-family: var(--mono);
  font-size: 0.7rem;
  cursor: pointer;
  transition: all 0.2s;
}
.copy-btn:hover { border-color: var(--green); color: var(--green); }
.copy-btn.copied { border-color: var(--green); color: var(--green); }
.code-block pre {
  padding: 20px;
  overflow-x: auto;
  font-family: var(--mono);
  font-size: 0.85rem;
  line-height: 1.8;
}
.prompt { color: var(--green); user-select: none; }
.cmd { color: var(--text); }
.comment { color: var(--muted); }
.flag { color: #7dd3fc; }
```

- [ ] **Step 2: Add Installation HTML** — insert after closing `</section>` of `#screenshots`:

```html
<!-- ═══════════════════════════ INSTALLATION ══════ -->
<section id="installation">
  <p class="section-label">Get started</p>
  <h2 class="section-title">Up and running<br>in 30 seconds</h2>
  <div class="install-grid">

    <div class="code-block" id="cb-install">
      <div class="code-block-header">
        <span>Install</span>
        <button class="copy-btn" onclick="copyCode('cb-install', 'pip install gnvitop')">Copy</button>
      </div>
      <pre><span class="prompt">$ </span><span class="cmd">pip install gnvitop</span></pre>
    </div>

    <div class="code-block" id="cb-run">
      <div class="code-block-header">
        <span>Run</span>
        <button class="copy-btn" onclick="copyCode('cb-run', 'gnvitop')">Copy</button>
      </div>
      <pre><span class="prompt">$ </span><span class="cmd">gnvitop</span>
<span class="comment"># Opens dashboard in your browser</span></pre>
    </div>

    <div class="code-block" id="cb-flags">
      <div class="code-block-header">
        <span>Common flags</span>
        <button class="copy-btn" onclick="copyCode('cb-flags', 'gnvitop -p 8080\ngnvitop --host 0.0.0.0\ngnvitop --tui\ngnvitop --agent')">Copy</button>
      </div>
      <pre><span class="prompt">$ </span><span class="cmd">gnvitop <span class="flag">-p 8080</span></span>              <span class="comment"># custom port</span>
<span class="prompt">$ </span><span class="cmd">gnvitop <span class="flag">--host 0.0.0.0</span></span>       <span class="comment"># expose to LAN</span>
<span class="prompt">$ </span><span class="cmd">gnvitop <span class="flag">--tui</span></span>               <span class="comment"># terminal UI</span>
<span class="prompt">$ </span><span class="cmd">gnvitop <span class="flag">--agent</span></span>             <span class="comment"># JSON output</span></pre>
    </div>

    <div class="code-block" id="cb-agent">
      <div class="code-block-header">
        <span>Agent mode output</span>
        <button class="copy-btn" onclick="copyCode('cb-agent', 'gnvitop --agent')">Copy</button>
      </div>
      <pre><span class="prompt">$ </span><span class="cmd">gnvitop <span class="flag">--agent</span></span>
<span class="comment">[{"host":"server-a","gpu":0,
  "available":true,"util":12},
 {"host":"server-b","gpu":1,
  "available":false,"util":95}]</span></pre>
    </div>

  </div>
</section>
```

- [ ] **Step 3: Add copy button JS** — insert inside `<script>` at the end:

```javascript
function copyCode(blockId, text) {
  navigator.clipboard.writeText(text).then(() => {
    const btn = document.querySelector(`#${blockId} .copy-btn`);
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(() => {
      btn.textContent = 'Copy';
      btn.classList.remove('copied');
    }, 2000);
  });
}
```

- [ ] **Step 4: Add ScrollReveal for code blocks** — inside `<script>`, add:

```javascript
ScrollReveal().reveal('.code-block', {
  delay: 80,
  distance: '20px',
  origin: 'bottom',
  interval: 100,
  duration: 500,
  reset: false
});
```

- [ ] **Step 5: Verify visually**

```bash
# Reload and scroll to "Get started"
# Expect: 4 terminal code blocks in 2-column grid, copy button shows "Copied!" on click, green prompt chars
```

- [ ] **Step 6: Commit**

```bash
git add docs/index.html
git commit -m "feat: add installation section with copyable terminal code blocks"
```

---

### Task 7: Footer + Final Polish

**Files:**
- Modify: `docs/index.html`

- [ ] **Step 1: Add Footer CSS** — insert inside `<style>` after Installation styles:

```css
/* ── Footer ────────────────────────────────────── */
footer {
  border-top: 1px solid var(--border);
  padding: 48px 24px;
  text-align: center;
}
.footer-badges {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 24px;
}
.footer-meta {
  font-size: 0.85rem;
  color: var(--muted);
}
.footer-meta a { color: var(--muted); }
.footer-meta a:hover { color: var(--green); }

/* ── Navbar ────────────────────────────────────── */
nav {
  position: fixed;
  top: 0; left: 0; right: 0;
  z-index: 100;
  padding: 14px 32px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: rgba(10,10,15,0.85);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid transparent;
  transition: border-color 0.3s;
}
nav.scrolled { border-bottom-color: var(--border); }
.nav-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 700;
  font-size: 1.05rem;
  color: var(--text);
}
.nav-brand img { width: 28px; height: 28px; }
.nav-links {
  display: flex;
  gap: 24px;
  list-style: none;
}
.nav-links a {
  color: var(--muted);
  font-size: 0.9rem;
  transition: color 0.2s;
}
.nav-links a:hover { color: var(--green); text-decoration: none; }

/* ── Scrollbar ─────────────────────────────────── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--green); }
```

- [ ] **Step 2: Add Navbar HTML** — insert at the very start of `<body>`, before `<div id="hero">`:

```html
<nav id="navbar">
  <a href="#" class="nav-brand" style="text-decoration:none">
    <img src="assets/logo.svg" alt="gnvitop" />
    gnvitop
  </a>
  <ul class="nav-links">
    <li><a href="#features">Features</a></li>
    <li><a href="#how-it-works">How it works</a></li>
    <li><a href="#screenshots">Screenshots</a></li>
    <li><a href="#installation">Install</a></li>
    <li><a href="https://github.com/Linwei94/gnvitop" target="_blank">GitHub</a></li>
  </ul>
</nav>
```

- [ ] **Step 3: Add Footer HTML** — insert after closing `</section>` of `#installation`, before `</body>`:

```html
<!-- ════════════════════════════ FOOTER ══════════ -->
<footer>
  <div class="footer-badges">
    <a href="https://pypi.org/project/gnvitop/" target="_blank">
      <img src="https://img.shields.io/pypi/v/gnvitop?color=00ff88&labelColor=111118&style=flat-square" alt="PyPI version" />
    </a>
    <a href="https://pypi.org/project/gnvitop/" target="_blank">
      <img src="https://img.shields.io/pypi/pyversions/gnvitop?labelColor=111118&style=flat-square" alt="Python versions" />
    </a>
    <a href="https://github.com/Linwei94/gnvitop/blob/main/LICENSE" target="_blank">
      <img src="https://img.shields.io/github/license/Linwei94/gnvitop?labelColor=111118&style=flat-square" alt="License" />
    </a>
    <a href="https://github.com/Linwei94/gnvitop/stargazers" target="_blank">
      <img src="https://img.shields.io/github/stars/Linwei94/gnvitop?style=flat-square&labelColor=111118&color=7c3aed" alt="GitHub stars" />
    </a>
  </div>
  <p class="footer-meta">
    MIT License &nbsp;·&nbsp;
    <a href="https://github.com/Linwei94/gnvitop" target="_blank">GitHub</a> &nbsp;·&nbsp;
    <a href="https://pypi.org/project/gnvitop/" target="_blank">PyPI</a>
  </p>
</footer>
```

- [ ] **Step 4: Add navbar scroll JS** — insert inside `<script>` at the end:

```javascript
// Navbar border on scroll
window.addEventListener('scroll', () => {
  document.getElementById('navbar').classList.toggle('scrolled', window.scrollY > 10);
});
```

- [ ] **Step 5: Verify visually — full page review**

```bash
# Reload http://localhost:9000
# Check full page top to bottom:
# ✓ Fixed navbar appears, border shows on scroll
# ✓ Hero: particles, typewriter, GPU widget animating
# ✓ Features: 6 cards slide in on scroll, hover glow
# ✓ How it works: flow animates left to right
# ✓ Screenshots: terminal chrome with dashboard image
# ✓ Installation: 4 code blocks, copy works
# ✓ Footer: badges and links render
# ✓ Green scrollbar
```

- [ ] **Step 6: Commit**

```bash
git add docs/index.html
git commit -m "feat: add navbar, footer, polish — GitHub Pages complete"
```

---

### Task 8: Deploy to GitHub Pages

**Files:**
- No code changes

- [ ] **Step 1: Push to remote**

```bash
git push origin main
```

- [ ] **Step 2: Enable GitHub Pages in repo settings**

Go to: `https://github.com/Linwei94/gnvitop/settings/pages`

Set:
- Source: **Deploy from a branch**
- Branch: `main`
- Folder: `/docs`

Click **Save**.

- [ ] **Step 3: Wait ~60 seconds, then verify**

Visit: `https://linwei94.github.io/gnvitop/`

Expected: Full landing page loads with all animations working.

- [ ] **Step 4: Add Pages URL to README** — add this line to the top of `README.md`, after the badges:

```markdown
<p align="center">
  <a href="https://linwei94.github.io/gnvitop/">🌐 Live Demo</a>
</p>
```

- [ ] **Step 5: Commit and push**

```bash
git add README.md
git commit -m "docs: add GitHub Pages link to README"
git push origin main
```

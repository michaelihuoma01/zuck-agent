<h1 align="center">ZURK</h1>

<p align="center">
  <strong>The Remote Command Center for Claude Code</strong><br/>
  Control your AI coding agent from anywhere. Approve changes from your phone.<br/>
  Live-preview your app — directly from your laptop on your phone before commiting.
</p>

<p align="center">
  <a href="#installation">Install</a> •
  <a href="#live-preview">Live Preview</a> •
  <a href="#remote-access">Remote Access</a> •
  <a href="#features">Features</a> •
  <a href="#why-zurk">Why ZURK</a>
</p>

---

## The Problem

You fire up Claude Code, give it a task, and then... you wait. Staring at a terminal. On your desk. Unable to walk away.

Every other tool keeps you tethered to your machine. Cloud-based coding assistants only work inside their own sandboxed environments. Terminal-based agents demand you sit in front of the screen to approve every file write. And none of them let you see what your app actually looks like while the AI is building it.

**What if you could walk away?**

## The Solution

ZURK turns your laptop into a self-hosted AI command center. It wraps Claude Code in a real-time web interface that you can access from **any device** — your phone, your tablet, etc. Code and preview your changes from the gym, at the airport, while in commute, going for a walk, etc. Review diffs on the train. Watch your app take shape in a live preview while Claude writes the code.

```
Your Laptop (always running)          Any Device
┌────────────────────────┐            ┌──────────┐
│   ZURK Command Center  │◄──────────►│  Phone   │
│   + Claude Code        │  Tailscale │  Tablet  │
│   + Your Projects      │  or LAN    │  Laptop  │
│   + Live Dev Servers   │            │  Desktop │
└────────────────────────┘            └──────────┘
```

---

## Live Preview

**This is the killer feature no other tool has.**

ZURK auto-detects your project type (Vite, Next.js, Create React App, Nuxt, Flask, Django) and can spin up a live dev server — right on your machine, accessible from your phone using the ZURK PWA.

While Claude is writing code, you're watching the changes appear in real time in an actual running instance of your app. Not a screenshot. Not a sandbox. **Your actual project, running on your actual machine, with your actual data.**

- Auto-detects project framework (Vite, Next.js, CRA, Nuxt, Flask, Django, and more)
- One-click start/stop from the project page or session view
- Accessible over LAN or Tailscale — preview from your phone while Claude codes on your laptop
- Dev server runs in an isolated process — won't interfere with ZURK

**No other Claude Code interface offers this.** Cloud tools give you a sandboxed preview at best. Terminal-based tools give you nothing. ZURK gives you the real thing.

---

### From Anywhere in the World

Pair ZURK with [Tailscale](https://tailscale.com) for zero-config encrypted access from anywhere:

```bash
./scripts/setup_tailscale.sh
```

Three modes:
- **Quick** — HTTP within your tailnet (instant)
- **HTTPS** — TLS via `tailscale serve` (enables PWA install)
- **Funnel** — Public internet access (use with caution)

### Install as a Native App

ZURK is a Progressive Web App. Over HTTPS (Tailscale), you can install it as a native app on iOS, Android, macOS, or any platform with a modern browser. Full offline shell, push-ready architecture, home screen icon.

---

## Features

### Real-Time Session Control
Start Claude Code sessions from your phone. Send follow-up prompts. Watch messages stream in real-time over WebSocket with automatic reconnection and SSE fallback. Cancel stuck sessions instantly.

### Intelligent Approval Workflow
When Claude wants to write a file or run a command, ZURK pauses and notifies you. Review unified diffs with syntax highlighting. Inspect Bash commands with risk-level badges. Approve with a tap or deny with feedback — Claude reads your reason and adjusts its approach. Keyboard shortcuts (`a` / `d` / `Esc`) for power users.

### External Session Discovery
Already use Claude Code from the terminal? ZURK scans your local Claude session history and lets you browse, read, and **continue** any past session — right from the ZURK interface. No migration needed. Zero lock-in.

### Multi-Project Management
Register multiple project directories. Each gets its own session history, tool permissions, and live preview configuration. Switch between projects instantly.

### Production-Grade Infrastructure
- **Auto-start on boot** via macOS launchd with crash recovery
- **Health monitoring** with automatic restart on failure
- **Database backups** (daily, WAL-safe, 7-day retention)
- **Structured logging** with rotation (never fills your disk)
- **CLI management** via the `zurk` command

---

## Why ZURK

| | ZURK | Terminal Claude Code | Cloud Coding Tools |
|---|:---:|:---:|:---:|
| Work from your phone | **Yes** | No | Yes |
| Live preview of your actual app | **Yes** | No | Sandboxed only |
| Runs on your machine with your files | **Yes** | Yes | No |
| Approve changes remotely | **Yes** | No | Varies |
| Continue existing Claude sessions | **Yes** | N/A | No |
| No vendor lock-in | **Yes** | Yes | No |
| Offline-capable PWA | **Yes** | N/A | No |
| Zero cloud dependencies | **Yes** | Yes | No |

ZURK is the only tool that combines **local-first architecture** with **remote-first access**. Your code never leaves your machine. Your dev server runs locally. But you control everything from anywhere.

---

## Installation

### One-Line Install

```bash
curl -fsSL https://raw.githubusercontent.com/YOUR_USER/zurk/main/scripts/install.sh | bash
```

### Manual Install

```bash
git clone https://github.com/YOUR_USER/zurk.git && cd zurk
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cd frontend && npm install && npm run build && cd ..
cp .env.example .env   # Add your ANTHROPIC_API_KEY
```

### Running

```bash
# Development (hot reload)
./scripts/start.sh --dev

# Production
./scripts/start.sh

# Install as system service (auto-start on boot)
./scripts/install_service.sh
```

### CLI

```bash
zurk start          # Start the server
zurk stop           # Stop the server
zurk status         # Server health + stats
zurk logs           # Tail application logs
zurk backup         # Trigger a database backup
zurk dev            # Development mode with hot reload
```

---

## Requirements

- Python 3.11+
- Node.js 18+ (for frontend build; not needed with release install)
- An [Anthropic API key](https://console.anthropic.com)
- macOS or Linux (Windows via WSL)

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Agent Runtime | Claude Code SDK (Python) |
| Backend | FastAPI, SQLAlchemy 2.0, async SQLite |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS v4 |
| Real-Time | WebSocket + SSE fallback |
| Remote Access | Tailscale / LAN |
| App Shell | Progressive Web App (service worker) |

---

## Contributing

Contributions welcome! Please open an issue first to discuss what you'd like to change.

```bash
# Run the test suite
pytest tests/ -v

# Lint and format
black src/ tests/ && ruff check src/ tests/ --fix

# Type-check frontend
cd frontend && npx tsc --noEmit
```

## License

MIT — use it, fork it, ship it.

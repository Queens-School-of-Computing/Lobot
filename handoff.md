# Handoff — Lobot / QSC Cluster Work

**Date:** 2026-08-19
**Author:** Claude Code session with Aaron Visser
**Scope:** Current goals, session outcomes, and a digest of persistent memory for whoever (or whatever) picks this up next.

**Update (2026-08-19, later same day):** Investigated a reported lobot-tui
color/brand issue — top/bottom bars rendering grey instead of Queen's Blue.
Root cause was **not** a code bug: the terminal session was running inside
GNU `screen` with `TERM=screen` and no `COLORTERM`, so Rich/Textual fell back
to 16-color mode and downsampled `#002452` to grey. Fixed on the host via
`~/.screenrc` (`term screen-256color`, `truecolor on`). An initial round of
code edits (swapping hardcoded `cyan`/`yellow` Rich markup to Queen's Gold in
`main_screen.py`, `status_bar.py`, `actions_panel.py`) targeted the wrong
layer and was reverted — no lasting changes in Lobot-tools from this. See
`project_lobot_tui_screen_color.md`.

---

## 1. Open Goals

In rough priority order:

### 1.1 Deploy lobot_metrics — DEPLOYED ✅
The resource-tracking/billing component in `Lobot-tools/lobot_metrics/` is live
on the cluster. Development has continued post-deploy: heatmaps and improved
timezone handling in the email digest, more advanced digest filtering, and
colour improvements. See `project_lobot_metrics.md`.

### 1.2 Spawn page image info integration — DONE ✅
The JupyterHub spawn page's image selection now surfaces per-image info,
built on `component-versions.json` (nightly component versions, auto-pushed to
GitHub each changed build) and `IMAGE-COMPONENTS.md` (static stack inventory).

### 1.3 Component version tracking system — DEPLOYED ✅ (2026-06-10)
Nightly builds are version-driven instead of CACHE_BUST-driven. See
`project_qsc_version_tracking.md` for the full mechanism.

### 1.4 Backburner / future
- Slack notifications for image scripts (listed as future work in IMAGE-MANAGEMENT.md)
- Self-hosting assets instead of `raw.githubusercontent.com` (see `project_cdn_migration.md`)
- ChromeDriver-style version pinning audit elsewhere if Selenium issues persist

Nothing new is currently flagged as an open goal beyond the backburner list
above — the three items that headlined the previous handoff (2026-06-10) are
all complete.

---

## 2. What Happened Recently

- **2026-08-17/19:** Added `flock`-based self-locking to
  `build_push_qscimages.sh` so a second concurrent invocation exits
  immediately instead of racing. Docs (`BUILD-PUSH-QSCIMAGES.md` + `.html`)
  updated with a new "Concurrency Lock" section. Pushed to `master`
  (`91b840b`). Background and root cause recorded in
  `project_qscimages_duplicate_builds.md` for anyone who wants the story.
- **lobot_metrics:** deployed and iterated on since — heatmaps, digest
  filtering, timezone fixes, colour improvements (see Lobot-tools commit
  history).
- **Spawn page:** image info icon integration completed.

---

## 3. Memory Digest

Persistent memory lives at `~/.claude/projects/-Users-aaron-Documents-GitHub-Queens-School-of-Computing-Lobot/memory/` (mirrored in the `claude-memories` repo, `lobot/` subdir).

### Repos and layout
- **Lobot** (`Queens-School-of-Computing/Lobot`, branch `main`) — JupyterHub config only.
- **Lobot-tools** — all scripts, tools, and docs (IMAGE-MANAGEMENT, lobot-tui, lobot_metrics, etc.). Deployed to `/opt/Lobot/tools/` on cluster nodes.
- **gpu-jupyter-latest** — Docker image generator for the cluster's JupyterLab images (branch `master`). `.build/Dockerfile` is **generated** by `generate-Dockerfile.sh` from `custom/*.Dockerfile` fragments — never edit it directly; fix the fragment. The dated files (`Dockerfile.YYYYMMDD`) are standalone snapshots used by the nightly build.
- HTML files across repos are WordPress page fragments, not standalone documents.

### Cluster facts
- Control plane: `lobot-dev.cs.queensu.ca` — always excluded from node operations.
- Container runtime: containerd v2.2.1 — use `ctr`, not `crictl`.
- Build server: dedicated host (`distribution`, Ubuntu 26.04), pushes to DockerHub only; cluster pulls handled by `image-pull.sh` from Lobot-tools.
- SMTP relay: `innovate.cs.queensu.ca:25`, unauthenticated.

### Standing rules
- **Config sync:** `config.yaml.bk` is the shared base; `config-dev.yaml.bk` / `config-prod.yaml.bk` are thin overrides. `apply-config.sh` produces `config.yaml` + `config-env.yaml` on the server; helm upgrade always uses both. Update image tags in **both** env override files.
- **Doc sync:** changes to `image-pull.sh` / `image-cleanup.sh` require updating both IMAGE-MANAGEMENT.md **and** .html. Same md+html pairing applies to BUILD-PUSH-QSCIMAGES.
- **Status page:** served via JupyterHub `extra_handlers` at `/hub/status`; HTML at `/etc/jupyterhub/custom/status/status.html`.

### Nightly image pipeline (gpu-jupyter-latest)
- `build_push_qscimages.sh` on the build server: baseline build (once per dated Dockerfile) + version-driven nightly build (skips when nothing changed; `--force` overrides). Now self-locking via `flock` to prevent concurrent runs.
- Five tags per version across two lineages: baseline `...-DATE`, incremental `...-DATE-nightly` / `...-DATE-nightly-BUILDDATE`, full `...-DATE-nightly-full` / `...-DATE-nightly-full-BUILDDATE` (weekly `--full` no-cache rebuild).
- DockerHub pruning keeps `KEEP_NIGHTLY_COUNT=3` dated tags per lineage; local dated images are pruned entirely after push.
- Cron on `distribution`: `0 2 * * *` incremental (`--nightly-only`), `--full` on Sundays; creds sourced from `/etc/lobot/dockerhub-creds`.

### lobot-tui
- Code in Lobot-tools (`lobot_tui/`, `lobot_collector/`); Textual 8.1.1 in `/opt/Lobot/tools/lobot_tui/.venv` (Python 3.12); Textual is on the remote servers, not local. See `project_lobot_tui_state.md` for development state and safety flags.
- If colors look wrong in a live session, check `TERM`/`COLORTERM` and Rich's `color_system` first — a `screen`/`tmux` session without truecolor advertised will downsample the Queen's Blue chrome to grey even though the theme code is correct. See `project_lobot_tui_screen_color.md`.

### URL hosting
- Asset URLs are back on `raw.githubusercontent.com` (reverted 2026-04-13 after a block was lifted; jsDelivr was a temporary workaround). Self-hosting remains a future consideration. See `project_cdn_migration.md`.

### User preferences
- **Questions:** use AskUserQuestion with selectable options; prefix labels with numbers ("1. ...", "2. ...") since the UI doesn't number them; note the "Other" number in the question text. Aaron answers with a single keypress.
- Aaron works in VS Code on macOS; `gh` CLI is **not** installed locally.
- Narrate reasoning in visible output — Aaron reads along as work happens, not just the final summary.

---

## 4. Environment Cheatsheet

| Thing | Where |
|---|---|
| Lobot repo (local) | `~/Documents/GitHub/Queens-School-of-Computing/Lobot` |
| Lobot-tools repo (local) | `~/Documents/GitHub/Queens-School-of-Computing/Lobot-tools` |
| gpu-jupyter-latest repo (local) | `~/Documents/GitHub/Queens-School-of-Computing/gpu-jupyter-latest` |
| Memory (live) | `~/.claude/projects/-Users-aaron-...-Lobot/memory/` |
| Memory (repo mirror) | `~/Documents/GitHub/claude-memories/lobot/` |
| Build script | `gpu-jupyter-latest/build_push_qscimages.sh` |
| Build doc | `gpu-jupyter-latest/BUILD-PUSH-QSCIMAGES.md` + `.html` |
| Dated Dockerfiles | `gpu-jupyter-latest/.build/Dockerfile.20260313`, `.20260424` |
| Fragment with QSC packages | `gpu-jupyter-latest/custom/qscpackages.Dockerfile` |

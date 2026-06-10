# Handoff — Lobot / QSC Cluster Work

**Date:** 2026-06-10
**Author:** Claude Code session with Aaron Visser
**Scope:** Current goals, session outcomes, and a digest of persistent memory for whoever (or whatever) picks this up next.

---

## 1. Open Goals

In rough priority order:

### 1.1 Spawn page image info integration (next up)
Aaron's stated plan: an information icon on the JupyterHub spawn page's image
selection showing what each image contains. Building blocks are live:
`component-versions.json` (nightly component versions + `build_date`,
auto-pushed to GitHub each changed build) and `IMAGE-COMPONENTS.md` (static
stack inventory per image: CUDA/TF/PyTorch/MATLAB etc.), both in the
gpu-jupyter-latest repo, fetchable via raw.githubusercontent.com. The spawn
page templates live in the Lobot repo (`templates/`, profile list config).

### 1.2 Component version tracking system — DEPLOYED 2026-06-10 ✅
Nightly builds are version-driven instead of CACHE_BUST-driven. Files in
gpu-jupyter-latest (`master`, all pushed): `resolve_component_versions.py`
(queries 9 upstream APIs), `component-versions.json` manifest (created by the
first build-server run; `build_date` + component versions + Dockerfile hashes;
auto-committed to GitHub after successful runs), restructured dated
Dockerfiles (per-component `ARG <X>_VERSION`, ordered least→most frequently
updated, Claude Code last), `build_push_qscimages.sh` (skip-when-unchanged,
`--force` overrides), `IMAGE-COMPONENTS.md`. Docs (md + html) updated, fixing
all three discrepancies from the 2026-06-10 morning review.

**Deployment done on distribution build server (2026-06-10):** crontab now
`cd … && git pull --rebase && ./build_push_qscimages.sh --nightly-only`;
GitHub PAT stored via credential.helper store (user wiegerthefarmer — note:
GitHub `ghp_` token, NOT the DockerHub `dckr_pat_`); dry-run verified on the
server (all 9 endpoints reachable, both Dockerfiles BUILD). First real run
2026-06-11 02:00: full component rebuild (no manifest yet + restructure +
ChromeDriver fix), creates and pushes the manifest. From then on: skip or
partial rebuilds. Check the morning email + manifest commit history.

### 1.3 Deploy lobot_metrics (stalled since 2026-05-07)
The resource-tracking/billing component in `Lobot-tools/lobot_metrics/` is committed but never deployed. Six deploy steps are recorded in memory (`project_lobot_metrics.md`): create `/opt/Lobot/metrics_data`, venv + requirements, billing config from sample, init DB, install the three systemd units. The web dashboard is deferred to a future phase.

### 1.4 Backburner / future
- Slack notifications for image scripts (listed as future work in IMAGE-MANAGEMENT.md)
- Self-hosting assets instead of `raw.githubusercontent.com` (see `project_cdn_migration.md`)
- ChromeDriver-style version pinning audit elsewhere if Selenium issues persist

### A note on `/goal`
Aaron believed he'd set goals via a `/goal` command. No such command exists in `~/.claude/commands/` or any project `.claude/commands/`, and no goal files were found anywhere on disk — whatever `/goal` was, it persisted nothing. The list above was reconstructed from session history and memory instead.

---

## 2. What Happened This Session (2026-06-10)

1. **Reviewed BUILD-PUSH-QSCIMAGES.md** against the script — found the three discrepancies in §1.2 (still unfixed).
2. **Diagnosed and fixed the ChromeDriver pin.** All ChromeDriver installs now resolve the driver version at build time: read installed Chrome's major version, query `googlechromelabs.github.io/chrome-for-testing/LATEST_RELEASE_<MAJOR>`, download that exact build. Applied to `Dockerfile.20260313`, `Dockerfile.20260424`, `Dockerfile`, `Dockerfile.current`, and `custom/qscpackages.Dockerfile`. Committed (see §1.1), **not pushed**.
3. **Explained the red squiggle** on the code-server block in the dated Dockerfiles: it's hadolint rule **DL4001** ("Either use Wget or Curl but not both") surfaced by the VS Code Docker extension — a style warning, not an error. BuildKit's `--check` passes the file. Aaron decided to drop it; no suppression was added.
4. **Recorded a UX preference** (see §3, user preferences).

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
- Build server: dedicated host (Ubuntu 26.04), pushes to DockerHub only; cluster pulls handled by `image-pull.sh` from Lobot-tools.
- SMTP relay: `innovate.cs.queensu.ca:25`, unauthenticated.

### Standing rules
- **Config sync:** `config.yaml.bk` is the shared base; `config-dev.yaml.bk` / `config-prod.yaml.bk` are thin overrides. `apply-config.sh` produces `config.yaml` + `config-env.yaml` on the server; helm upgrade always uses both. Update image tags in **both** env override files.
- **Doc sync:** changes to `image-pull.sh` / `image-cleanup.sh` require updating both IMAGE-MANAGEMENT.md **and** .html. Same md+html pairing applies to BUILD-PUSH-QSCIMAGES.
- **Status page:** served via JupyterHub `extra_handlers` at `/hub/status`; HTML at `/etc/jupyterhub/custom/status/status.html`.

### Nightly image pipeline (gpu-jupyter-latest)
- `build_push_qscimages.sh` on the build server: baseline build (once per dated Dockerfile) + nightly build (CACHE_BUST forces fresh layers for Chrome/ChromeDriver/selenium deps, VS Code, code-server, Ollama, Claude Code, uv, opencode).
- Three tags per version: baseline `...-DATE`, floating `...-DATE-nightly` (what hub pages reference), dated `...-DATE-nightly-BUILDDATE` (rollback).
- DockerHub pruning keeps `KEEP_NIGHTLY_COUNT=3` dated tags; local dated images are pruned entirely after push.
- Cron: `0 2 * * *` with `--nightly-only`, creds sourced from `/etc/lobot/dockerhub-creds`.

### lobot-tui
- Code in Lobot-tools (`lobot_tui/`, `lobot_collector/`); Textual 8.1.1 in `/opt/Lobot/tools/lobot_tui/.venv` (Python 3.12); Textual is on the remote servers, not local. See `project_lobot_tui_state.md` for development state and safety flags.

### URL hosting
- Asset URLs are back on `raw.githubusercontent.com` (reverted 2026-04-13 after a block was lifted; jsDelivr was a temporary workaround). Self-hosting remains a future consideration. See `project_cdn_migration.md`.

### User preferences
- **Questions:** use AskUserQuestion with selectable options; prefix labels with numbers ("1. ...", "2. ...") since the UI doesn't number them; note the "Other" number in the question text. Aaron answers with a single keypress.
- Aaron works in VS Code on macOS; `gh` CLI is **not** installed locally.

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

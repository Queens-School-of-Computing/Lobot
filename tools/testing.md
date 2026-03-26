# Lobot Test Suite

Automated tests for the Python modules and shell scripts in `tools/`. Tests run on the dev
server via SSH using the existing TUI Python virtual environment.

---

## Quick Start

```bash
# Run all tests (unit + integration + safe script tests)
/opt/Lobot/tools/run-tests.sh -v

# Run opt-in dry-run script tests (creates temporary pods, no emails, no real pulls or deletions)
/opt/Lobot/tools/run-tests.sh -v -m script_integration

# Run a specific file
/opt/Lobot/tools/run-tests.sh -v tools/tests/test_parsers.py

# Run a specific test class or function
/opt/Lobot/tools/run-tests.sh -v -k TestParseCpuRequest
/opt/Lobot/tools/run-tests.sh -v -k "test_invalid_expand_size_format"
```

The wrapper script (`run-tests.sh`) works from any directory — it resolves paths relative
to the repo root at `/opt/Lobot` and uses the venv at
`/opt/Lobot/tools/lobot_tui/.venv/bin/python3`.

---

## Test Files

| File | What it tests | Always runs? |
|------|--------------|:------------:|
| `tools/tests/test_parsers.py` | Pure Python parsing functions (`parsers.py`) | ✓ |
| `tools/tests/test_models.py` | Domain dataclasses and `ClusterState` serialization (`models.py`) | ✓ |
| `tools/tests/test_collector_integration.py` | Live HTTP endpoints of the lobot-collector service | If service is up |
| `tools/tests/test_scripts.py` | Shell script argument errors, `lv-manage.sh` info mode | Mostly ✓ |

### test_parsers.py (71 tests)

Tests every function in `lobot_tui/data/parsers.py` using fixture JSON constructed in
`conftest.py`. No kubectl or network access required.

| Class | What it covers |
|-------|---------------|
| `TestPodUsername` | `jupyter-` prefix stripping, `-2d` → `-` hyphen unescaping |
| `TestParseImageTag` | Tag extraction, truncation at `MAX_TAG_LEN` (66 chars) |
| `TestAgeString` | ISO8601 → human age (seconds/minutes/hours/days buckets), `Z` suffix, error cases |
| `TestParseCpuRequest` | `"4"`, `"500m"`, `"1000m"`, empty/invalid → float cores |
| `TestParseMemoryRequestGb` | `Ki`, `Mi`, `Gi`, `Ti`, `G`, `M` unit suffixes → float GB |
| `TestParseGpuRequest` | Integer parsing, `None`/empty → 0 |
| `TestParsePods` | Full pod JSON → `PodInfo` list: fields, sorting, resource map, invalid JSON |
| `TestParseNodes` | Full node JSON → `NodeInfo` + resource map: control plane, cordoned, NotReady |
| `TestMergeNodesAndPods` | Aggregation: all-pod vs jupyter-only for `ResourceSummary`, control plane excluded |
| `TestParseLonghornNodes` | Disk JSON → `DiskInfo`: uninitialized disk skipped, sorted by name |

### test_models.py (31 tests)

Tests computed properties and serialization in `lobot_tui/data/models.py`.

| Class | What it covers |
|-------|---------------|
| `TestResourceSummary` | `cpu_used`, `ram_used_gb`, `gpu_used`, `has_gpu` |
| `TestNodeInfo` | `cordoned`, `cpu_free`, `ram_free_gb`, `gpu_free` — all clamped at zero |
| `TestDiskInfo` | `used_gb`, clamped at zero when available > total |
| `TestClusterStateSerialization` | `to_dict()` / `from_dict()` round-trip for all fields, datetime ISO serialization, `None` datetimes, backward-compat `"labs"` key, error fields preserved |

### test_collector_integration.py (17 tests)

Tests the live lobot-collector HTTP service on `127.0.0.1:9095`. Skipped automatically if
the service is not reachable.

| Class | What it covers |
|-------|---------------|
| `TestApiState` | `/api/state`: HTTP 200, `application/json` content-type, valid JSON, deserializes to `ClusterState`, all top-level keys present, node/pod field validation, no service error, consistency across repeated calls |
| `TestApiEvents` | `/api/events`: HTTP 200, `text/event-stream` content-type, first SSE event is valid JSON, deserializes to `ClusterState`, node set matches `/api/state` |

### test_scripts.py (23 tests, 5 opt-in)

Tests shell scripts by invoking them with `bash` via `subprocess.run`.

| Class | What it covers | Opt-in? |
|-------|---------------|:-------:|
| `TestImagePullArgErrors` | Missing `-i` → exit 1; `-n` + `-e` together → exit 1 | No |
| `TestImageCleanupArgErrors` | Same as above for `image-cleanup.sh` | No |
| `TestLvManageArgErrors` | No args → exit 1 + usage; `--expand 100` (no suffix) → exit 1; `--expand 100K` (wrong suffix) → exit 1 | No |
| `TestSyncGroupsHelp` | `--help` → exit 0 + usage text | No |
| `TestLvManageInfo` | Real PVC info output (read-only kubectl queries); nonexistent PVC → exit 1 with error | If kubectl up |
| `TestImagePullDryRun` | `--dry-run --yes -n <node>`: exit 0, node in output, present/missing reported | **Yes** |
| `TestImageCleanupDryRun` | `--dry-run --yes`: exit 0, produces output | **Yes** |

The two `TestLvManageArgErrors` expand tests (`test_invalid_expand_size_format` and
`test_invalid_expand_size_wrong_suffix`) both pass a throwaway PVC name (`"some-pvc"`)
that doesn't exist on the cluster. This is intentional — `lv-manage.sh` validates the
`--expand` size format before making any kubectl calls, so the script exits with an error
before it ever tries to look up the PVC. The two tests cover two distinct failure modes:
a missing suffix entirely (`"100"`) and a suffix that exists but isn't in the allowed set
(`"100K"` — only `M`, `G`, `T` are accepted).

There are no tests for a successful `--expand` operation. Unlike `lv-manage.sh` info
mode (which is read-only), actually expanding a volume is irreversible and there is no
`--dry-run` flag for it, so a success test would modify real cluster state.

The `script_integration` tests pass `--noemail` to suppress email notifications during
testing. They still create temporary pods on the cluster and are excluded from the default
run via `addopts = "-m 'not script_integration'"` in `pyproject.toml`.

---

## How Tests Work

The suite has four distinct categories of tests, each with a different correctness
guarantee. Understanding the distinction helps you know what a passing run actually
proves — and what it doesn't.

### 1. Unit tests (`test_parsers.py`, `test_models.py`)

These test pure Python functions in complete isolation — no network, no kubectl, no
cluster state. They run in under a second and never fail due to infrastructure problems.

**How they work:** `conftest.py` constructs realistic but controlled fixture data: a fake
`kubectl get pods -o json` response containing three pods (a normal jupyter pod, a pod
whose username contains a hyphen-escaped character, and a non-jupyter system pod), a fake
node list with one worker and one control-plane node, and a fake Longhorn node list with
one initialized disk and one uninitialized disk. The tests feed this known input to each
parsing function and assert the exact output.

**What they guarantee:** That the parsing and model logic is correct for every input
shape the code is supposed to handle. Edge cases are tested explicitly:

- The `-2d` → `-` hyphen unescaping in pod usernames (JupyterHub encodes hyphens this
  way; getting it wrong would show corrupted usernames in the TUI)
- `Ki`, `Mi`, `Gi`, `Ti`, `G`, `M` memory suffixes all converting to the right GB value
- `500m` CPU millicores converting to `0.5` cores
- Uninitialized Longhorn disks (where `storageMaximum == 0`) being skipped entirely
- Control-plane nodes being excluded from resource aggregation
- `ClusterState.to_dict()` / `from_dict()` round-tripping correctly, including `None`
  datetimes and the old `"labs"` wire format key

**What they don't guarantee:** That `kubectl` actually returns JSON in the shape the
fixtures assume. If a Kubernetes upgrade changes a field path, these tests will still
pass — the collector integration tests are what catch that.

---

### 2. Collector integration tests (`test_collector_integration.py`)

These make real HTTP requests to the live `lobot-collector` service running on the dev
server at `127.0.0.1:9095`. All 17 tests are automatically skipped if the service is not
reachable, so they never cause failures in a CI or offline context.

**How they work:** A small stdlib `http.client` helper connects to the collector and
makes real requests. The tests assert on the actual HTTP responses — status codes,
content-type headers, JSON structure, and field types. For the SSE endpoint
(`/api/events`), the test reads bytes from the stream until it finds a complete
`data: {...}\n\n` event, then deserializes and validates it.

**What they guarantee:** That the entire data pipeline — kubectl → parser → model → HTTP
response — produces output that is structurally valid and internally consistent:

- `/api/state` returns HTTP 200 with `application/json` and a body that deserializes into
  a `ClusterState` without errors
- All expected top-level keys (`nodes`, `pods`, `resources`, `longhorn_disks`, etc.) are
  present
- Node and pod fields have the correct types (strings, numbers, booleans — not `None`
  where values are required)
- Two back-to-back calls return the same set of node names (the service is stable, not
  oscillating)
- The first SSE event from `/api/events` is also a valid `ClusterState`, and its node set
  matches the `/api/state` response

**What they don't guarantee:** That the *values* are accurate (e.g., that the reported
CPU count matches the actual hardware). They verify structure and type correctness, not
domain accuracy. Running these requires the dev server to be up and `lobot-collector`
to be running.

---

### 3. Shell script argument tests (`test_scripts.py` — always-run)

These invoke the real shell scripts with bad or missing arguments and assert on exit codes
and output. They run without any cluster access — they only test the scripts' input
validation layer.

**How they work:** `subprocess.run(["bash", str(TOOLS_DIR / script)] + list(args), ...)`
runs the actual script. The tests check `result.returncode` and `result.stdout +
result.stderr`. Because these tests deliberately trigger early-exit error paths (missing
required flags, mutually exclusive flags, invalid format strings), no cluster calls are
ever made.

**What they guarantee:** That the scripts reject bad input correctly and produce
human-readable error output — i.e., that the defensive input validation layer works:

- `image-pull.sh` with no `-i` flag exits non-zero and prints an error
- `image-pull.sh` with both `-n` and `-e` exits non-zero (they're mutually exclusive)
- `lv-manage.sh` with no arguments exits non-zero and prints usage
- `lv-manage.sh --expand 100K` exits non-zero because `K` is not a valid size suffix
  (only `M`, `G`, `T` are accepted)
- `sync_groups.sh --help` exits 0 and prints usage text

**What they don't guarantee:** That the scripts do the right thing on a real cluster.
That's what the opt-in dry-run tests cover.

---

### 4. Dry-run script tests (`test_scripts.py` — `script_integration`, opt-in)

These run `image-pull.sh` and `image-cleanup.sh` end-to-end against the real cluster,
using `--dry-run --yes --noemail`. They are excluded from the default run because they
create temporary pods, which takes ~60 seconds. No emails are sent and no images are
actually pulled or removed.

**How they work:** The test first calls `kubectl get nodes` to find a real Ready worker
node, then runs the full script with `--dry-run`. The script genuinely executes its
kubectl calls — it creates a temporary `alpine:latest` pod on the target node (for
`image-pull.sh`) or deploys a DaemonSet (for `image-cleanup.sh`) — but stops short of
actually pulling or deleting anything.

**What they guarantee:** That the scripts' full execution path works on real
infrastructure, from argument parsing through kubectl calls to output formatting and exit:

- The script exits 0 (no crash, no unhandled error, no kubectl failure)
- The target node name appears in the output (the node targeting logic worked)
- The output contains words like "present", "pull", or "would" (the script reported
  something meaningful rather than silently doing nothing)

**What they don't guarantee:** That a real (non-dry-run) execution would succeed. For
example, a permissions problem that only manifests when actually deleting images would
not be caught here.

---

### The overall picture

Each layer catches a different class of bug:

| Layer | Catches |
|-------|---------|
| Unit tests | Wrong field paths, unit conversion errors, sorting/filtering logic, serialization bugs |
| Collector integration | Broken kubectl output shape, collector service crashes, invalid HTTP responses |
| Script argument tests | Missing input validation, wrong exit codes, confusing error messages |
| Script dry-run tests | kubectl call failures, broken node targeting, script crashes on real infra |

A change that breaks `_parse_cpu_request` will fail unit tests in milliseconds. A
Kubernetes upgrade that renames a JSON field will pass unit tests but fail the collector
integration tests the next time the service runs. A shell script that accidentally accepts
conflicting flags will pass everything except the argument tests.

---

## Expected Output

### Default run — `run-tests.sh -v`

```
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.0.2, pluggy-1.6.0
rootdir: /opt/Lobot
plugins: asyncio-1.3.0
asyncio: mode=Mode.AUTO

collecting ... collected 142 items / 5 deselected / 137 selected

tools/tests/test_models.py::TestResourceSummary::test_cpu_used PASSED
tools/tests/test_models.py::TestResourceSummary::test_cpu_used_all_free PASSED
...
tools/tests/test_scripts.py::TestLvManageInfo::test_exits_zero_for_valid_pvc PASSED
tools/tests/test_scripts.py::TestLvManageInfo::test_produces_output_for_valid_pvc PASSED
tools/tests/test_scripts.py::TestLvManageInfo::test_nonexistent_pvc_exits_nonzero PASSED
tools/tests/test_scripts.py::TestLvManageInfo::test_nonexistent_pvc_prints_error PASSED

====================== 137 passed, 5 deselected in 3.70s =======================
```

The 5 deselected tests are the `script_integration` dry-run tests.

If lobot-collector is not running, the 17 integration tests show as skipped:

```
====================== 120 passed, 5 deselected, 17 skipped in 1.20s ===========
```

### Opt-in dry-run tests — `run-tests.sh -v -m script_integration`

```
collecting ... collected 5 items

tools/tests/test_scripts.py::TestImagePullDryRun::test_dry_run_single_node_exits_zero PASSED
tools/tests/test_scripts.py::TestImagePullDryRun::test_dry_run_output_mentions_node PASSED
tools/tests/test_scripts.py::TestImagePullDryRun::test_dry_run_reports_present_or_missing PASSED
tools/tests/test_scripts.py::TestImageCleanupDryRun::test_dry_run_exits_zero PASSED
tools/tests/test_scripts.py::TestImageCleanupDryRun::test_dry_run_produces_output PASSED

========================== 5 passed in 56.39s ==================================
```

These take ~60 seconds due to pod creation. No emails are sent — `--noemail` is passed
by the tests.

### Unit tests only — `run-tests.sh -v tools/tests/test_parsers.py tools/tests/test_models.py`

```
collecting ... collected 102 items

...

============================= 102 passed in 0.33s ==============================
```

### Integration tests only — `run-tests.sh -v tools/tests/test_collector_integration.py`

```
collecting ... collected 17 items

tools/tests/test_collector_integration.py::TestApiState::test_returns_200 PASSED
...
tools/tests/test_collector_integration.py::TestApiEvents::test_first_event_matches_state_endpoint PASSED

============================= 17 passed in 0.50s =======================
```

---

## Configuration

Test configuration lives in the `[tool.pytest.ini_options]` section of `/opt/Lobot/pyproject.toml`:

```toml
[tool.pytest.ini_options]
pythonpath = ["tools"]          # makes lobot_tui importable as a package
testpaths = ["tools/tests"]     # default discovery path
asyncio_mode = "auto"           # for any future async tests
addopts = "-m 'not script_integration'"   # exclude email-sending tests from default run
markers = [
    "script_integration: dry-run shell script tests that send real emails and create cluster pods (opt-in)",
]
```

---

## Setup (first time)

Pytest and pytest-asyncio are listed in `tools/lobot_tui/requirements-tui.txt` and must
be installed in the TUI venv:

```bash
/opt/Lobot/tools/lobot_tui/.venv/bin/pip install pytest pytest-asyncio
```

This only needs to be done once. After that, `run-tests.sh` handles everything.

---

## Adding New Tests

- **Unit tests for Python modules**: add to `test_parsers.py`, `test_models.py`, or create
  a new `test_<module>.py` file in `tools/tests/`.
- **Collector integration tests**: add to `test_collector_integration.py`.
- **Shell script tests without side effects**: add to `test_scripts.py` in the appropriate
  class (no mark needed).
- **Shell script tests with side effects** (emails, pod creation): add to `test_scripts.py`
  decorated with `@pytest.mark.script_integration`.

Fixture JSON for `_parse_pods`, `_parse_nodes`, and `_parse_longhorn_nodes` lives in
`tools/tests/conftest.py` and is shared across all test files.

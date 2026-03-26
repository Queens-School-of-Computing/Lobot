# Lobot Test Suite

Automated tests for the Python modules and shell scripts in `tools/`. Tests run on the dev
server via SSH using the existing TUI Python virtual environment.

---

## Quick Start

```bash
# Run all tests (unit + integration + safe script tests)
/opt/Lobot/tools/run-tests.sh -v

# Run with opt-in dry-run script tests (sends real emails, creates pods)
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
| `TestLvManageArgErrors` | No args → exit 1 + usage; invalid `--expand` size format → exit 1 | No |
| `TestSyncGroupsHelp` | `--help` → exit 0 + usage text | No |
| `TestLvManageInfo` | Real PVC info output; nonexistent PVC → exit 1 with error | If kubectl up |
| `TestImagePullDryRun` | `--dry-run --yes -n <node>`: exit 0, node in output, present/missing reported | **Yes** |
| `TestImageCleanupDryRun` | `--dry-run --yes`: exit 0, produces output | **Yes** |

The `script_integration` tests pass `--noemail` to suppress email notifications during
testing. They still create temporary pods on the cluster and are excluded from the default
run via `addopts = "-m 'not script_integration'"` in `pyproject.toml`.

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

"""Global in-process command log — captures all commands run in this session."""

from collections import deque
from datetime import datetime
from pathlib import Path

from ..config import LOG_DIR

_MAX = 300
_log: deque = deque(maxlen=_MAX)


def _log_file() -> Path:
    """Return today's log file path, creating the directory if needed."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR / f"lobot-tui-{datetime.now().strftime('%Y-%m-%d')}.log"


def record(command: str, lines: list, exit_code: int | None) -> None:
    """Record a completed command to the in-process deque and the daily log file."""
    ts_full = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ts_short = datetime.now().strftime("%H:%M:%S")
    _log.appendleft({
        "ts": ts_short,
        "command": command,
        "lines": lines,
        "exit_code": exit_code,
    })

    # Append to the persistent daily log file (never raises — can't break the TUI)
    try:
        code_str = f"exit {exit_code}" if exit_code is not None else "failed to launch"
        with _log_file().open("a") as f:
            f.write(f"[{ts_full}] [{code_str}] $ {command}\n")
            for line in lines:
                f.write(f"  {line}\n")
            if lines:
                f.write("\n")
    except Exception:
        pass


def entries() -> list:
    return list(_log)

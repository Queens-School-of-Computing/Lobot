"""Global in-process command log — captures all commands run by ActionScreen."""

from collections import deque
from datetime import datetime

_MAX = 300
_log: deque = deque(maxlen=_MAX)


def record(command: str, lines: list, exit_code: int | None) -> None:
    _log.appendleft({
        "ts": datetime.now().strftime("%H:%M:%S"),
        "command": command,
        "lines": lines,
        "exit_code": exit_code,
    })


def entries() -> list:
    return list(_log)

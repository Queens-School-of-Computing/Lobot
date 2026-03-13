"""ActionRunner: async subprocess runner that streams output line by line."""

import asyncio
from typing import AsyncIterator


async def run_command(argv: list, cwd: str = None) -> AsyncIterator[str]:
    """
    Run the given command and yield output lines as they arrive.
    Yields the exit code as a final line: "[exit N]"
    """
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    async for raw_line in proc.stdout:
        yield raw_line.decode(errors="replace").rstrip()
    await proc.wait()
    yield f"[exit {proc.returncode}]"

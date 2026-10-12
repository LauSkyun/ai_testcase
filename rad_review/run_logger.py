from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


class RunLogger:
    def __init__(self, path: Path, echo: bool | None = None) -> None:
        self.path = path
        self.echo = self._resolve_echo(echo)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write_line("run log started")

    def info(self, message: str, **fields: Any) -> None:
        self._write_line(message, **fields)

    @contextmanager
    def step(self, name: str, **fields: Any) -> Iterator[None]:
        start = time.perf_counter()
        self._write_line(f"ENTER {name}", **fields)
        try:
            yield
        except Exception as exc:
            elapsed = time.perf_counter() - start
            self._write_line(f"EXIT {name} failed", elapsed=f"{elapsed:.3f}s", error=str(exc))
            raise
        else:
            elapsed = time.perf_counter() - start
            self._write_line(f"EXIT {name} ok", elapsed=f"{elapsed:.3f}s")

    def _write_line(self, message: str, **fields: Any) -> None:
        timestamp = datetime.now().isoformat(timespec="seconds")
        details = " ".join(f"{key}={self._format_value(value)}" for key, value in fields.items())
        line = f"[{timestamp}] {message}"
        if details:
            line = f"{line} {details}"
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        if self.echo:
            print(f"[RAD][log] {line}", file=sys.stderr)

    def _format_value(self, value: Any) -> str:
        text = str(value).replace("\n", "\\n")
        if " " in text:
            return repr(text)
        return text

    def _resolve_echo(self, echo: bool | None) -> bool:
        if echo is not None:
            return echo
        env_value = os.getenv("RAD_LOG_ECHO", "").strip().lower()
        if env_value in {"1", "true", "yes", "on"}:
            return True
        if env_value in {"0", "false", "no", "off"}:
            return False
        return sys.stderr.isatty()

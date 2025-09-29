from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List

from .logging import Logger


class _JSONLSink:
    def __init__(self, path: str):
        self.fh = open(path, "a", encoding="utf-8")

    def write(self, obj: Dict[str, Any]) -> None:
        self.fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.fh.flush()


class _SnapshotSink:
    def __init__(self, path: str, interval: float, max_batch: int, pretty: bool):
        self.path = path
        self.interval = interval
        self.max_batch = max_batch
        self.pretty = pretty
        self._buf: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._next = time.time() + self.interval

    def add(self, obj: Dict[str, Any]) -> None:
        should_flush = False
        with self._lock:
            self._buf.append(obj)
            if len(self._buf) >= self.max_batch or time.time() >= self._next:
                should_flush = True
        if should_flush:
            self.flush()

    def flush(self) -> None:
        with self._lock:
            data = self._buf[:]
            self._buf.clear()
            self._next = time.time() + self.interval
        indent = 2 if self.pretty else None
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=indent)
        os.replace(tmp, self.path)


class OutputWriters:
    def __init__(self, out_dir: str, cfg: Dict[str, Any], logger: Logger):
        self.out_dir = out_dir
        self.cfg = cfg
        self.logger = logger

    def jsonl(self, name: str) -> _JSONLSink:
        path = os.path.join(self.out_dir, name)
        return _JSONLSink(path)

    def snapshot(self, name: str) -> _SnapshotSink:
        ls = self.cfg.get("live_snapshot", {})
        interval = float(ls.get("interval_seconds", 5))
        max_batch = int(ls.get("max_batch", 500))
        pretty = bool(ls.get("pretty", True))
        path = os.path.join(self.out_dir, name)
        return _SnapshotSink(path, interval, max_batch, pretty)



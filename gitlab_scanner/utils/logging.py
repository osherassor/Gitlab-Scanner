from __future__ import annotations

import sys
import time
from typing import Any, Dict
import re


class Logger:
    def __init__(self, cfg: Dict[str, Any]):
        self.level = (cfg.get("level") or "info").lower()
        self.timestamps = bool(cfg.get("timestamps", True))
        self.banners = bool(cfg.get("banners", True))
        self.color_mode = cfg.get("color", "auto")
        self.use_color = False
        try:
            if self.color_mode is True or (str(self.color_mode).lower() == "auto" and sys.stdout.isatty()):
                self.use_color = True
        except Exception:
            self.use_color = False
        self._log_file = None
        lf = cfg.get("log_file")
        if lf:
            try:
                self._log_file = open(lf, "a", encoding="utf-8")
            except Exception:
                self._log_file = None
        self._silenced = False
        self._progress_len = 0

    def _should(self, want: str) -> bool:
        order = {"debug": 10, "info": 20, "warn": 30, "error": 40}
        return order.get(self.level, 20) <= order.get(want, 20)

    def _fmt(self, level: str, msg: str) -> str:
        ts = time.strftime("%Y-%m-%dT%H:%M:%S") if self.timestamps else ""
        prefix = f"[{ts}] {level.upper():5s} " if ts else f"{level.upper():5s} "
        return f"{prefix}{msg}"

    def _write(self, line: str) -> None:
        if self._silenced:
            return
        try:
            # If a progress line is active, end it with a clean newline first
            if self._progress_len > 0:
                sys.stdout.write("\r" + (" " * self._progress_len) + "\r\n")
                self._progress_len = 0
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
        except BrokenPipeError:
            self._silenced = True
            return
        if self._log_file:
            try:
                self._log_file.write(line + "\n")
                self._log_file.flush()
            except Exception:
                pass

    def _color(self, s: str, color: str | None) -> str:
        if not self.use_color or not color:
            return s
        colors = {
            "green": "\x1b[32m",
            "red": "\x1b[31m",
            "yellow": "\x1b[33m",
            "blue": "\x1b[34m",
            "magenta": "\x1b[35m",
            "cyan": "\x1b[36m",
        }
        reset = "\x1b[0m"
        return f"{colors.get(color, '')}{s}{reset}"

    def _fmt_tag(self, tag: str, msg: str, color: str | None) -> str:
        ts = time.strftime("%Y-%m-%dT%H:%M:%S") if self.timestamps else ""
        tag_txt = f"[{tag.upper()}]"
        if color:
            tag_txt = self._color(tag_txt, color)
        if ts:
            return f"[{ts}] {tag_txt} {msg}"
        return f"{tag_txt} {msg}"

    def debug(self, msg: str) -> None:
        if self._should("debug"):
            self._write(self._fmt("debug", msg))

    def info(self, msg: str) -> None:
        if self._should("info"):
            self._write(self._fmt("info", msg))

    def warn(self, msg: str) -> None:
        if self._should("warn"):
            self._write(self._fmt("warn", msg))

    def error(self, msg: str) -> None:
        if self._should("error"):
            self._write(self._fmt("error", msg))

    def banner(self, title: str) -> None:
        if not self.banners:
            return
        bar = "#" * 6
        msg = f"{bar} Starting {title} {bar}"
        colored = self._color(msg, "blue")
        self._write(self._fmt("info", colored))

    def tag(self, tag: str, msg: str, color: str | None = None) -> None:
        if self._should("info"):
            self._write(self._fmt_tag(tag, msg, color))

    def repo(self, msg: str) -> None:
        self.tag("REPO", msg, "green")

    def auth(self, msg: str) -> None:
        self.tag("AUTH", msg, "red")

    def user(self, msg: str) -> None:
        self.tag("USER", msg, "green")

    def ver(self, msg: str) -> None:
        self.tag("VER", msg, "green")

    def group(self, msg: str) -> None:
        self.tag("GROUP", msg, "green")

    # Progress line helpers (single-line dynamic updates)
    def progress(self, msg: str) -> None:
        if self._silenced:
            return
        try:
            padded = msg
            if self._progress_len > len(msg):
                padded += " " * (self._progress_len - len(msg))
            sys.stdout.write("\r" + padded)
            sys.stdout.flush()
            self._progress_len = len(msg)
        except BrokenPipeError:
            self._silenced = True
            return

    def progress_end(self) -> None:
        if self._silenced:
            return
        try:
            if self._progress_len > 0:
                sys.stdout.write("\r" + (" " * self._progress_len) + "\r\n")
                sys.stdout.flush()
                self._progress_len = 0
        except BrokenPipeError:
            self._silenced = True
            return

    def progress_colored(self, msg: str) -> None:
        if self._silenced:
            return
        if not self.use_color:
            self.progress(msg)
            return
        try:
            yellow = "\x1b[33m"
            red_bold = "\x1b[1;31m"
            reset = "\x1b[0m"
            # Color the entire text yellow and numbers red bold
            body = re.sub(r"(\d+)", lambda m: f"{red_bold}{m.group(1)}{yellow}", msg)
            colored = f"{yellow}{body}{reset}"
            pad_len = max(0, self._progress_len - len(msg))
            sys.stdout.write("\r" + colored + (" " * pad_len))
            sys.stdout.flush()
            self._progress_len = len(msg)
        except BrokenPipeError:
            self._silenced = True
            return

    def sum(self, msg: str) -> None:
        # Purple full-line summary with [SUM] prefix
        if not self._should("info"):
            return
        ts = time.strftime("%Y-%m-%dT%H:%M:%S") if self.timestamps else ""
        head = f"[{ts}] " if ts else ""
        text = f"[SUM] {msg}"
        if self.use_color:
            text = self._color(text, "magenta")
        self._write(head + text)



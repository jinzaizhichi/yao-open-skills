#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile


SCRIPT_INTERFACE = "cli"
SCRIPT_INTERFACE_REASON = "Removes private authoring evidence and local paths from the distributable skill archive."

ALLOWED_REPORTS = {
    "reports/review-studio.html",
    "reports/security_trust_report.md",
    "reports/skill-interpretation.html",
    "reports/skill-overview.html",
    "reports/positioning-skill-system-overview-2026-07-16/index.html",
}
ALLOWED_REPORT_PREFIXES: tuple[str, ...] = ()
TEXT_SUFFIXES = {".html", ".json", ".md", ".py", ".txt", ".yaml", ".yml"}
MAC_USER_ROOT = "/" + "Users/"
LOCAL_HREF = re.compile(
    r"href=([\"'])(?:(?:file://)?" + re.escape(MAC_USER_ROOT) + r"|[A-Za-z]:\\\\Users\\\\).*?\1",
    re.IGNORECASE,
)
LOCAL_PATH = re.compile(
    r"(?:file://)?" + re.escape(MAC_USER_ROOT) + r"[^<>\"'\r\n]+|[A-Za-z]:\\\\Users\\\\[^<>\"'\r\n]+",
    re.IGNORECASE,
)


def safe_entry(name: str) -> bool:
    if not name or "\x00" in name or "\\" in name:
        return False
    path = PurePosixPath(name)
    windows_drive = bool(path.parts and re.fullmatch(r"[A-Za-z]:", path.parts[0]))
    return not path.is_absolute() and not windows_drive and ".." not in path.parts and "" not in path.parts


def source_relative(name: str) -> str:
    parts = PurePosixPath(name).parts
    return "/".join(parts[1:]) if len(parts) > 1 else name


def should_keep(name: str) -> bool:
    relative = source_relative(name)
    parts = PurePosixPath(relative).parts
    if not parts:
        return False
    if any(part in {"__pycache__", ".pytest_cache"} for part in parts):
        return False
    if PurePosixPath(relative).suffix.lower() in {".pyc", ".pyo"}:
        return False
    if parts[0] in {"registry", "tests"}:
        return False
    if parts[0] != "reports":
        return True
    return relative in ALLOWED_REPORTS or any(relative.startswith(prefix) for prefix in ALLOWED_REPORT_PREFIXES)


def sanitized_text(name: str, payload: bytes) -> tuple[bytes, int]:
    if PurePosixPath(name).suffix.lower() not in TEXT_SUFFIXES:
        return payload, 0
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return payload, 0
    local_paths = len(LOCAL_PATH.findall(text))
    if not local_paths:
        return payload, 0
    if source_relative(name).startswith("reports/"):
        text = LOCAL_HREF.sub('href="#"', text)
        text = LOCAL_PATH.sub("[local-path-redacted]", text)
        return text.encode("utf-8"), local_paths
    raise ValueError(f"local absolute path found in runtime source: {name}")


def clone_info(info: zipfile.ZipInfo) -> zipfile.ZipInfo:
    cloned = zipfile.ZipInfo(info.filename, date_time=info.date_time)
    cloned.compress_type = zipfile.ZIP_DEFLATED
    cloned.comment = info.comment
    cloned.external_attr = info.external_attr
    cloned.create_system = info.create_system
    return cloned


def sanitize_archive(input_path: Path, output_path: Path) -> dict[str, int | str | bool]:
    if input_path.is_symlink():
        raise ValueError("input archive must not be a symbolic link")
    if output_path.is_symlink():
        raise ValueError("output archive must not be a symbolic link")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    kept = 0
    removed = 0
    redactions = 0
    input_bytes = input_path.stat().st_size
    try:
        with NamedTemporaryFile(dir=output_path.parent, prefix=".sanitized-package.", suffix=".zip", delete=False) as handle:
            temporary = Path(handle.name)
        with zipfile.ZipFile(input_path) as source:
            infos = source.infolist()
            if len(infos) > 5000:
                raise ValueError("archive contains too many entries")
            if sum(info.file_size for info in infos) > 200 * 1024 * 1024:
                raise ValueError("archive expands beyond the 200 MB review limit")
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as target:
                for info in infos:
                    if info.is_dir():
                        continue
                    if not safe_entry(info.filename):
                        raise ValueError(f"unsafe archive entry: {info.filename}")
                    if not should_keep(info.filename):
                        removed += 1
                        continue
                    payload, count = sanitized_text(info.filename, source.read(info))
                    redactions += count
                    target.writestr(clone_info(info), payload)
                    kept += 1
        temporary.replace(output_path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return {
        "ok": True,
        "input_bytes": input_bytes,
        "output_bytes": output_path.stat().st_size,
        "kept_entries": kept,
        "removed_entries": removed,
        "local_path_redactions": redactions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sanitize a yao-positioning-skill distribution archive.")
    parser.add_argument("input", type=Path, help="Raw ZIP produced by the cross-platform packager")
    parser.add_argument("--out", type=Path, required=True, help="Sanitized output ZIP; may equal input")
    args = parser.parse_args()
    try:
        report = sanitize_archive(args.input, args.out)
    except (FileNotFoundError, OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"cannot sanitize package: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

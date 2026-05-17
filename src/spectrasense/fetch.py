"""Download and verify public I/Q captures declared in captures.toml.

The TOML file is the single source of truth for what to fetch and what
parameters belong to each capture. This module just reads it and downloads.

Usage:
    python3 -m spectrasense.fetch                 # fetch all
    python3 -m spectrasense.fetch lte_b20_806mhz  # fetch one by key
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tomllib
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TOML = REPO_ROOT / "captures.toml"


@dataclass(frozen=True)
class Capture:
    key: str
    description: str
    data_url: str
    dest: Path
    dtype: str
    sample_rate_hz: int
    center_freq_hz: int
    meta_url: str | None
    meta_dest: Path | None
    sha512: str | None
    license: str | None


def load_captures(toml_path: Path) -> list[Capture]:
    with toml_path.open("rb") as f:
        doc = tomllib.load(f)
    out: list[Capture] = []
    for key, t in doc.items():
        if not isinstance(t, dict):
            continue
        out.append(
            Capture(
                key=key,
                description=t.get("description", ""),
                data_url=t["data_url"],
                dest=REPO_ROOT / t["dest"],
                dtype=t["dtype"],
                sample_rate_hz=int(t["sample_rate_hz"]),
                center_freq_hz=int(t["center_freq_hz"]),
                meta_url=t.get("meta_url"),
                meta_dest=(REPO_ROOT / t["meta_dest"]) if t.get("meta_dest") else None,
                sha512=t.get("sha512"),
                license=t.get("license"),
            )
        )
    return out


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)

    def hook(n: int, bs: int, total: int) -> None:
        read = n * bs
        if total > 0:
            pct = min(100.0, 100.0 * read / total)
            print(f"\r  {dest.name}: {read/1e6:7.1f} / {total/1e6:.1f} MB ({pct:5.1f}%)",
                  end="", flush=True)
        else:
            print(f"\r  {dest.name}: {read/1e6:7.1f} MB", end="", flush=True)

    urllib.request.urlretrieve(url, dest, reporthook=hook)
    print()


def _sha512(path: Path) -> str:
    h = hashlib.sha512()
    with path.open("rb") as f:
        for buf in iter(lambda: f.read(1 << 20), b""):
            h.update(buf)
    return h.hexdigest()


def fetch_one(capture: Capture) -> None:
    print(f"[{capture.key}] {capture.description}")
    if capture.meta_url and capture.meta_dest and not capture.meta_dest.exists():
        print(f"  fetching meta: {capture.meta_url}")
        _download(capture.meta_url, capture.meta_dest)

    if capture.dest.exists():
        print(f"  data already present: {capture.dest.relative_to(REPO_ROOT)}")
    else:
        print(f"  fetching data: {capture.data_url}")
        _download(capture.data_url, capture.dest)

    if capture.sha512:
        print("  verifying SHA-512 ...")
        actual = _sha512(capture.dest)
        if actual != capture.sha512:
            capture.dest.unlink(missing_ok=True)
            raise SystemExit(
                f"  SHA-512 mismatch for {capture.dest}:\n"
                f"    expected: {capture.sha512}\n"
                f"    actual:   {actual}\n"
                f"  file removed; re-run to retry"
            )
        print("  ok")
    else:
        print("  (no sha512 in captures.toml; skipping verification)")


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("keys", nargs="*", help="capture keys to fetch (default: all)")
    ap.add_argument("--toml", type=Path, default=DEFAULT_TOML)
    args = ap.parse_args(argv)

    captures = load_captures(args.toml)
    if args.keys:
        wanted = set(args.keys)
        unknown = wanted - {c.key for c in captures}
        if unknown:
            print(f"unknown capture keys: {sorted(unknown)}", file=sys.stderr)
            print(f"available: {[c.key for c in captures]}", file=sys.stderr)
            return 2
        captures = [c for c in captures if c.key in wanted]

    for c in captures:
        fetch_one(c)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

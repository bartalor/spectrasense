"""Download and verify public I/Q sample captures declared in samples.toml.

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
DEFAULT_TOML = REPO_ROOT / "samples.toml"


@dataclass(frozen=True)
class Sample:
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


def load_samples(toml_path: Path) -> list[Sample]:
    with toml_path.open("rb") as f:
        doc = tomllib.load(f)
    out: list[Sample] = []
    for key, t in doc.items():
        if not isinstance(t, dict):
            continue
        out.append(
            Sample(
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
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url) as resp, tmp.open("wb") as out:
        total = resp.headers.get("Content-Length")
        total_int = int(total) if total else None
        read = 0
        chunk = 1 << 20
        while True:
            buf = resp.read(chunk)
            if not buf:
                break
            out.write(buf)
            read += len(buf)
            if total_int:
                pct = 100.0 * read / total_int
                print(f"\r  {dest.name}: {read/1e6:7.1f} / {total_int/1e6:.1f} MB ({pct:5.1f}%)",
                      end="", flush=True)
            else:
                print(f"\r  {dest.name}: {read/1e6:7.1f} MB", end="", flush=True)
    print()
    tmp.replace(dest)


def _sha512(path: Path) -> str:
    h = hashlib.sha512()
    with path.open("rb") as f:
        for buf in iter(lambda: f.read(1 << 20), b""):
            h.update(buf)
    return h.hexdigest()


def fetch_one(sample: Sample) -> None:
    print(f"[{sample.key}] {sample.description}")
    if sample.meta_url and sample.meta_dest and not sample.meta_dest.exists():
        print(f"  fetching meta: {sample.meta_url}")
        _download(sample.meta_url, sample.meta_dest)

    if sample.dest.exists():
        print(f"  data already present: {sample.dest.relative_to(REPO_ROOT)}")
    else:
        print(f"  fetching data: {sample.data_url}")
        _download(sample.data_url, sample.dest)

    if sample.sha512:
        print("  verifying SHA-512 ...")
        actual = _sha512(sample.dest)
        if actual != sample.sha512:
            sample.dest.unlink(missing_ok=True)
            raise SystemExit(
                f"  SHA-512 mismatch for {sample.dest}:\n"
                f"    expected: {sample.sha512}\n"
                f"    actual:   {actual}\n"
                f"  file removed; re-run to retry"
            )
        print("  ok")
    else:
        print("  (no sha512 in samples.toml; skipping verification)")


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("keys", nargs="*", help="sample keys to fetch (default: all)")
    ap.add_argument("--toml", type=Path, default=DEFAULT_TOML)
    args = ap.parse_args(argv)

    samples = load_samples(args.toml)
    if args.keys:
        wanted = set(args.keys)
        unknown = wanted - {s.key for s in samples}
        if unknown:
            print(f"unknown sample keys: {sorted(unknown)}", file=sys.stderr)
            print(f"available: {[s.key for s in samples]}", file=sys.stderr)
            return 2
        samples = [s for s in samples if s.key in wanted]

    for s in samples:
        fetch_one(s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

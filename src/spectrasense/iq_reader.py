"""I/Q capture reader.

Supports two on-disk layouts:

  fc32 : interleaved float32  (I0 Q0 I1 Q1 ...), already in [-1, 1] convention
  sc16 : interleaved int16    (I0 Q0 I1 Q1 ...), full-scale int16 -> divide by 32768

Use open_capture() when you know the format and rate explicitly (raw .iq /
.bin files). Use open_sigmf() to load a .sigmf-data file with its sidecar
.sigmf-meta — dtype, sample rate, and center frequency come from the meta.

Large files are accessed via numpy.memmap so we never pull the whole capture
into RAM. read_chunks() yields complex64 arrays of a requested length.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Literal

import numpy as np

Dtype = Literal["fc32", "sc16"]

_BYTES_PER_SAMPLE: dict[Dtype, int] = {
    "fc32": 8,   # 2 * float32
    "sc16": 4,   # 2 * int16
}

# SigMF core:datatype string -> our Dtype.
_SIGMF_DTYPE: dict[str, Dtype] = {
    "ci16_le": "sc16",
    "cf32_le": "fc32",
}


@dataclass(frozen=True)
class IQCapture:
    """A handle to an I/Q capture on disk. Immutable; cheap to pass around."""

    path: Path
    dtype: Dtype
    sample_rate: float          # samples per second (Hz)
    center_freq: float          # RF center frequency (Hz)

    @property
    def num_samples(self) -> int:
        size = self.path.stat().st_size
        bps = _BYTES_PER_SAMPLE[self.dtype]
        if size % bps != 0:
            raise ValueError(
                f"{self.path}: size {size} not a multiple of "
                f"{bps} bytes/sample for dtype={self.dtype}"
            )
        return size // bps

    @property
    def duration_s(self) -> float:
        return self.num_samples / self.sample_rate


def open_capture(
    path: str | Path,
    dtype: Dtype,
    sample_rate: float,
    center_freq: float,
) -> IQCapture:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(p)
    if dtype not in _BYTES_PER_SAMPLE:
        raise ValueError(f"unsupported dtype {dtype!r}; expected one of {list(_BYTES_PER_SAMPLE)}")
    if sample_rate <= 0:
        raise ValueError(f"sample_rate must be positive, got {sample_rate}")
    return IQCapture(path=p, dtype=dtype, sample_rate=float(sample_rate), center_freq=float(center_freq))


def open_sigmf(path: str | Path) -> IQCapture:
    """Open a SigMF capture (.sigmf-data) using its .sigmf-meta sidecar.

    Reads dtype, sample rate, and center frequency from the meta JSON.
    """
    data_path = Path(path)
    meta_path = data_path.with_suffix(".sigmf-meta")
    if not data_path.is_file():
        raise FileNotFoundError(data_path)
    if not meta_path.is_file():
        raise FileNotFoundError(f"missing SigMF sidecar: {meta_path}")

    meta = json.loads(meta_path.read_text())
    g = meta["global"]
    caps = meta.get("captures", [{}])
    sigmf_dtype = g["core:datatype"]
    if sigmf_dtype not in _SIGMF_DTYPE:
        raise ValueError(f"unsupported SigMF datatype {sigmf_dtype!r}")
    return IQCapture(
        path=data_path,
        dtype=_SIGMF_DTYPE[sigmf_dtype],
        sample_rate=float(g["core:sample_rate"]),
        center_freq=float(caps[0].get("core:frequency", 0.0)),
    )


def read_chunks(
    cap: IQCapture,
    chunk_samples: int,
    start_sample: int = 0,
    max_samples: int | None = None,
) -> Iterator[np.ndarray]:
    """Yield successive complex64 chunks from the capture.

    chunk_samples is in *complex samples*, not bytes.
    """
    if chunk_samples <= 0:
        raise ValueError("chunk_samples must be positive")
    if start_sample < 0:
        raise ValueError("start_sample must be non-negative")

    total = cap.num_samples
    end = total if max_samples is None else min(total, start_sample + max_samples)
    if start_sample >= end:
        return

    if cap.dtype == "fc32":
        # memmap as float32, view I/Q pairs as complex64.
        raw = np.memmap(cap.path, dtype=np.float32, mode="r")
        cplx = raw.view(np.complex64)
        pos = start_sample
        while pos < end:
            stop = min(pos + chunk_samples, end)
            # copy out of memmap so the caller can mutate / GC frees mmap pages
            yield np.ascontiguousarray(cplx[pos:stop])
            pos = stop
        return

    if cap.dtype == "sc16":
        raw = np.memmap(cap.path, dtype=np.int16, mode="r")
        pos = start_sample
        scale = np.float32(1.0 / 32768.0)
        while pos < end:
            stop = min(pos + chunk_samples, end)
            # raw layout: I0 Q0 I1 Q1 ...  -> indices 2k and 2k+1
            sl = raw[2 * pos : 2 * stop]
            # reshape to (N, 2), cast, scale, combine
            iq = sl.reshape(-1, 2).astype(np.float32) * scale
            yield (iq[:, 0] + 1j * iq[:, 1]).astype(np.complex64, copy=False)
            pos = stop
        return

    raise AssertionError(f"unhandled dtype {cap.dtype!r}")  # pragma: no cover


def read_all(cap: IQCapture, max_samples: int | None = None) -> np.ndarray:
    """Convenience: read the whole capture (or first max_samples) as one array.

    Use sparingly on large files; prefer read_chunks().
    """
    pieces = list(read_chunks(cap, chunk_samples=1 << 20, max_samples=max_samples))
    if not pieces:
        return np.empty(0, dtype=np.complex64)
    return np.concatenate(pieces)

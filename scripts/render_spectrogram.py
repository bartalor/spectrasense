#!/usr/bin/env python3
"""Render a spectrogram PNG from a SigMF I/Q capture and print resolution numbers.

dtype, sample rate, and center frequency are read from the .sigmf-meta sidecar.

Usage:
  render_spectrogram.py PATH.sigmf-data \
      [--nperseg N] [--overlap N] [--window NAME] \
      [--max-seconds S] [--out PNG]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# allow running as `python3 scripts/render_spectrogram.py` without install
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from spectrasense import iq_reader, spectrogram  # noqa: E402


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", type=Path, help="path to a .sigmf-data file")
    ap.add_argument("--nperseg", type=int, default=2048)
    ap.add_argument("--overlap", type=int, default=1024)
    ap.add_argument("--window", default="hann")
    ap.add_argument("--max-seconds", type=float, default=1.0,
                    help="render at most this many seconds from the start of the capture")
    ap.add_argument("--out", type=Path, default=Path("artifacts/spectrogram.png"))
    return ap.parse_args()


def main() -> int:
    args = parse_args()

    cap = iq_reader.open_sigmf(args.path)
    params = spectrogram.SpectrogramParams(
        nperseg=args.nperseg, noverlap=args.overlap, window=args.window
    )

    n_to_read = int(args.max_seconds * cap.sample_rate)
    samples = iq_reader.read_all(cap, max_samples=n_to_read)

    spec = spectrogram.compute(
        samples=samples,
        sample_rate=cap.sample_rate,
        center_freq=cap.center_freq,
        params=params,
    )

    df_hz = params.freq_resolution_hz(cap.sample_rate)
    dt_s = params.time_resolution_s(cap.sample_rate)

    print(f"capture        : {cap.path}")
    print(f"  dtype        : {cap.dtype}")
    print(f"  sample_rate  : {cap.sample_rate:,.0f} Hz")
    print(f"  center_freq  : {cap.center_freq:,.0f} Hz")
    print(f"  total samples: {cap.num_samples:,}  ({cap.duration_s:.3f} s)")
    print(f"  samples used : {samples.size:,}  ({samples.size / cap.sample_rate:.3f} s)")
    print()
    print(f"spectrogram params")
    print(f"  window       : {params.window}")
    print(f"  nperseg      : {params.nperseg}")
    print(f"  noverlap     : {params.noverlap}  (hop = {params.hop})")
    print()
    print(f"resolution")
    print(f"  delta_f (bin spacing): {df_hz:>10,.2f} Hz  ({df_hz/1e3:.3f} kHz)")
    print(f"  delta_t (frame step) : {dt_s*1e6:>10,.2f} us")
    print(f"  output shape          : {spec.power_db.shape}  (freq, time)")
    print(f"  freq axis range       : {spec.freqs_hz[0]/1e6:.3f} .. {spec.freqs_hz[-1]/1e6:.3f} MHz")
    print(f"  time axis range       : {spec.times_s[0]*1e3:.3f} .. {spec.times_s[-1]*1e3:.3f} ms")
    print(f"  power range (dB)      : {spec.power_db.min():.1f} .. {spec.power_db.max():.1f}")

    args.out.parent.mkdir(parents=True, exist_ok=True)

    # Clamp display range to a sensible window around the peak; otherwise the
    # noise floor washes out the structure.
    vmax = float(spec.power_db.max())
    vmin = vmax - 60.0

    fig, ax = plt.subplots(figsize=(11, 6), dpi=130)
    im = ax.imshow(
        spec.power_db,
        aspect="auto",
        origin="lower",
        extent=(spec.times_s[0] * 1e3, spec.times_s[-1] * 1e3,
                spec.freqs_hz[0] / 1e6, spec.freqs_hz[-1] / 1e6),
        cmap="viridis",
        vmin=vmin, vmax=vmax,
        interpolation="nearest",
    )
    ax.set_xlabel("time (ms)")
    ax.set_ylabel("frequency (MHz)")
    ax.set_title(
        f"Spectrogram  |  fs={cap.sample_rate/1e6:g} Msps  fc={cap.center_freq/1e6:g} MHz\n"
        f"window={params.window}  nperseg={params.nperseg}  noverlap={params.noverlap}  "
        f"Δf={df_hz/1e3:.2f} kHz  Δt={dt_s*1e6:.2f} µs"
    )
    cb = fig.colorbar(im, ax=ax)
    cb.set_label("power (dB, relative)")
    fig.tight_layout()
    fig.savefig(args.out)
    plt.close(fig)

    print()
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

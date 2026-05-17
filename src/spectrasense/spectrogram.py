"""Sliding-window FFT (STFT) -> power-vs-frequency-over-time.

The point of this module is to be the explicit time/frequency resolution
substrate. Parameters are not defaulted opaquely; callers must pass them and
will be told what resolution they bought.

Built on scipy.signal.ShortTimeFFT (modern STFT API in SciPy >= 1.12). We
lean on the library for the FFT + windowing primitives; what's owned here is
the parameter contract and the dB / frequency-axis conventions.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import signal as sps


@dataclass(frozen=True)
class SpectrogramParams:
    nperseg: int            # FFT length in samples (== window length)
    noverlap: int           # overlapping samples between successive frames
    window: str             # any scipy.signal.get_window name (e.g. "hann", "blackman")

    def __post_init__(self) -> None:
        if self.nperseg <= 1:
            raise ValueError("nperseg must be > 1")
        if not (0 <= self.noverlap < self.nperseg):
            raise ValueError("noverlap must satisfy 0 <= noverlap < nperseg")

    @property
    def hop(self) -> int:
        return self.nperseg - self.noverlap

    def freq_resolution_hz(self, sample_rate: float) -> float:
        """Rayleigh frequency resolution (bin spacing). Hann widens main lobe
        to ~1.5x this; report bin spacing as the headline number."""
        return sample_rate / self.nperseg

    def time_resolution_s(self, sample_rate: float) -> float:
        """Time between successive STFT frames (hop / fs)."""
        return self.hop / sample_rate


@dataclass(frozen=True)
class Spectrogram:
    power_db: np.ndarray    # shape (n_freq, n_time), dBFS-style power
    freqs_hz: np.ndarray    # length n_freq, RF frequency in Hz (center_freq applied)
    times_s: np.ndarray     # length n_time, seconds from start of capture
    params: SpectrogramParams
    sample_rate: float
    center_freq: float


def compute(
    samples: np.ndarray,
    sample_rate: float,
    center_freq: float,
    params: SpectrogramParams,
) -> Spectrogram:
    """Compute an STFT-based spectrogram on a complex64 / complex128 array."""
    if samples.ndim != 1:
        raise ValueError("samples must be 1-D")
    if not np.iscomplexobj(samples):
        raise ValueError("samples must be complex (use complex64 for I/Q)")
    if samples.size < params.nperseg:
        raise ValueError(
            f"samples ({samples.size}) shorter than one FFT window "
            f"({params.nperseg}); need at least one full segment"
        )

    win = sps.get_window(params.window, params.nperseg, fftbins=True)
    SFT = sps.ShortTimeFFT(
        win=win,
        hop=params.hop,
        fs=sample_rate,
        fft_mode="centered",   # output freqs run -fs/2 .. +fs/2, zero in the middle
        scale_to="magnitude",
    )

    # extent="valid" -> only frames fully inside the input (no zero padding at edges)
    Sx = SFT.stft(samples, p0=0, p1=None, padding="zeros")

    # Keep only frames whose window fits entirely within the data.
    # ShortTimeFFT's p_min/p_max give the valid-frame range.
    p_min = SFT.p_min
    p_max = SFT.upper_border_begin(samples.size)[1]
    Sx = Sx[:, p_min:p_max]
    n_time = Sx.shape[1]

    # Power, then dB. Floor to avoid log(0); -120 dBFS is well below any real signal.
    power = (np.abs(Sx) ** 2).astype(np.float32, copy=False)
    floor = np.float32(1e-12)
    power_db = 10.0 * np.log10(np.maximum(power, floor))

    # Frequency axis: centered output is -fs/2..+fs/2 (excl), shift by center_freq.
    freqs_baseband = SFT.f                          # length nperseg, centered
    freqs_hz = freqs_baseband + center_freq

    # Time axis: frame k corresponds to sample index k*hop, taken at the *center*
    # of the window for a "where in time" interpretation.
    frame_indices = np.arange(p_min, p_min + n_time) * params.hop
    times_s = (frame_indices + params.nperseg / 2) / sample_rate

    return Spectrogram(
        power_db=power_db,
        freqs_hz=freqs_hz,
        times_s=times_s,
        params=params,
        sample_rate=sample_rate,
        center_freq=center_freq,
    )

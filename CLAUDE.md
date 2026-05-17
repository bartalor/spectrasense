# Project - spectrasense

## What this is
An LTE-aware spectrum monitor that operates on recorded I/Q capture files
(no radio hardware). It builds a time–frequency view of the spectrum, detects
and characterizes active signals, applies a light LTE-awareness check, and
flags anomalies against a baseline.

This is an interview-prep project. Its job is to cover the RF analysis /
RF measurements / spectrum monitoring side of a cellular + RF software role.
It deliberately does not cover cellular protocol signaling — a separate
project owns that. Keep it on the RF/spectrum side.

## Hard constraints
- No hardware. Input is always recorded I/Q files. Support at least
  complex float32 (fc32) and interleaved int16 (sc16); make the format
  and sample rate explicit inputs, never silently assumed.
- Python for everything (NumPy / SciPy for DSP). Bash for orchestration.
  SQLite via plain SQL, no ORM.
- Lean on libraries for the DSP primitives (FFT, windowing). The point is to
  design the detection/analysis pipeline and reason about RF, not to
  reimplement an FFT.

## Scope — core (must finish)
1. I/Q reader — load capture files, parse to complex samples, take sample
   rate + center frequency as explicit parameters. Handle large files in
   chunks; don't assume it fits in RAM.
2. Spectrogram engine — sliding-window FFT to power-vs-frequency-over-time.
   Configurable window size, overlap, window function. Core RF measurement
   layer.
3. Signal detection — adaptive noise-floor estimate, detect energy above it,
   group detections into signals. Per signal: center frequency, bandwidth,
   power, start/end time, duration.
4. Anomaly detection — build a baseline spectrum from a clean capture, then
   flag deviations: new emitter, signal at unexpected frequency,
   power/bandwidth outside baseline.
5. Storage — SQLite. Tables at minimum: captures, detections (per signal, per
   time window), anomalies. Real indexes (frequency, timestamp, capture_id).
   Hand-written analysis queries with joins.
6. Orchestration — Bash scripts: run the pipeline over a set of capture
   files, produce baseline, run a scenario, collect artifacts.

## Scope — LTE-awareness layer (expected, bounded)
7. Given a candidate LTE band / channel bandwidth, check whether a detected
   signal is consistent with an LTE carrier — occupied bandwidth roughly
   matching 1.4/3/5/10/15/20 MHz, expected spectral shape. A plausibility
   classifier, not a decoder.

## Scope — stretch only (project must stand without this)
8. PSS correlation — attempt to confirm a candidate is a real LTE cell by
   correlating against the three PSS sequences to recover timing / partial
   cell identity. Reach goal. If it fights back, cut it — the spectrum
   monitor core is the deliverable. Do not let this block 1–7, and never
   ship a broken sync routine in place of a working monitor.

## Demo (reproducible from files alone)
- Clean capture → establish baseline → clean result.
- Capture with an extra/unexpected signal → detect and characterize it,
  raise an anomaly, a SQL query surfaces it with its parameters.
- Use public I/Q sample sets; document the exact file, its sample rate and
  center frequency, in the repo.

## Design decisions to own (surface, don't bury behind defaults)
- FFT window size / overlap / window function and the resolution tradeoff.
- Noise-floor estimation method and why.
- What counts as a distinct signal vs noise; detection thresholds.
- Baseline representation and what counts as an anomaly.
- Schema + indexing; the analysis queries.

## Out of scope
- Live SDR / hardware capture.
- Protocol / NAS / RRC / signaling decode.
- Networking / path-monitoring features (different project).

## Sequencing
Confirm I/Q sample source first, then build: reader → spectrogram →
detection → anomaly + storage → LTE-awareness → (stretch) PSS. Get a thin
end-to-end path working early (reader → spectrogram → one detection →
SQLite) before deepening any stage. Each step should force a real design
decision, not follow a recipe.
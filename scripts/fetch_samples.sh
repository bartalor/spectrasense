#!/usr/bin/env bash
# Re-fetch the public I/Q sample captures that are too large to commit.
#
# Currently:
#   - Daniel Estevez's LTE B20 downlink @ 806 MHz, 30.72 Msps, sc16 (ci16_le),
#     ~117 MB. Vodafone PCI 380 primary (also 378, 379 on adjacent cells).
#     CC-BY 4.0. https://destevez.net/2022/04/lte-downlink-synchronization-signals/

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/data/lte"
BASE_URL="http://eala.destevez.net/~daniel/LTE"
NAME="LTE_downlink_806MHz_2022-04-09_30720ksps"

mkdir -p "$DEST"

if [[ ! -f "$DEST/$NAME.sigmf-meta" ]]; then
  echo "fetching $NAME.sigmf-meta ..."
  curl -fSL -o "$DEST/$NAME.sigmf-meta" "$BASE_URL/$NAME.sigmf-meta"
fi

if [[ ! -f "$DEST/$NAME.sigmf-data" ]]; then
  echo "fetching $NAME.sigmf-data (~117 MB) ..."
  curl -fSL -o "$DEST/$NAME.sigmf-data" "$BASE_URL/$NAME.sigmf-data"
fi

echo "verifying SHA-512 against metadata ..."
EXPECTED="$(python3 -c "import json,sys; print(json.load(open('$DEST/$NAME.sigmf-meta'))['global']['core:sha512'])")"
ACTUAL="$(sha512sum "$DEST/$NAME.sigmf-data" | awk '{print $1}')"
if [[ "$EXPECTED" != "$ACTUAL" ]]; then
  echo "SHA-512 mismatch!" >&2
  echo "  expected: $EXPECTED" >&2
  echo "  actual:   $ACTUAL" >&2
  exit 1
fi
echo "ok: $DEST/$NAME.sigmf-data"

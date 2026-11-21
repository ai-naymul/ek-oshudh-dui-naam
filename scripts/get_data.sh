#!/usr/bin/env bash
# Download the Bangladesh medicine registry (MIT licence) into data/raw/.
# Source: https://huggingface.co/datasets/ArnobBot/Medicine-Dataset-of-Bangladesh
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/raw
BASE="https://huggingface.co/datasets/ArnobBot/Medicine-Dataset-of-Bangladesh/resolve/main"
for f in medicine generic "drug class" indication manufacturer "dosage form"; do
  out="data/raw/${f// /_}.csv"
  if [ ! -s "$out" ]; then
    curl -sSfL -m 180 -o "$out" "$BASE/${f// /%20}.csv"
    echo "downloaded $out"
  else
    echo "exists $out"
  fi
done

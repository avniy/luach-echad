#!/bin/sh
# Brings the app to its newest version. Your searches and settings (the folder "data") are kept.
# (macOS / Linux.)
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 was not found. Install Python 3.10 or newer, then run this again."
  exit 1
fi
exec python3 update.py "$@"

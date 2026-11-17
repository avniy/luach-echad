#!/bin/sh
# Starts the app on this computer only and opens it in Chrome. Ctrl+C stops it.
# (macOS / Linux. Add --lan after "serve" to let invited devices on the home network in.)
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 was not found. Install Python 3.10 or newer, then run this again."
  exit 1
fi
exec python3 app.py serve --open "$@"

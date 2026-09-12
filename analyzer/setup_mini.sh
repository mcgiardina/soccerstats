#!/bin/bash
# One-shot setup for a spare Mac (e.g. the garage Mac mini) that shares this Dropbox folder.
# Run it ON THE MINI from this directory:  ./setup_mini.sh
# It keeps machine-specific things out of Dropbox, installs the analyzer, downloads the model
# weights, and installs a login agent that processes runs queued from the app.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

echo "1/5  Keeping the virtualenv and build folders out of Dropbox sync"
mkdir -p .venv ../node_modules ../dist cache
for d in .venv ../node_modules ../dist cache; do xattr -w com.dropbox.ignored 1 "$d"; done

echo "2/5  Python environment"
PY=$(command -v python3.13 || command -v python3.12 || command -v python3.11 || command -v python3.10 || true)
if [ -z "$PY" ]; then
  echo "     -> Python 3.10+ is required (yt-dlp dropped 3.9, and the system Python 3.9 then only gets 360p video)."
  echo "        Install it with:  brew install python@3.13   then re-run this script."
  exit 1
fi
if [ -x .venv/bin/python ] && ! .venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "     -> existing .venv uses $(.venv/bin/python --version); rebuilding it with $PY"
  rm -rf .venv
fi
if [ ! -x .venv/bin/python ]; then "$PY" -m venv .venv; fi
xattr -w com.dropbox.ignored 1 .venv    # a rebuilt .venv is a new folder: keep it out of Dropbox again
echo "     using $("$PY" --version)"
# yt-dlp prefers a JavaScript runtime for YouTube; Deno is small and the one it enables by default
if command -v brew >/dev/null && ! command -v deno >/dev/null; then brew install -q deno || true; fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt gdown
.venv/bin/pip install -q --upgrade yt-dlp   # a stale yt-dlp falls back to 360p streams

echo "3/5  Model weights (Roboflow football, ~420 MB, outside Dropbox)"
./get_weights.sh >/dev/null

echo "4/5  Secrets file outside Dropbox"
mkdir -p ~/.config/matchfilm
if [ ! -f ~/.config/matchfilm/.env ]; then
  cat > ~/.config/matchfilm/.env <<'ENV'
# Match Film analyzer secrets for THIS machine only (not synced).
SUPABASE_URL=https://lrovuuhgnevxrdxoeuxl.supabase.co
# Paste the service role key from Supabase → Project Settings → API. It lets the worker write results.
SUPABASE_SERVICE_KEY=
ENV
  echo "     -> edit ~/.config/matchfilm/.env and paste SUPABASE_SERVICE_KEY, then re-run this script"
  exit 0
fi
if ! grep -q "SUPABASE_SERVICE_KEY=." ~/.config/matchfilm/.env; then
  echo "     -> SUPABASE_SERVICE_KEY is still empty in ~/.config/matchfilm/.env"; exit 1
fi

echo "5/5  Login agent (runs at login, restarts if it dies)"
PLIST=~/Library/LaunchAgents/com.matchfilm.analyzer.plist
mkdir -p ~/Library/LaunchAgents ~/Library/Logs
sed -e "s#/Users/USERNAME/soccerstats/analyzer#$HERE#g" -e "s#/Users/USERNAME#$HOME#g" launchd/com.matchfilm.analyzer.plist > "$PLIST"
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "done. Log: ~/Library/Logs/matchfilm-analyzer.log"
echo "Keep this Mac awake: System Settings → Energy → Prevent automatic sleeping when the display is off."

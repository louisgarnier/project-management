#!/bin/bash
# Start the local transcription server (mlx-whisper on Apple Silicon)
# Run this from the project root: ./run_transcription.sh
# First run: deletes old venv (if any), creates fresh venv, installs dependencies (~5 min)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV="$SCRIPT_DIR/transcription/.venv"

# venv check: if mlx_whisper not importable, delete stale venv and rebuild
if [ ! -f "$VENV/bin/activate" ] || ! "$VENV/bin/python" -c "import mlx_whisper" 2>/dev/null; then
  echo "Setup required: deleting old venv (if any) and installing mlx-whisper..."
  rm -rf "$VENV"
  python3 -m venv "$VENV"
  source "$VENV/bin/activate"
  pip install -r transcription/requirements.txt
  echo "Setup complete."
  echo ""
else
  source "$VENV/bin/activate"
fi

echo "Starting Call Tracker local transcription server..."
echo "Server will be available at http://localhost:8001"
echo "Press Ctrl+C to stop."
echo ""

uvicorn transcription.main:app --host 0.0.0.0 --port 8001

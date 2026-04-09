#!/bin/bash
# Start the local transcription server (Whisper + pyannote)
# Run this from the project root: ./run_transcription.sh
# First run: automatically creates venv and installs dependencies (~10 min)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV="$SCRIPT_DIR/transcription/.venv"

# First-time setup: create venv and install dependencies
# Check for whisper package specifically — not just the activate file —
# to handle the case where venv was created but pip install was interrupted.
if [ ! -f "$VENV/bin/activate" ] || ! "$VENV/bin/python" -c "import whisper" 2>/dev/null; then
  echo "Setup required: installing dependencies (this takes ~10 minutes on first run)..."
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

#!/bin/bash
# Install a git pre-push hook that runs the fake-instrument tests and the offscreen GUI smoke tests (~1 min)
# and blocks the push if any fail.
# Bypass once with `git push --no-verify` (don't, for code that touches states.py or the instrument drivers).
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." >/dev/null 2>&1 && pwd )"
HOOK="$DIR/.git/hooks/pre-push"
cat > "$HOOK" <<'HOOKEOF'
#!/bin/bash
cd "$(git rev-parse --show-toplevel)" || exit 1
PY=.venv/bin/python; [ -x "$PY" ] || PY=python3
for t in tests/test_state_machine.py tests/test_gui_smoke.py; do
    echo "[pre-push] running $t ..."
    if ! out=$("$PY" -I "$t" 2>&1); then
        echo "$out" | grep -E "FAIL|RESULT fail|failure" | head -20
        echo "[pre-push] $t failed; push blocked."
        exit 1
    fi
    echo "$out" | grep -E "failure"
done
HOOKEOF
chmod +x "$HOOK"
echo "installed $HOOK"

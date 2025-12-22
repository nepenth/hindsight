#!/bin/bash
#
# Smoke test for hindsight-embed CLI with daemon mode
# Tests retain and recall operations via the background daemon
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$(cd "$SCRIPT_DIR/../hindsight-api" && pwd)"

echo "=== Hindsight Embed Smoke Test (Daemon Mode) ==="

# Check required environment
if [ -z "$HINDSIGHT_EMBED_LLM_API_KEY" ]; then
    echo "Error: HINDSIGHT_EMBED_LLM_API_KEY is required"
    exit 1
fi

# Use a unique bank ID for this test run
export HINDSIGHT_EMBED_BANK_ID="test-$$-$(date +%s)"
echo "Using bank ID: $HINDSIGHT_EMBED_BANK_ID"
echo "Script dir: $SCRIPT_DIR"
echo "API dir: $API_DIR"

# Stop any existing daemon
echo ""
echo "Stopping any existing daemon..."
uv run --project "$SCRIPT_DIR" python -c "from hindsight_embed.daemon_client import stop_daemon; stop_daemon()" 2>/dev/null || true
sleep 1

# Test 1: Retain (this should start the daemon)
echo ""
echo "Test 1: Retaining a memory (first call - daemon will start)..."
START_TIME=$(python3 -c "import time; print(time.time())")
OUTPUT=$(uv run --project "$SCRIPT_DIR" hindsight-embed retain "The user's favorite color is blue" 2>&1)
END_TIME=$(python3 -c "import time; print(time.time())")
DURATION=$(python3 -c "print(f'{$END_TIME - $START_TIME:.2f}')")
echo "$OUTPUT"
echo "Duration: ${DURATION}s"
if ! echo "$OUTPUT" | grep -q "Stored memory"; then
    echo "FAIL: Expected 'Stored memory' in output"
    exit 1
fi
echo "PASS: Memory retained successfully"

# Test 2: Recall (daemon already running - should be faster)
echo ""
echo "Test 2: Recalling memories (daemon already running)..."
START_TIME=$(python3 -c "import time; print(time.time())")
JSON_OUTPUT=$(uv run --project "$SCRIPT_DIR" hindsight-embed recall "What is the user's favorite color?" 2>/dev/null)
END_TIME=$(python3 -c "import time; print(time.time())")
DURATION=$(python3 -c "print(f'{$END_TIME - $START_TIME:.2f}')")
echo "$JSON_OUTPUT"
echo "Duration: ${DURATION}s"
if ! echo "$JSON_OUTPUT" | grep -qi "blue"; then
    echo "FAIL: Expected 'blue' in recall output"
    exit 1
fi
if ! echo "$JSON_OUTPUT" | python3 -c "import sys, json; json.load(sys.stdin)" 2>/dev/null; then
    echo "FAIL: Expected valid JSON output"
    exit 1
fi
echo "PASS: Memory recalled successfully (JSON format)"

# Test 3: Retain with context (daemon should still be running)
echo ""
echo "Test 3: Retaining memory with context..."
START_TIME=$(python3 -c "import time; print(time.time())")
OUTPUT=$(uv run --project "$SCRIPT_DIR" hindsight-embed retain "User prefers Python over JavaScript" --context work 2>&1)
END_TIME=$(python3 -c "import time; print(time.time())")
DURATION=$(python3 -c "print(f'{$END_TIME - $START_TIME:.2f}')")
echo "$OUTPUT"
echo "Duration: ${DURATION}s"
if ! echo "$OUTPUT" | grep -q "Stored memory"; then
    echo "FAIL: Expected 'Stored memory' in output"
    exit 1
fi
echo "PASS: Memory with context retained successfully"

# Test 4: Recall with budget
echo ""
echo "Test 4: Recalling with budget..."
START_TIME=$(python3 -c "import time; print(time.time())")
JSON_OUTPUT=$(uv run --project "$SCRIPT_DIR" hindsight-embed recall "programming preferences" --budget mid 2>/dev/null)
END_TIME=$(python3 -c "import time; print(time.time())")
DURATION=$(python3 -c "print(f'{$END_TIME - $START_TIME:.2f}')")
echo "$JSON_OUTPUT"
echo "Duration: ${DURATION}s"
if ! echo "$JSON_OUTPUT" | grep -qi "python"; then
    echo "FAIL: Expected 'Python' in recall output"
    exit 1
fi
if ! echo "$JSON_OUTPUT" | python3 -c "import sys, json; json.load(sys.stdin)" 2>/dev/null; then
    echo "FAIL: Expected valid JSON output"
    exit 1
fi
echo "PASS: Memory recalled with budget successfully (JSON format)"

# Test 5: Check daemon is running
echo ""
echo "Test 5: Verifying daemon is running..."
if curl -s http://127.0.0.1:8889/health | grep -q "healthy"; then
    echo "PASS: Daemon is running and healthy"
else
    echo "FAIL: Daemon is not running"
    exit 1
fi

# Cleanup: Stop daemon
echo ""
echo "Stopping daemon..."
uv run --project "$SCRIPT_DIR" python -c "from hindsight_embed.daemon_client import stop_daemon; stop_daemon()" 2>/dev/null || true

echo ""
echo "=== All tests passed! ==="

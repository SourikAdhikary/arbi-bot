#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

cleanup() {
    echo -e "\n${RED}Shutting down both bots...${NC}"
    kill "$PY_PID" 2>/dev/null || true
    kill "$RUST_PID" 2>/dev/null || true
    wait "$PY_PID" 2>/dev/null || true
    wait "$RUST_PID" 2>/dev/null || true
    echo -e "${GREEN}All processes stopped.${NC}"
}
trap cleanup EXIT INT TERM

echo -e "${CYAN}=== Polymarket Trading System ===${NC}"
echo ""

ARB_BINARY="arb-engine/target/release/arb-engine"
if [ ! -f "$ARB_BINARY" ]; then
    echo -e "${CYAN}Building Rust arb engine (release)...${NC}"
    (cd arb-engine && cargo build --release)
fi

if [ -f ".venv/bin/python3" ]; then
    PYTHON=".venv/bin/python3"
elif [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
else
    PYTHON="$(command -v python3 || command -v python)"
fi

if [ -z "$PYTHON" ]; then
    echo -e "${RED}Python not found. Install python3 or create a .venv first.${NC}"
    exit 1
fi

echo -e "${CYAN}Using Python: $PYTHON${NC}"

echo -e "${GREEN}[1/2] Starting Python strategy bot (endgame + value + correlation)...${NC}"
"$PYTHON" -m src.main &
PY_PID=$!

echo -e "${GREEN}[2/2] Starting Rust arb engine (WebSocket real-time arbitrage)...${NC}"
"$ARB_BINARY" &
RUST_PID=$!

echo ""
echo -e "${CYAN}Both bots running. Press Ctrl+C to stop.${NC}"
echo -e "  Python PID: $PY_PID"
echo -e "  Rust   PID: $RUST_PID"
echo ""

wait

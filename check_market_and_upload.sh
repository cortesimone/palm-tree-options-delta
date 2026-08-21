#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Production environment marker.
# This tells the Python config module to load .env.production (if it exists)
# and sets config.is_production = True.
# ---------------------------------------------------------------------------
export APP_ENV=production

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/market_check.log"
VENV_PYTHON="${SCRIPT_DIR}/.venv/bin/python3"

# Use venv python if available, otherwise fall back to system python
if [[ -x "${VENV_PYTHON}" ]]; then
    PYTHON="${VENV_PYTHON}"
else
    PYTHON="python3"
fi

# ---------------------------------------------------------------------------
# Load configuration via the Python config module (hierarchical loading).
# ---------------------------------------------------------------------------
read_config() {
    ${PYTHON} -c "
import sys, os
sys.path.insert(0, '${SCRIPT_DIR}')
from config import config
print(getattr(config, '${1}', ''))
"
}

ALPACA_API_KEY="$(read_config alpaca_api_key)"
ALPACA_API_SECRET="$(read_config alpaca_api_secret)"
ALPACA_DATA_URL="$(read_config trade_base)"
CRON_SYMBOL="$(read_config cron_symbol)"
CRON_TARGET_DELTA="$(read_config cron_target_delta)"
CRON_COUNT="$(read_config cron_count)"
CRON_USE_BOTH="$(read_config cron_use_both)"

log() {
    local timestamp
    timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "[${timestamp}] $*" >> "${LOG_FILE}"
}

if [[ -z "${ALPACA_API_KEY}" || -z "${ALPACA_API_SECRET}" ]]; then
    log "ERROR: Alpaca API credentials not configured"
    exit 1
fi

# Check market status via Alpaca API
API_RESPONSE="$(curl -s -o /dev/null -w "%{http_code}" \
    --request GET \
    --header "APCA-API-KEY-ID: ${ALPACA_API_KEY}" \
    --header "APCA-API-SECRET-KEY: ${ALPACA_API_SECRET}" \
    "${ALPACA_DATA_URL}/v3/clock" 2>>"${LOG_FILE}")" || true

if [[ "${API_RESPONSE}" != "200" ]]; then
    log "ERROR: Alpaca API returned HTTP ${API_RESPONSE} -- market check failed"
    exit 1
fi

MARKET_STATUS="$(curl -s \
    --request GET \
    --header "APCA-API-KEY-ID: ${ALPACA_API_KEY}" \
    --header "APCA-API-SECRET-KEY: ${ALPACA_API_SECRET}" \
    "${ALPACA_DATA_URL}/v3/clock" 2>>"${LOG_FILE}")" || true

IS_OPEN="$(echo "${MARKET_STATUS}" | ${PYTHON} -c "
import sys, json
data = json.load(sys.stdin)
phase = data['clocks'][0]['phase']
print(phase in ('pre', 'core', 'post'))
" 2>/dev/null)" || true

if [[ "${IS_OPEN}" != "True" ]]; then
    log "INFO: Market phase is ${IS_OPEN} -- skipping upload"
    exit 0
fi

log "INFO: Market is open -- running upload"
cd "${SCRIPT_DIR}"

# Build the upload command from config values
UPLOAD_CMD="${PYTHON} upload_to_sheet.py ${CRON_SYMBOL} ${CRON_TARGET_DELTA} ${CRON_COUNT}"
if [[ "${CRON_USE_BOTH}" == "True" || "${CRON_USE_BOTH}" == "true" || "${CRON_USE_BOTH}" == "1" ]]; then
    UPLOAD_CMD="${UPLOAD_CMD} --both"
fi

${UPLOAD_CMD} >> "${LOG_FILE}" 2>&1 && \
    log "INFO: Upload completed successfully" || \
    log "ERROR: Upload command failed"
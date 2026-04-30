#!/bin/bash

HEALTH_URL="${HEALTH_URL:-http://localhost/api/v1/health}"

response=$(curl -sf "$HEALTH_URL" 2>/dev/null)
if [ $? -eq 0 ]; then
    echo "OK: $response"
    if echo "$response" | grep -q '"status":"degraded"'; then
        exit 1
    fi
    exit 0
else
    echo "FAIL: Backend health check failed"
    exit 1
fi

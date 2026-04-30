#!/bin/bash

HEALTH_URL="${HEALTH_URL:-http://localhost/api/v1/health}"

response=$(curl -sf "$HEALTH_URL" 2>/dev/null)
if [ $? -eq 0 ]; then
    echo "OK: $response"
    exit 0
else
    echo "FAIL: Backend health check failed"
    exit 1
fi

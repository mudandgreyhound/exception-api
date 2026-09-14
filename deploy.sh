#!/usr/bin/env bash
set -euo pipefail
cd /opt/exception_api
git pull origin main
./venv/bin/pip install -q -r requirements.txt
sudo systemctl restart sale-monitor-api
sudo systemctl --no-pager status sale-monitor-api | head -5
echo "✅ deployed"

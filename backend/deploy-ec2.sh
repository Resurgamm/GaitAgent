#!/usr/bin/env bash
# Deploy ChildGait stub backend to EC2 (no model weights required).
# Usage:
#   ./deploy-ec2.sh ubuntu@<host>
#   PEM=../test.pem ./deploy-ec2.sh ubuntu@<ip>

set -euo pipefail
cd "$(dirname "$0")"

TARGET="${1:?usage: $0 user@host}"
PEM="${PEM:-$(cd .. && pwd)/test.pem}"
SSH=(ssh -i "$PEM" -o StrictHostKeyChecking=accept-new)
RSYNC=(rsync -avz --exclude '.venv' --exclude '__pycache__' -e "ssh -i $PEM -o StrictHostKeyChecking=accept-new")

echo ">>> uploading backend/ to $TARGET:~/backend/"
"${RSYNC[@]}" ./ "$TARGET:~/backend/"

echo ">>> installing + starting systemd service (ASSESS_MODE=stub, profiles.json)"
"${SSH[@]}" "$TARGET" 'bash -s' <<'EOF'
set -euo pipefail
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 python3-venv python3-pip
cd ~/backend
test -f profiles.json
test -f stub_synth.py
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -U pip
pip install -q -r requirements.txt

sudo tee /etc/systemd/system/childgait.service >/dev/null <<'UNIT'
[Unit]
Description=ChildGait API
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/backend
Environment=ASSESS_MODE=inference
Environment=MODEL_DIR=/home/ubuntu/ChildGait-Video
Environment=CHILDGAIT_ROOT=/home/ubuntu/ChildGait-Video
ExecStart=/home/ubuntu/backend/.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now childgait
sudo systemctl restart childgait
sleep 1
curl -s http://127.0.0.1:8000/health
echo
EOF

HOST="${TARGET#*@}"
echo ">>> public check: curl http://$HOST:8000/health"
curl -s -m 8 "http://$HOST:8000/health" || echo "(not reachable yet — open SG TCP 8000)"
echo
echo "Done. AppModule.API_BASE_URL should be http://$HOST:8000"

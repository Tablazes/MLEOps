#!/usr/bin/env bash
# VitaCall edge-deploy: gefinetuned Whisper-tiny naar Raspberry Pi Zero 2 W.
#
# Draait vanaf Windows (Git Bash). Stappen afzonderlijk aanroepbaar:
#   bash deploy_pi.sh keys     # eenmalig: ssh-key installeren (vraagt 1x wachtwoord)
#   bash deploy_pi.sh recon    # hardware/OS-check (arch, RAM, model)
#   bash deploy_pi.sh prep     # apt-deps + tijdelijke 1GB swap
#   bash deploy_pi.sh build    # whisper.cpp clonen (gepind) + compileren (-j2, ~15-30 min)
#   bash deploy_pi.sh model    # HF->ggml (Windows) + scp + quantize q5_0 (Pi)
#   bash deploy_pi.sh service  # systemd-unit installeren + starten
#   bash deploy_pi.sh test     # health + proef-transcriptie via HTTP
#   bash deploy_pi.sh alles    # prep t/m test
set -euo pipefail

PI_USER=${PI_USER:-pi}
PI_HOST=${PI_HOST:-192.168.68.124}
PI="$PI_USER@$PI_HOST"
# accept-new: eerste keer host-key automatisch accepteren (voorkomt
# "Host key verification failed" in niet-interactieve shells).
SSH_OPTS=(-o StrictHostKeyChecking=accept-new)
ssh() { command ssh "${SSH_OPTS[@]}" "$@"; }
scp() { command scp "${SSH_OPTS[@]}" "$@"; }
WHISPER_TAG=${WHISPER_TAG:-v1.7.5}   # gepind: convert-script en server-API bekend
MODEL_DIR=${MODEL_DIR:-models/whisper-tiny-vitacall-nl}
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

keys() {
    [ -f ~/.ssh/id_ed25519 ] || ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519
    # ssh-copy-id ontbreekt op Windows; handmatig appenden (vraagt 1x wachtwoord).
    ssh "$PI" "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys" \
        < ~/.ssh/id_ed25519.pub
    ssh -o BatchMode=yes "$PI" "echo key-login werkt"
}

recon() {
    ssh "$PI" 'cat /proc/device-tree/model; echo; uname -a; free -m; . /etc/os-release; echo "$PRETTY_NAME"'
    ARCH=$(ssh "$PI" uname -m)
    if [ "$ARCH" = "armv7l" ]; then
        echo "WAARSCHUWING: 32-bit OS ($ARCH). Herimage naar 64-bit Raspberry Pi OS Lite voor NEON-performance." >&2
    fi
}

prep() {
    ssh "$PI" 'sudo apt-get update -qq && sudo apt-get install -y -qq git cmake build-essential'
    # Tijdelijke swap: compileren op 512MB zonder OOM.
    ssh "$PI" 'sudo sed -i "s/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=1024/" /etc/dphys-swapfile && sudo dphys-swapfile setup && sudo dphys-swapfile swapon; free -m | grep -i swap'
}

build() {
    ssh "$PI" "[ -d whisper.cpp ] || git clone --depth 1 --branch $WHISPER_TAG https://github.com/ggml-org/whisper.cpp"
    ssh "$PI" 'cd whisper.cpp && cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j2 --config Release'
    ssh "$PI" 'ls -la whisper.cpp/build/bin/'
}

model() {
    # HF -> ggml f16 op Windows (puur Python, geen build nodig).
    if [ ! -d "$REPO_DIR/whisper.cpp" ]; then
        git clone --depth 1 --branch "$WHISPER_TAG" https://github.com/ggml-org/whisper.cpp "$REPO_DIR/whisper.cpp"
    fi
    if [ ! -d "$REPO_DIR/whisper.cpp/whisper-assets" ]; then
        # convert-script heeft de originele OpenAI-assets (mel-filters/tokenizer) nodig.
        git clone --depth 1 https://github.com/openai/whisper "$REPO_DIR/whisper.cpp/whisper-openai" || true
    fi
    cd "$REPO_DIR"
    python whisper.cpp/models/convert-h5-to-ggml.py "$MODEL_DIR" whisper.cpp/whisper-openai .
    ls -la ggml-model.bin
    scp ggml-model.bin "$PI:whisper.cpp/models/ggml-vitacall-nl-f16.bin"
    ssh "$PI" 'cd whisper.cpp && ./build/bin/quantize models/ggml-vitacall-nl-f16.bin models/ggml-vitacall-nl-q5_0.bin q5_0 && ls -la models/*.bin'
}

service() {
    # Systemd-unit inline (geen apart bestand): whisper-server met het
    # gequantiseerde gefinetunede model, memory-cap voor de 512MB Zero 2 W.
    ssh "$PI" "sudo tee /etc/systemd/system/vitacall-asr.service > /dev/null" <<EOF
[Unit]
Description=VitaCall edge-ASR (whisper.cpp server, gefinetuned Whisper-tiny NL)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$PI_USER
WorkingDirectory=/home/$PI_USER/whisper.cpp
ExecStart=/home/$PI_USER/whisper.cpp/build/bin/whisper-server \\
    -m /home/$PI_USER/whisper.cpp/models/ggml-vitacall-nl-q5_0.bin \\
    -l nl -t 4 --host 0.0.0.0 --port 8080
Restart=on-failure
RestartSec=5
MemoryMax=400M

[Install]
WantedBy=multi-user.target
EOF
    ssh "$PI" 'sudo systemctl daemon-reload && sudo systemctl enable --now vitacall-asr && sleep 3 && systemctl status vitacall-asr --no-pager -l | head -12'
    # Swap weer uit: alleen nodig tijdens compileren.
    ssh "$PI" 'sudo dphys-swapfile swapoff || true'
}

test() {
    curl -s -m 10 "http://$PI_HOST:8080/" >/dev/null && echo "server bereikbaar" || echo "server NIET bereikbaar"
    curl -s -m 120 "http://$PI_HOST:8080/inference" \
        -F file=@"$REPO_DIR/evidence/ref_audio/ref_00.wav" \
        -F response_format=json
    echo
}

alles() { prep; build; model; service; test; }

stap="${1:-alles}"
[ "$stap" = "key" ] && stap=keys   # veelgemaakte typo
"$stap"

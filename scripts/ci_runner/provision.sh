#!/bin/bash
# Run as root in a fresh, mount-free Ubuntu 24.04 ARM64 Lima base VM.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git jq build-essential python3 python3-venv \
  uidmap dbus-user-session slirp4netns fuse-overlayfs nftables unzip zip libicu74 libssl-dev zlib1g-dev
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
printf '%s\n' 'deb [arch=arm64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable' > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli docker-ce-rootless-extras
systemctl disable --now docker.service docker.socket
# Ubuntu's AppArmor userns restriction otherwise prevents rootless Docker.
# Only the isolated guest changes; runner still has no sudo/capabilities.
printf 'kernel.apparmor_restrict_unprivileged_userns=0\n' > /etc/sysctl.d/90-ci-rootless.conf
sysctl --system
useradd --create-home --shell /bin/bash --uid 1100 runner
loginctl enable-linger runner
mkdir -p /opt/hostedtoolcache /opt/actions-runner
chown runner:runner /opt/hostedtoolcache /opt/actions-runner
curl -fsSL https://nodejs.org/dist/v20.20.1/node-v20.20.1-linux-arm64.tar.xz -o /tmp/node.tar.xz
curl -fsSL https://nodejs.org/dist/v20.20.1/SHASUMS256.txt -o /tmp/node-shasums
(cd /tmp; grep ' node-v20.20.1-linux-arm64.tar.xz$' node-shasums | sed 's/node-v20.20.1-linux-arm64.tar.xz/node.tar.xz/' | sha256sum -c -)
tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1
curl -fsSL https://github.com/actions/runner/releases/download/v2.338.0/actions-runner-linux-arm64-2.338.0.tar.gz -o /tmp/runner.tar.gz
echo '628b4a7258487b80c1d3c221095a7ded349f5ae0175fd3dfab708d07428f041b  /tmp/runner.tar.gz' | sha256sum -c -
tar -xzf /tmp/runner.tar.gz -C /opt/actions-runner
/opt/actions-runner/bin/installdependencies.sh
chown -R runner:runner /opt/actions-runner
# Same OS dependency installer as the workflow, provisioned with root only here.
npx --yes playwright@1.58.2 install-deps chromium
runuser -u runner -- env HOME=/home/runner XDG_RUNTIME_DIR=/run/user/1100 dockerd-rootless-setuptool.sh install
runuser -u runner -- env HOME=/home/runner XDG_RUNTIME_DIR=/run/user/1100 systemctl --user enable docker
cat > /etc/systemd/system/db-ci-runner.service <<'UNIT'
[Unit]
Description=Disposable DieselBridge GitHub Actions worker
After=network-online.target nftables.service user@1100.service
Requires=nftables.service
[Service]
User=runner
Group=runner
WorkingDirectory=/opt/actions-runner
Environment=HOME=/home/runner
Environment=XDG_RUNTIME_DIR=/run/user/1100
Environment=DOCKER_HOST=unix:///run/user/1100/docker.sock
Environment=RUNNER_TOOL_CACHE=/opt/hostedtoolcache
ExecStart=/opt/actions-runner/run.sh
KillMode=control-group
TimeoutStopSec=20
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
# Not enabled: the supervisor starts it only after configuring a fresh clone.
rm -f /tmp/node.tar.xz /tmp/runner.tar.gz /tmp/node-shasums

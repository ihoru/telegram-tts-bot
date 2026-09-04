#!/usr/bin/env bash
set -euo pipefail

mode=${1:?Expected check or deploy}
[[ "$mode" == check || "$mode" == deploy ]]
[[ "$DEPLOY_HOST" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ ]]
[[ "$DEPLOY_USER" =~ ^[a-z_][a-z0-9_-]*$ ]]
[[ "$DEPLOY_PORT" =~ ^[0-9]{1,5}$ ]]
test -n "$DEPLOY_SSH_KEY"
test -n "$DEPLOY_KNOWN_HOSTS"

ssh_dir=$(mktemp -d)
trap 'rm -rf "$ssh_dir"' EXIT
chmod 700 "$ssh_dir"
printf '%s\n' "$DEPLOY_SSH_KEY" > "$ssh_dir/key"
printf '%s\n' "$DEPLOY_KNOWN_HOSTS" > "$ssh_dir/known_hosts"
chmod 600 "$ssh_dir/key" "$ssh_dir/known_hosts"
unset DEPLOY_SSH_KEY DEPLOY_KNOWN_HOSTS

ssh_args=(-F /dev/null -T -i "$ssh_dir/key" -p "$DEPLOY_PORT"
  -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes
  -o UserKnownHostsFile="$ssh_dir/known_hosts"
  -o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=4)

if [[ "$mode" == check ]]; then
  status=0
  output=$(ssh "${ssh_args[@]}" "$DEPLOY_USER@$DEPLOY_HOST" check 2>&1) || status=$?
  if [[ "$status" != 1 || "$output" != 'Expected: deploy sha256:<64 lowercase hex characters>' ]]; then
    echo "Restricted SSH access check failed; verify key, host pinning, and forced command." >&2
    exit 1
  fi
  echo "Restricted SSH access verified; no container changes requested."
else
  [[ "$IMAGE_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]]
  ssh "${ssh_args[@]}" "$DEPLOY_USER@$DEPLOY_HOST" "deploy $IMAGE_DIGEST"
fi

#!/bin/bash
# Executed as root by AWS Systems Manager.
set -Eeuo pipefail
IMAGE_URI="${1:?Image URI required}"
APP_VERSION="${2:?Release version required}"
REGISTRY=732529884848.dkr.ecr.us-east-1.amazonaws.com
[[ "$IMAGE_URI" == "$REGISTRY/deployiqsample:"* ]] || exit 2
exec 9>"${DEPLOYIQ_LOCK_FILE:-/var/lock/deployiq-deploy.lock}"
flock -n 9 || { echo 'Another deployment is active'; exit 1; }

candidate=deployiq-candidate
backup=deployiq-previous
swapping=false
had_previous=false
cleanup() {
  result=$?
  trap - EXIT
  docker rm -f "$candidate" >/dev/null 2>&1 || true
  if (( result != 0 )) && [[ "$swapping" == true ]]; then
    echo 'Deployment failed; restoring previous container'
    docker logs --tail 50 deployiq-sample || true
    docker rm -f deployiq-sample >/dev/null 2>&1 || true
    if [[ "$had_previous" == true ]]; then
      docker rename "$backup" deployiq-sample
      docker start deployiq-sample
    fi
  fi
  docker logout "$REGISTRY" >/dev/null 2>&1 || true
  exit "$result"
}
trap cleanup EXIT

healthy() {
  for attempt in {1..30}; do
    if curl --fail --silent --max-time 2 "$1/health"; then
      return 0
    fi
    sleep 2
  done
  return 1
}

aws ecr get-login-password --region us-east-1 |
  docker login --username AWS --password-stdin "$REGISTRY"
docker pull "$IMAGE_URI"
docker rm -f "$candidate" >/dev/null 2>&1 || true
docker run -d --name "$candidate" \
  --log-opt max-size=10m --log-opt max-file=3 \
  -p 127.0.0.1:8001:8000 -e "APP_VERSION=$APP_VERSION" "$IMAGE_URI"
healthy http://127.0.0.1:8001
# Verify the new release before replacing the current service.
docker rm -f "$candidate"
docker rm -f "$backup" >/dev/null 2>&1 || true
if docker inspect deployiq-sample >/dev/null 2>&1; then
  docker rename deployiq-sample "$backup"
  had_previous=true
fi
swapping=true
if [[ "$had_previous" == true ]]; then
  docker stop "$backup"
fi
docker run -d --name deployiq-sample --restart unless-stopped \
  --log-opt max-size=10m --log-opt max-file=3 \
  -p 80:8000 -e "APP_VERSION=$APP_VERSION" "$IMAGE_URI"
healthy http://127.0.0.1
swapping=false
docker rm -f "$backup" >/dev/null 2>&1 || true
echo "Deployed $APP_VERSION"

#!/usr/bin/env bash
# build.sh — builda a imagem única frr-larp:latest (D4).
# Sem sudo: o grupo docker dá acesso ao daemon.
set -euo pipefail
cd "$(dirname "$0")/.."   # raiz do repo

if [ -f scripts/_env.sh ]; then
  # shellcheck disable=SC1091
  source scripts/_env.sh
else
  export DOCKER_CONTEXT=default
  export DOCKER_HOST="${DOCKER_HOST:-unix:///var/run/docker.sock}"
fi

# copia o larpd de src/ para docker/ (a cópia é gitignorada — docker/larpd.py)
cp src/larpd.py docker/larpd.py

docker build -t frr-larp:latest docker/

echo "imagem frr-larp:latest buildada"

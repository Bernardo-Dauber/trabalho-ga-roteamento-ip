#!/usr/bin/env bash
# _env.sh — ambiente comum a todos os scripts (sem sudo).
# Uso: source scripts/_env.sh  (sempre a partir da raiz do repo)
#
# - Fixa o contexto Docker correto (default = daemon real em /var/run/docker.sock).
#   O contexto 'desktop-linux' aponta para um socket morto e faz qualquer
#   comando docker falhar com "Cannot connect to the Docker daemon".
# - Adiciona o binário do Containerlab (modo usuário) ao PATH.
# - Preflight: se docker não responde, orienta (não tenta sudo -n nem trava).
set -euo pipefail

export DOCKER_CONTEXT="${DOCKER_CONTEXT:-default}"
export DOCKER_HOST="${DOCKER_HOST:-unix:///var/run/docker.sock}"
export PATH="$HOME/containerlab/bin:$PATH"

if ! docker info >/dev/null 2>&1; then
  echo "[_env] ERRO: docker não responde no contexto '$DOCKER_CONTEXT'." >&2
  echo "[_env]   Contexto errado?  rode: docker context use default" >&2
  echo "[_env]   Daemon parado?    inicie: systemctl start docker  (ou dockerd)" >&2
  echo "[_env]   Não tente sudo -n; corrija o contexto/daemon e repita." >&2
  exit 2
fi

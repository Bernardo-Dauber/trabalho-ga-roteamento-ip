#!/usr/bin/env bash
# _env.sh — ambiente comum a todos os scripts (sem sudo).
# Uso: source scripts/_env.sh  (sempre a partir da raiz do repo)
#
# - Fixa o contexto Docker no dockerd do SISTEMA (contexto 'default',
#   /var/run/docker.sock). Não é preferência, é requisito do Containerlab: ele
#   cria veth/bridge e mexe na netns dos containers a partir do host. O daemon do
#   Docker Desktop roda dentro de uma VM LinuxKit (kernel *-linuxkit), onde essas
#   netns/bridges não existem para o processo do host — o deploy ali falha com
#   "namespace path not available for container" ou, pior, termina sem erro e
#   deixa os nós SEM nenhuma interface do lab (verificado empiricamente neste
#   host). Por isso `docker context use desktop-linux` não é uma opção.
# - Imprime qual daemon está em uso: há dois daemons vivos neste host e um
#   `docker ps` no contexto errado (desktop-linux, que o Docker Desktop reativa
#   sozinho ao iniciar) mostra vazio, passando a impressão de que o lab não subiu.
# - Adiciona o binário do Containerlab (modo usuário) ao PATH.
# - Preflight: se docker não responde, orienta (não tenta sudo -n nem trava).
set -euo pipefail

export DOCKER_CONTEXT="${DOCKER_CONTEXT:-default}"
export DOCKER_HOST="${DOCKER_HOST:-unix:///var/run/docker.sock}"
export PATH="$HOME/containerlab/bin:$PATH"

echo "[_env] daemon: contexto '$DOCKER_CONTEXT' ($DOCKER_HOST)"

# contexto que o CLI usaria sem override — só para avisar quando divergem
CLI_CTX=$(env -u DOCKER_CONTEXT -u DOCKER_HOST docker context show 2>/dev/null || echo "?")
if [ "$CLI_CTX" != "$DOCKER_CONTEXT" ]; then
  echo "[_env]   nota: o contexto do CLI é '$CLI_CTX' — 'docker ps' sem override"
  echo "[_env]         mostra OUTRO daemon (o lab não aparece lá). Para ver:"
  echo "[_env]         DOCKER_CONTEXT=$DOCKER_CONTEXT docker ps"
fi

if ! docker info >/dev/null 2>&1; then
  echo "[_env] ERRO: docker não responde no contexto '$DOCKER_CONTEXT'." >&2
  echo "[_env]   Daemon parado?  inicie: systemctl start docker  (ou dockerd)" >&2
  echo "[_env]   Socket errado?  confira 'docker context ls' (o lab exige 'default')" >&2
  echo "[_env]   Não tente sudo -n; corrija o contexto/daemon e repita." >&2
  exit 2
fi

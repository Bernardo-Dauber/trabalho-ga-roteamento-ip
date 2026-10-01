#!/usr/bin/env bash
# inspect.sh [rip|ospf|larp] [flags do containerlab] — inspect sem exportar MODE.
#
# O manifesto referencia ${MODE} nos binds (configs/${MODE}/R<n>). O Containerlab
# expande essa variável a partir do AMBIENTE do processo e NÃO lê .env do repo:
# sem MODE exportado, até um `inspect` (que não deploya nada) aborta com
#   Failed to verify bind path: stat .../configs/$MODE/R1: no such file or directory
# (verificado na 0.79.0). run.sh/scenario.sh exportam MODE por isso.
#
# Aqui o modo, quando não vem como argumento, é inferido do bind do R1 que já
# está no ar — ou seja, `scripts/inspect.sh` funciona com o modo que estiver
# rodando. Sem lab no ar, cai em 'rip' só para o parse não quebrar.
set -euo pipefail
cd "$(dirname "$0")/.."   # raiz do repo
# shellcheck disable=SC1091
source scripts/_env.sh

case "${1:-}" in
  rip|ospf|larp) MODE="$1"; shift ;;
  "")            MODE="" ;;
  *)             echo "uso: inspect.sh [rip|ospf|larp] [flags do containerlab]" >&2; exit 1 ;;
esac

if [ -z "$MODE" ]; then
  src=$(docker inspect clab-routing-lab-R1 \
    --format '{{range .Mounts}}{{if eq .Destination "/etc/frr"}}{{.Source}}{{end}}{{end}}' \
    2>/dev/null || true)
  if [[ "$src" =~ /configs/(rip|ospf|larp)/ ]]; then
    MODE="${BASH_REMATCH[1]}"
    echo "[inspect] MODE inferido do lab no ar: $MODE"
  else
    MODE=rip
    echo "[inspect] nenhum lab no ar — usando MODE=$MODE só para expandir o manifesto"
  fi
fi

MODE=$MODE containerlab inspect -t topology.clab.yml "$@"

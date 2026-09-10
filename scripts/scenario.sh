#!/usr/bin/env bash
# scenario.sh rip|ospf|larp — roteiro cronometrado, ÚNICA via de execução (D12).
#
# Transcreve o §9.4 do relatório com as adaptações desta spec/plano:
#   - FASE parametrizável (default 60 → 300 s totais); eventos em FASE,
#     2*FASE, 3*FASE, 4*FASE; o coletor roda 5*FASE s. Fases curtas (ex. 15)
#     existem só para o loop de desenvolvimento; apenas FASE=60 alimenta
#     figs/ e os resultados commitados (D12).
#   - sem sudo (source scripts/_env.sh); down()/up() via docker exec
#     (a linha containerlab-inspect do relatório era no-op — removida).
#   - degradação de R1-R5 em t=240 usa --rate em kbit (10000 = 10 mbit;
#     o CLI do containerlab 0.79.0 não aceita "10mbit", D3).
#   - teardown + deploy + impairments + (larpd) + coleta, tudo aqui:
#     nunca rodar comandos soltos do §10 enquanto se coleta (§13).
set -euo pipefail
cd "$(dirname "$0")/.."   # raiz do repo
# shellcheck disable=SC1091
source scripts/_env.sh

MODE=${1:-}
if [[ ! "$MODE" =~ ^(rip|ospf|larp)$ ]]; then
  echo "uso: scenario.sh rip|ospf|larp [FASE=<segundos>]" >&2
  exit 1
fi
# FASE pode vir como env (FASE=15 bash scripts/scenario.sh rip) ou como 2º arg
FASE=${FASE:-60}
if [ $# -ge 2 ] && [[ "$2" =~ ^FASE=[0-9]+$ ]]; then
  FASE="${2#FASE=}"
fi
if ! [[ "$FASE" =~ ^[0-9]+$ ]] || [ "$FASE" -lt 5 ]; then
  echo "[scenario] FASE deve ser inteiro >= 5 (default 60)" >&2
  exit 1
fi
TOTAL=$((FASE * 5))

# resultados do modo sempre limpos: cada execução é autocontida (D17)
rm -rf "results/$MODE"

echo "[scenario] $MODE — FASE=${FASE}s, coleta de ${TOTAL}s"
bash scripts/run.sh "$MODE"

# coletor roda em paralelo aos eventos; t=0 = fim do deploy
python3 src/collect.py "$MODE" "$TOTAL" &
COLLECTOR=$!
trap 'kill $COLLECTOR 2>/dev/null || true' EXIT

down() { docker exec "clab-routing-lab-$1" ip link set "$2" down >/dev/null; }
up()   { docker exec "clab-routing-lab-$1" ip link set "$2" up   >/dev/null; }

sleep "$FASE" ; echo "t=$FASE        derrubando satélite R1-R4 (eth3 R1)"              ; down R1 eth3
sleep "$FASE" ; echo "t=$((2*FASE))  restaurando satélite R1-R4"                        ; up   R1 eth3
sleep "$FASE" ; echo "t=$((3*FASE))  derrubando backbone R2-R3 (eth2 R2)"              ; down R2 eth2
sleep "$FASE" ; echo "t=$((4*FASE))  restaurando backbone + degradando R1-R5 p/ 200ms"
                up R2 eth2
                containerlab tools netem set -n clab-routing-lab-R1 -i eth2 \
                  --delay 200ms --rate 10000
sleep "$FASE" ; echo "t=$TOTAL      fim da coleta"

wait "$COLLECTOR" || true
trap - EXIT
echo "[scenario] $MODE concluído — resultados em results/$MODE/"
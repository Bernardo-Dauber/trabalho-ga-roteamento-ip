#!/usr/bin/env bash
# run.sh rip|ospf|larp — sobe o lab por modo (sem sudo).
# Adaptação do §9.2 do relatório para operar sem sudo (grupo docker).
set -euo pipefail
cd "$(dirname "$0")/.."   # raiz do repo
# shellcheck disable=SC1091
source scripts/_env.sh

MODE=${1:-}
if [[ ! "$MODE" =~ ^(rip|ospf|larp)$ ]]; then
  echo "uso: run.sh rip|ospf|larp" >&2
  exit 1
fi

# teardown prévio (não falha se não houver lab). MODE no ambiente para o
# Containerlab expandir ${MODE} no manifesto (v0.79.0: expande no deploy,
# mas o inspect falha sem a env).
MODE=$MODE containerlab destroy -t topology.clab.yml --cleanup 2>/dev/null || true

# sempre regenera configs antes de subir — evita drift (D3)
python3 src/gen_configs.py

# deploy com o modo selecionado (o Containerlab expande ${MODE} nos binds)
MODE=$MODE containerlab deploy -t topology.clab.yml
sleep 5

# aplica netem (banda/latência) nos enlaces.
# M1: não-fatal — se falhar (ex.: caps/AppArmor), avisa e segue.
# Tornar fatal a partir do M2; netem validado à parte.
if bash scripts/impair.sh; then
  echo "impairments aplicados (netem)"
else
  echo "[aviso] impair.sh falhou — impairments NÃO aplicados. Não bloqueia o M1." >&2
fi

# Subida do larpd somente depois que o zebra aplicou todos os enlaces /30.
if [ "$MODE" = "larp" ]; then
  for i in 1 2 3 4 5; do
    node="clab-routing-lab-R$i"
    expected=$(python3 -c \
      'from topology import links_of; import sys; print(len(links_of(sys.argv[1])))' \
      "R$i")
    deadline=$((SECONDS + 90))
    while :; do
      if addresses=$(docker exec "$node" ip -j -4 addr show 2>/dev/null); then
        count=$(printf '%s' "$addresses" | python3 -c \
          'import json, sys; data=json.load(sys.stdin); print(sum(1 for i in data for a in i.get("addr_info", []) if a.get("family") == "inet" and int(a.get("prefixlen", -1)) == 30))')
      else
        count=0
      fi
      if [ "$count" -ge "$expected" ]; then
        break
      fi
      if [ "$SECONDS" -ge "$deadline" ]; then
        echo "[erro] $node não ficou pronto: $count/$expected enlaces /30" >&2
        exit 1
      fi
      sleep 1
    done
    echo "$node pronto: $count/$expected enlaces /30"
    docker exec -d "$node" \
      sh -c "LARP_RID=10.255.0.$i larpd > /var/log/larpd.log 2>&1"
  done
fi

echo "modo $MODE ativo"
MODE=$MODE containerlab inspect -t topology.clab.yml

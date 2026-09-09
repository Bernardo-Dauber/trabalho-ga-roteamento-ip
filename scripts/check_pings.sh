#!/usr/bin/env bash
# check_pings.sh — pings de vizinhança (R–R e R–host) derivados de topology.py.
# Ancestral mode-agnóstico do verify.sh (que é de M2/M3, D14).
# Uso: rodar com o lab de pé (bash scripts/run.sh <modo> primeiro).
set -uo pipefail
cd "$(dirname "$0")/.."   # raiz do repo
# shellcheck disable=SC1091
source scripts/_env.sh

PREFIX=clab-routing-lab
FAILED=0
TOTAL=0

# gera as linhas "container|ip|descricao" a partir de topology.py
mapfile -t PAIRS < <(python3 - <<'PY'
import sys
sys.path.insert(0, ".")
from topology import ROUTERS, LINKS, LANS, addr_of

rows = []
# R–R: para cada enlace (a,b), ping nas duas direções (IP via addr_of)
for (a, b) in LINKS:
    ip_b = addr_of(b, (a, b))   # ex.: 10.0.12.2 (lado b)
    ip_a = addr_of(a, (a, b))   # ex.: 10.0.12.1 (lado a)
    rows.append((f"clab-routing-lab-{a}", ip_b.split("/")[0], f"R->R {a}->{b}"))
    rows.append((f"clab-routing-lab-{b}", ip_a.split("/")[0], f"R->R {b}->{a}"))
# R–host: roteador -> host  e  host -> gateway
for r in ROUTERS:
    k = r[1:]
    rows.append((f"clab-routing-lab-{r}", f"192.168.{k}.10", f"R->host {r}->h{k}"))
    rows.append((f"clab-routing-lab-h{k}", f"192.168.{k}.1",  f"host->gw h{k}->{r}"))

for (c, ip, desc) in rows:
    print(f"{c}|{ip}|{desc}")
PY
)

for line in "${PAIRS[@]}"; do
  IFS='|' read -r c ip desc <<< "$line"
  TOTAL=$((TOTAL+1))
  if docker exec "$c" ping -c1 -W2 "$ip" >/dev/null 2>&1; then
    echo "PASS  $desc ($c -> $ip)"
  else
    echo "FAIL  $desc ($c -> $ip)"
    FAILED=$((FAILED+1))
  fi
done

echo "------------------------------"
echo "resumo: $((TOTAL-FAILED))/$TOTAL PASS"
if [ "$FAILED" -ne 0 ]; then
  echo "FALHOU ($FAILED pares)" >&2
  exit 1
fi
echo "TODOS OS PINGS DE VIZINHANÇA OK"

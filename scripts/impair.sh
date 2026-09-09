#!/usr/bin/env bash
# Aplica banda e latência em cada enlace conforme topology.py (gerado)
set -e
apply() {  # nó iface latencia_ms banda_kbit
  containerlab tools netem set -n clab-routing-lab-$1 -i $2 --delay ${3}ms --rate ${4}
}
apply R1 eth1 30 100000 ; apply R2 eth1 30 100000
apply R2 eth2 30 100000 ; apply R3 eth1 30 100000
apply R3 eth2 30 100000 ; apply R4 eth1 30 100000
apply R1 eth2 1 10000 ; apply R5 eth2 1 10000
apply R4 eth2 1 10000 ; apply R5 eth1 1 10000
apply R2 eth3 5 10000 ; apply R5 eth3 5 10000
apply R1 eth3 100 1000 ; apply R4 eth3 100 1000
echo "impairments aplicados"

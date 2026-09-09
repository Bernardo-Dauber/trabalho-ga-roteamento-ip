#!/usr/bin/env python3
"""larpd — Latency-Aware Routing Protocol daemon (STUB de M1).

Este é um stub EXPLÍCITO do marco M1: existe apenas para o `COPY larpd.py`
do Dockerfile não quebrar o build da imagem `frr-larp:latest` (D4). A
implementação real do daemon (núcleo puro + camada de I/O) entra no marco M2
(D6) — testes unitários, subida 2 → 3 → 5 nós, custos estabilizando perto do
netem e instalação de rotas com `proto 200`.
"""
import sys


def main():
    print("larpd: stub M1")
    return 0


if __name__ == "__main__":
    sys.exit(main())

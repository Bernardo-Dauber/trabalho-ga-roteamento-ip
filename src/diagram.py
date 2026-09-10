#!/usr/bin/env python3
"""Diagrama da topologia a partir de topology.py (D17) — matplotlib, sem graphviz.

Gera figs/diagrama.png (embutido no README e usado no slide 2). Qualquer
mudança de topologia reflete aqui automaticamente (D3: fonte da verdade única).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from topology import LINKS, LANS

# posições manuais (layout legível para a narrativa: backbone na horizontal)
POS = {
    "R1": (1.5, 3.5), "R2": (4.0, 5.4), "R3": (6.9, 4.2),
    "R4": (6.0, 1.6), "R5": (3.0, 1.2),
}
BACKBONE = {("R1", "R2"), ("R2", "R3"), ("R3", "R4")}
SATELLITE = {("R1", "R4")}

fig, ax = plt.subplots(figsize=(10, 6.5))

# enlaces
for (a, b), (net, _, _, bw, lat, cost) in LINKS.items():
    xa, ya = POS[a]; xb, yb = POS[b]
    if (a, b) in SATELLITE:
        style, color, label = "--", "#c0392b", "satélite (1 mbit, 100 ms)"
    elif (a, b) in BACKBONE:
        style, color, label = "-", "#2c3e50", "backbone (100 mbit, 30 ms)"
    else:
        style, color, label = "-", "#7f8c8d", f"{bw} mbit, {lat} ms"
    ax.plot([xa, xb], [ya, yb], style, color=color, lw=2, zorder=1)
    mx, my = (xa + xb) / 2, (ya + yb) / 2
    ax.annotate(f"{net}\n{lat} ms", (mx, my), ha="center", va="center",
                fontsize=8, color="0.25",
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none",
                          alpha=0.85), zorder=3)

# roteadores
for r, (x, y) in POS.items():
    ax.scatter(x, y, s=900, c="#2980b9", edgecolors="white", zorder=4)
    ax.text(x, y, r, color="white", ha="center", va="center", fontsize=12,
            fontweight="bold", zorder=5)

# hosts (LANs)
for r, (x, y) in POS.items():
    k = r[1:]
    net, _lanif = LANS[r]
    hx, hy = x, y - 0.95
    ax.scatter(hx, hy, marker="s", s=260, c="#e67e22", edgecolors="white",
               zorder=4)
    ax.text(hx, hy, f"h{k}", color="white", ha="center", va="center",
            fontsize=9, fontweight="bold", zorder=5)
    ax.annotate(net, (hx, hy - 0.28), ha="center", fontsize=8, color="0.3")

# linha de custo LARP vs OSPF (nota de leitura)
ax.text(0.5, 6.3,
        "RIP: 1 salto (satélite) · OSPF: backbone (custo 4) · LARP: via R5 (latência ~2 ms)",
        ha="center", fontsize=10, fontstyle="italic", color="0.35")

ax.set_xlim(0, 8.5); ax.set_ylim(-0.3, 6.9)
ax.set_aspect("equal")
ax.axis("off")
ax.set_title("Topologia física — 5 roteadores FRR/LARP + 5 hosts (fonte: topology.py)",
             fontsize=12, pad=12)

os.makedirs("figs", exist_ok=True)
fig.tight_layout()
fig.savefig("figs/diagrama.png", dpi=160)
print("figs/diagrama.png gerado")
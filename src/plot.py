#!/usr/bin/env python3
"""Plotador das 4 figuras comparativas (§9.5) com as três soluções sobrepostas.

Gera figs/{tabela,controle,latencia,convergencia}.png a partir de
results/<modo>/{table,control,latency,path}.csv. Os tempos absolutos
(tcpdump `-tt` e ping `-D`/timestamp de chegada) são normalizados em
t − t_min para sobrepor os três modos na mesma linha do tempo (D11).

EVENTS é derivado de FASE (default 60): os marcadores fixos só valem para a
duração padrão (D12). Use `FASE=60 python3 src/plot.py` para as figuras finais.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

FASE = int(os.environ.get("FASE", "60"))
MODES = ["rip", "ospf", "larp"]
LABEL = {"rip": "RIPv2", "ospf": "OSPFv2", "larp": "LARP (proposto)"}
EVENTS = [(FASE, "queda satélite"), (2 * FASE, "restauro"),
          (3 * FASE, "queda backbone"), (4 * FASE, "degradação R1-R5")]
os.makedirs("figs", exist_ok=True)
plt.rcParams.update({"figure.dpi": 160, "savefig.dpi": 160, "font.size": 9})


def load(name, *cols):
    """Lê um CSV do modo m e devolve DataFrame dos modos que existem."""
    frames = {}
    for m in MODES:
        path = f"results/{m}/{name}.csv"
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            print(f"[plot] aviso: {path} ausente/vazio — modo {m} ignorado")
            continue
        frames[m] = pd.read_csv(path, usecols=cols)
    return frames


def marks(ax):
    for t, lbl in EVENTS:
        ax.axvline(t, color="gray", ls="--", lw=0.8)
        ax.text(t + 2, ax.get_ylim()[1] * 0.95, lbl, fontsize=7, rotation=90,
                va="top", color="gray")


def fig_table():
    fig, ax = plt.subplots(figsize=(8, 4))
    for m, d in load("table", "t", "rotas").items():
        g = d.groupby("t")["rotas"].mean()
        ax.plot(g.index, g.values, label=LABEL[m])
    ax.set_xlabel("tempo (s)")
    ax.set_ylabel("entradas na tabela (média dos 5 nós)")
    ax.set_title("Tamanho da tabela de roteamento")
    ax.legend(); marks(ax)
    fig.tight_layout(); fig.savefig("figs/tabela.png")
    plt.close(fig)


def fig_control():
    fig, ax = plt.subplots(figsize=(8, 4))
    for m, d in load("control", "t_abs", "bytes").items():
        d["t"] = d["t_abs"] - d["t_abs"].min()
        s = d.groupby(d["t"].astype(int))["bytes"].sum().rolling(5).mean()
        ax.plot(s.index, s.values, label=LABEL[m])
    ax.set_xlabel("tempo (s)")
    ax.set_ylabel("bytes de controle / s (média móvel 5s)")
    ax.set_title("Consumo de banda pelo plano de controle")
    ax.legend(); marks(ax)
    fig.tight_layout(); fig.savefig("figs/controle.png")
    plt.close(fig)


def fig_latency():
    fig, ax = plt.subplots(figsize=(8, 4))
    for m, d in load("latency", "t_abs", "rtt_ms").items():
        d["t"] = d["t_abs"] - d["t_abs"].min()
        ax.plot(d["t"], d["rtt_ms"].astype(float), label=LABEL[m], lw=0.8)
    ax.set_xlabel("tempo (s)")
    ax.set_ylabel("RTT h1→h4 (ms)")
    ax.set_title("Latência fim a fim — lacunas indicam indisponibilidade")
    ax.legend(); marks(ax)
    fig.tight_layout(); fig.savefig("figs/latencia.png")
    plt.close(fig)


def fig_convergence():
    """Tempo sem conectividade por evento, derivado das lacunas do ping."""
    rows = []
    for m, d in load("latency", "t_abs", "rtt_ms").items():
        d["t"] = d["t_abs"] - d["t_abs"].min()
        gaps = d["t"].astype(float).diff()
        for t_evt, lbl in EVENTS:
            w = d[(d["t"] > t_evt) & (d["t"] < t_evt + FASE)]
            g = gaps.loc[w.index]
            # lacuna de 0,2 s é o intervalo normal do ping; abaixo disso não é queda
            dt = max(0.0, g.max() - 0.2) if len(g) else 0.0
            rows.append({"modo": LABEL[m], "evento": lbl, "downtime": dt})
    p = pd.DataFrame(rows).pivot(index="evento", columns="modo",
                                 values="downtime")
    ax = p.plot.bar(figsize=(8, 4), rot=15)
    ax.set_ylabel("indisponibilidade (s)")
    ax.set_title("Tempo de convergência por evento")
    ax.figure.tight_layout(); ax.figure.savefig("figs/convergencia.png")
    plt.close(ax.figure)


if __name__ == "__main__":
    fig_table(); fig_control(); fig_latency(); fig_convergence()
    print("figuras em figs/ (tabela, controle, latencia, convergencia)")
#!/usr/bin/env python3
"""Coletor de métricas. Uso: collect.py <modo> <duracao_s>

Transcrição do §9.3 do relatório com as adaptações desta spec/plano:
  - sem `sudo`; assume o contexto Docker `default` (source scripts/_env.sh)
  - 4 threads: table.csv (rotas, 1 Hz), control.csv (tcpdump em R1),
    latency.csv (ping h1->h4 a 0,2 s), path.csv (traceroute a cada 5 s)
  - lacunas do ping = indisponibilidade (ausência de dado é dado, §9.3)
  - grava `results/<modo>/execucao.txt`: registro de execução (D11)
  - ping do Alpine é BusyBox e NÃO suporta `-D` (timestamps do kernel):
    faz fallback para timestamp de chegada (time.time()) — o plotador
    normaliza t - t_min de qualquer forma (D11). Divergência documentada.

Saída: results/<modo>/{table,control,latency,path}.csv + execucao.txt
"""
import csv
import os
import re
import subprocess
import sys
import threading
import time

os.environ.setdefault("DOCKER_CONTEXT", "default")
os.environ.setdefault("DOCKER_HOST", "unix:///var/run/docker.sock")

MODE = sys.argv[1]
DURATION = int(sys.argv[2])
ROUTERS = [f"R{i}" for i in range(1, 6)]
PREFIX = os.environ.get("LAB_PREFIX", "clab-routing-lab")
OUT = f"results/{MODE}"
H4 = "192.168.4.10"

FILTER = {"rip": "udp port 520", "ospf": "proto 89", "larp": "udp port 5555"}[MODE]


def node(name):
    return f"{PREFIX}-{name}"


def dexec(node_name, cmd):
    """Roda um comando dentro do container e devolve stdout (str)."""
    r = subprocess.run(["docker", "exec", node(node_name), "sh", "-c", cmd],
                       capture_output=True, text=True)
    return r.stdout


def run_record():
    """D11: registro de execução — modo, versões, commit."""
    def sh(cmd):
        try:
            return subprocess.run(cmd, shell=True, capture_output=True,
                                  text=True).stdout.strip()
        except Exception:
            return "N/A"
    stamp = time.strftime("%Y-%m-%d %H:%M:%S %z")
    lines = [
        "registro de execução (D11)",
        f"modo: {MODE}",
        f"duracao_s: {DURATION}",
        f"inicio: {stamp}",
        f"docker: {sh('docker --version')}",
        f"containerlab: {sh('containerlab version | grep -E \"^ *version\" | tr -d \" \"')}",
        f"python: {sh('python3 --version')}",
        f"git: {sh('git rev-parse HEAD 2>/dev/null') or 'sem git'}",
        f"host: {sh('uname -sr')}",
    ]
    with open(f"{OUT}/execucao.txt", "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"registro de execução -> {OUT}/execucao.txt")


def table_sizes():
    """Tamanho da tabela de roteamento ao longo do tempo (1 Hz, 5 nós)."""
    with open(f"{OUT}/table.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "router", "rotas"])
        t0 = time.time()
        while time.time() - t0 < DURATION:
            t = round(time.time() - t0, 1)
            for r in ROUTERS:
                out = dexec(r, "ip route show")
                n = len([l for l in out.splitlines() if l.strip()])
                w.writerow([t, r, n])
            f.flush()
            time.sleep(1.0)


def control_traffic():
    """Pacotes e bytes de controle vistos em R1 (filtro do modo)."""
    p = subprocess.Popen(
        ["docker", "exec", node("R1"), "tcpdump", "-l", "-n", "-i", "any",
         "-tt", "-q", FILTER],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    with open(f"{OUT}/control.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_abs", "bytes"])
        for line in p.stdout:
            m = re.search(r"length (\d+)", line)
            ts = line.split()[0] if line.split() else None
            if m and ts:
                w.writerow([ts, m.group(1)])
                f.flush()


def ping_timestamped():
    """True se o `ping` do host suporta -D (iputils); BusyBox não suporta."""
    probe = subprocess.run(
        ["docker", "exec", node("h1"), "ping", "-D", "-c", "1", "-W", "1",
         "127.0.0.1"],
        capture_output=True, text=True)
    return probe.returncode == 0


def latency():
    """RTT fim a fim h1 -> h4, ~5 amostras/s. Lacunas = indisponibilidade."""
    ts_mode = ping_timestamped()
    if ts_mode:
        argv = ["docker", "exec", node("h1"), "ping", "-i", "0.2", "-D", H4]
        rx = re.compile(r"\[(\d+\.\d+)\].*time=([\d.]+) ms")
    else:
        # BusyBox: sem -D — carimba na chegada da linha (equivalente para o
        # plotador, que normaliza t−t_min; a lacuna entre linhas é a métrica).
        argv = ["docker", "exec", node("h1"), "ping", "-i", "0.2", H4]
        rx = re.compile(r"time=([\d.]+) ms")
    p = subprocess.Popen(argv, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True)
    with open(f"{OUT}/latency.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_abs", "rtt_ms"])
        for line in p.stdout:
            m = rx.search(line)
            if m:
                if ts_mode:
                    w.writerow([m.group(1), m.group(2)])
                else:
                    # BusyBox: só o RTT no grupo 1; timestamp de chegada
                    w.writerow([f"{time.time():.3f}", m.group(1)])
                f.flush()


def paths():
    """Caminho escolhido, amostrado a cada 5 s — evidência do slide central."""
    with open(f"{OUT}/path.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "hops"])
        t0 = time.time()
        while time.time() - t0 < DURATION:
            out = dexec("h1", "traceroute -n -q1 -w1 " + H4)
            # só linhas de salto (" 1  x.x.x.x  ..."), ignora o cabeçalho
            # "traceroute to A (A) ..." que repete o destino
            hops = " ".join(re.findall(r"^\s*\d+\s+((?:\d+\.){3}\d+)",
                                      out, re.M))
            w.writerow([round(time.time() - t0, 1), hops])
            f.flush()
            time.sleep(5.0)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    run_record()
    workers = [threading.Thread(target=fn, daemon=True)
               for fn in (table_sizes, control_traffic, latency, paths)]
    for t in workers:
        t.start()
    time.sleep(DURATION)
    print(f"coleta de {MODE} concluída em {OUT}/")
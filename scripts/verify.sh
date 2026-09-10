#!/usr/bin/env bash
# verify.sh — harness de verificação (seam primária, D14).
#
# Dois níveis, ambos sobre comportamento observável (nunca internals):
#
#   1. SMOKE por modo (lab de pé, segundos):  verify.sh <rip|ospf|larp>
#      - conectividade full-mesh 5×5 entre hosts
#      - caminho inicial h1→h4 bate com o esperado do modo
#      - honestidade do modo larp (sem ripd/ospfd; log do daemon com custos)
#      É o portão de M2/M3.
#
#   2. OFFLINE (após scenario.sh, sem lab):   verify.sh --offline [FASE]
#      - lê results/<modo>/*.csv e afirma:
#        (a) janelas de indisponibilidade por evento dentro das tolerâncias D13
#        (b) caminho dominante por janela = esperado do modo
#        (c) os três modos têm caminho inicial DISTINTO entre si
#
# Tolerâncias D13 são constantes nomeadas abaixo (calibradas em M4 com a
# execução real antes de serem travadas no commit dos resultados).
set -uo pipefail
cd "$(dirname "$0")/.."   # raiz do repo
# shellcheck disable=SC1091
source scripts/_env.sh

# ------------------------------------------------------------------ constantes
# D13 — janelas de indisponibilidade (segundos). Valores calibrados em M4.
JITTER_GAP=1.0            # lacuna normal do ping: 1 pacote perdido = 0,4 s
RIP_QUEDA_MIN=5.0         # RIP DEVE ter >= isso de queda no t=FASE (satélite);
                          # se convergir em ~3 s a medição está errada (§9.5)
RIP_GAP_MAX=60.0          # teto da convergência do RIP (dezenas de segundos)
OSPF_GAP_MAX=25.0         # OSPF reconverge em poucos segundos
LARP_GAP_MAX=25.0         # LARP ~ DEAD_AFTER (6 s) + margem
INDIFFERENT_GAP_MAX=6.0   # evento que não deveria afetar o modo
WINDOW_FRAC=0.75          # fração da fase usada como janela pós-evento

H4=192.168.4.10

# ---------------------------------------------------------------- prefixo lab
resolve_prefix() {
  # nome do container resolve via docker ps; fallback literals do manifesto
  local candidate
  candidate=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -E -- '-R1$' | head -1 || true)
  if [ -n "$candidate" ]; then
    echo "${candidate%-R1}"
  else
    echo "clab-routing-lab"
  fi
}
PREFIX=$(resolve_prefix)

# ------------------------------------------------------------------ smoke
smoke() {
  local mode=$1 failed=0 prefix=$PREFIX
  echo "== smoke $mode (lab de pé, prefixo=$prefix) =="

  # aguarda convergência inicial dos protocolos antes de afirmar o caminho
  # OSPF em cold-start leva ~40 s (hellos de 10 s + adjacência); RIP/LARP
  # convergem em poucos segundos. 55 s cobre os três com folga.
  echo "-- aguardando 55 s de convergência inicial (OSPF cold-start é lento)"
  sleep 55

  # 1. full-mesh 5×5 de hosts (report §10); 1 retry por par para absorver
  #    queda transitória (a rede está convergindo/atualizando tabelas)
  local i j ok=0
  for i in 1 2 3 4 5; do
    for j in 1 2 3 4 5; do
      [ "$i" -eq "$j" ] && continue
      if docker exec "${prefix}-h$i" ping -c1 -W2 "192.168.$j.10" >/dev/null 2>&1 \
         || docker exec "${prefix}-h$i" ping -c1 -W2 "192.168.$j.10" >/dev/null 2>&1; then
        ok=$((ok+1))
      else
        echo "FAIL conectividade h$i->h$j"; failed=$((failed+1))
      fi
    done
  done
  echo "PASS full-mesh 5×5: $ok/20"
  [ "$ok" -ne 20 ] && failed=$((failed+1))

  # 2. caminho inicial h1→h4
  local tpath
  tpath=$(docker exec "${prefix}-h1" traceroute -n -q1 -w1 "$H4" 2>/dev/null \
          | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | tr '\n' ' ')
  echo "   traceroute: $tpath"
  local exp sig
  case "$mode" in
    rip)  exp="RIP via satélite (10.0.14.x)";  sig="10.0.14.2" ;;
    ospf) exp="OSPF via backbone (10.0.12.x 10.0.23.x 10.0.34.x)"
          sig="10.0.12.2 10.0.23.2 10.0.34.2" ;;
    larp) exp="LARP via R5 (10.0.15.x 10.0.45.x)"
          sig="10.0.15.2 10.0.45.1" ;;
  esac
  local ok_sig=1 s
  for s in $sig; do
    case " $tpath " in
      *" $s "*) ;;
      *) echo "FAIL caminho: falta $s ($exp)"; ok_sig=0 ;;
    esac
  done
  [ "$ok_sig" -eq 1 ] && echo "PASS caminho inicial: $exp" || failed=$((failed+1))

  # 3. honestidade do modo larp
  if [ "$mode" = "larp" ]; then
    local procs
    procs=$(docker exec "${prefix}-R1" sh -c 'ps -o comm= 2>/dev/null' | sort -u | tr '\n' ' ')
    echo "   processos R1: $procs"
    if echo "$procs" | grep -qE 'ripd|ospfd'; then
      echo "FAIL honestidade: ripd/ospfd rodando no modo larp"; failed=$((failed+1))
    else
      echo "PASS honestidade: sem ripd/ospfd"
    fi
    local rip_out ospf_out
    # vtysh sai com código 1 quando o daemon não roda; capturamos a saída
    # antes de testar (pipefail tornaria o pipeline falso mesmo com match)
    rip_out=$(docker exec "${prefix}-R1" vtysh -c "show ip rip" 2>&1 || true)
    ospf_out=$(docker exec "${prefix}-R1" vtysh -c "show ip ospf neighbor" 2>&1 || true)
    if echo "$rip_out" | grep -q "ripd is not running" \
       && echo "$ospf_out" | grep -q "ospfd is not running"; then
      echo "PASS honestidade: show ip rip / show ip ospf vazios"
    else
      echo "FAIL honestidade: FRR ancora rotas RIP/OSPF no modo larp"
      echo "       rip : $(echo "$rip_out" | tail -1)"
      echo "       ospf: $(echo "$ospf_out" | tail -1)"
      failed=$((failed+1))
    fi
    if docker exec "${prefix}-R1" sh -c 'grep -q "custo" /var/log/larpd.log 2>/dev/null'; then
      echo "PASS honestidade: /var/log/larpd.log com custos medidos"
    else
      echo "FAIL honestidade: larpd.log sem custos medidos"; failed=$((failed+1))
    fi
  fi

  echo "------------------------------"
  if [ "$failed" -ne 0 ]; then
    echo "SMOKE $mode FALHOU ($failed)" >&2
    return 1
  fi
  echo "SMOKE $mode OK"
  return 0
}

# ------------------------------------------------------------------ offline
offline() {
  # verify.sh --offline [FASE] — roda sem lab, sobre os CSVs
  python3 - "$1" <<'PY'
import csv, math, os, statistics, sys

FASE = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0

# tolerâncias D13 (espelhadas do bash; valores calibrados em M4)
JITTER_GAP       = 1.0
RIP_QUEDA_MIN    = 5.0
RIP_GAP_MAX      = 60.0
OSPF_GAP_MAX     = 25.0
LARP_GAP_MAX     = 25.0
INDIFFERENT_GAP_MAX = 6.0
WINDOW_FRAC      = 0.75
SAMPLE_INTERVAL  = 5.0   # cadência do path.csv

MODES = ["rip", "ospf", "larp"]
EXPECT_INITIAL = {
    "rip":  ("10.0.14.2",),
    "ospf": ("10.0.12.2", "10.0.23.2", "10.0.34.2"),
    "larp": ("10.0.15.2", "10.0.45.1"),
}
SATELLITE = ("10.0.14.2",)
VIA_R5    = ("10.0.15.2", "10.0.45.1")
BACKBONE  = ("10.0.12.2", "10.0.23.2", "10.0.34.2")
# LARP depois da degradação de R1-R5: sai da R1-R5 e vai pelo menor caminho
# medido, que é R1->R2->R5->R4 (~36 ms: 30+5+1) — NÃO o backbone (90 ms).
# O essencial a afirmar: não usa mais 10.0.15.2 (a PONTA R1 do enlace
# degradado; 10.0.45.1 continua aparecendo porque R4 é alcançado por R5) e o
# primeiro salto vira R2. (Calibrado em M4; o relatório previa backbone —
# a métrica dinâmica achou o caminho verdadeiramente menor.)
DEGRADED_LINK = "10.0.15.2"   # ponta R1 do enlace R1-R5
VIA_R2        = ("10.0.12.2",)

failures = []

def fail(msg):
    failures.append(msg)
    print("  FAIL " + msg)

def ok(msg):
    print("  PASS " + msg)

# ------------------------------------------------------------- cargas
def read_latency(mode):
    """t normalizado + gaps. Retorna (lista de t, gaps por índice)."""
    path = f"results/{mode}/latency.csv"
    rows = []
    with open(path) as f:
        for i, line in enumerate(f):
            if i == 0:
                continue
            parts = line.strip().split(",")
            if len(parts) < 2 or not parts[0] or not parts[1]:
                continue
            rows.append(float(parts[0]))
    if not rows:
        return None, []
    t0 = rows[0]
    ts = [v - t0 for v in rows]
    gaps = [ts[i] - ts[i - 1] for i in range(1, len(ts))]
    return ts, gaps

def max_gap_in(ts, gaps, a, b):
    """Maior lacuna de ping (s) que SOBREPÕE a janela (a, b).

    A lacuna de índice i acontece ENTRE ts[i] e ts[i+1] (gaps[i] =
    ts[i+1]-ts[i]). Ela pertence ao evento se toca a janela (ex.: o down em
    t=60 parte o stream em 59.6..74.9 — início antes do evento, fim depois)."""
    best = 0.0
    for i, g in enumerate(gaps):
        start, end = ts[i], ts[i + 1]
        if start < b and end > a and g > best:
            best = g
    return best

def read_path(mode):
    """lista (t, frozenset de IPs) do path.csv."""
    out = []
    with open(f"results/{mode}/path.csv") as f:
        for i, line in enumerate(f):
            if i == 0:
                continue
            parts = line.strip().split(",", 1)
            if len(parts) < 2 or not parts[0]:
                continue
            ips = tuple(p for p in parts[1].replace(",", " ").split()
                        if "." in p)
            try:
                out.append((float(parts[0]), frozenset(ips)))
            except ValueError:
                continue
    return out

def dominant_in(path, a, b):
    """moda dos conjuntos de IPs no intervalo (a, b); None se vazio."""
    win = [ips for t, ips in path if a < t < b]
    if not win:
        return None
    from collections import Counter
    return Counter(win).most_common(1)[0][0]

def has(ips, sig):
    return all(any(s == ip for ip in ips) for s in sig)

def windows():
    """Janelas (nome, início, fim) relativas aos eventos."""
    w = []
    w.append(("inicial", 0.75 * FASE, FASE))
    for k in range(1, 5):
        w.append((f"ev{k}", k * FASE, k * FASE + WINDOW_FRAC * FASE))
    return w

# ------------------------------------------------------------- 1. arquivos
print(f"== offline verify (FASE={FASE:g}) ==")
if FASE != 60.0:
    print("  aviso: tolerâncias D13 e janelas calibradas para FASE=60; "
          "fases curtas podem falhar por construção (só servem para iterar)")
for m in MODES:
    for f in ("table.csv", "control.csv", "latency.csv", "path.csv",
              "execucao.txt"):
        if not os.path.exists(f"results/{m}/{f}"):
            fail(f"arquivo ausente: results/{m}/{f}")

# ------------------------------------------------------------- 2. latência
lat = {m: read_latency(m) for m in MODES}
ev_labels = ["queda satélite (t=F)", "restauro satélite (t=2F)",
             "queda backbone (t=3F)", "restauro+degradação R1-R5 (t=4F)"]

# reação esperada por (modo, evento 1..4): None = indiferente
expect_gap = {
    # (modo, k) -> (min, max)
    ("rip", 1): (RIP_QUEDA_MIN, RIP_GAP_MAX),   # perde o satélite usado (15 s medido)
    ("rip", 2): (0.0, RIP_GAP_MAX),             # volta ao satélite
    ("ospf", 3): (0.0, OSPF_GAP_MAX),           # backbone cai (switch sem lacuna)
    ("ospf", 4): (0.0, OSPF_GAP_MAX),           # backbone restaura
    ("larp", 4): (0.0, LARP_GAP_MAX),           # muda de caminho por latência
}
for m in MODES:
    ts, gaps = lat[m]
    if ts is None:
        continue
    for k in range(1, 5):
        ev = (m, k)
        gap = max_gap_in(ts, gaps, k * FASE, k * FASE + WINDOW_FRAC * FASE)
        have_fail = False
        if ev in expect_gap:
            lo, hi = expect_gap[ev]
            if gap < lo:
                fail(f"{m} ev{k} ({ev_labels[k-1]}): lacuna {gap:.1f}s < mínimo {lo:.0f}s — "
                     "medição suspeita (protocolo deveria ter reagido)")
                have_fail = True
            elif gap > hi:
                fail(f"{m} ev{k} ({ev_labels[k-1]}): lacuna {gap:.1f}s > teto {hi:.0f}s")
                have_fail = True
        else:
            if gap > INDIFFERENT_GAP_MAX:
                fail(f"{m} ev{k} ({ev_labels[k-1]}): reagiu sem dever "
                     f"(lacuna {gap:.1f}s > {INDIFFERENT_GAP_MAX:.0f}s)")
                have_fail = True
        if not have_fail:
            ok(f"{m} ev{k} ({ev_labels[k-1]}): lacuna {gap:.1f}s")

# ------------------------------------------------------------- 3. caminhos
paths = {m: read_path(m) for m in MODES}
WIN_INI = (0.75 * FASE, FASE)
dominants = {m: dominant_in(paths[m], *WIN_INI) for m in MODES}

print("-- caminho inicial (janela 0.75F..F)")
for m in MODES:
    d = dominants[m]
    if d is None:
        fail(f"{m}: sem amostras de traceroute na janela inicial")
        continue
    if has(d, EXPECT_INITIAL[m]):
        ok(f"{m}: caminho inicial = esperado ({" ".join(sorted(d))})")
    else:
        fail(f"{m}: caminho inicial {sorted(d)} não bate com {EXPECT_INITIAL[m]}")

# (c) três caminhos iniciais distintos entre si
inis = {m: dominants[m] for m in MODES if dominants[m] is not None}
if len(inis) == 3:
    a, b, c = (inis[m] for m in MODES)
    if a == b or b == c or a == c:
        fail("caminhos iniciais NÃO são mutuamente distintos "
             f"({[sorted(v) for v in [a, b, c]]})")
    else:
        ok("caminhos iniciais dos 3 modos são mutuamente distintos")

# reações de caminho esperadas por janela
print("-- reação por evento (caminho dominante)")
for k, evname in [(1, "queda satélite"), (2, "restauro satélite"),
                  (3, "queda backbone"), (4, "restauro+degradação R1-R5")]:
    for m in MODES:
        # janela da reação: OSPF volta ao backbone só ao final (hellos de 10 s
        # reconstroem a adjacência R2-R3 em ~40-50 s — medido em M4); as demais
        # reações são rápidas e aparecem logo após o evento.
        if m == "ospf" and k == 4:
            win = (5 * FASE - 4 * SAMPLE_INTERVAL, 5 * FASE)
        else:
            win = (k * FASE, k * FASE + WINDOW_FRAC * FASE)
        d = dominant_in(paths[m], *win)
        if d is None:
            fail(f"{m} ev{k} ({evname}): sem amostras na janela")
            continue
        if m == "rip" and k == 1 and not has(d, VIA_R5):
            fail(f"rip ev1: deveria ter migrado p/ via R5, está em {sorted(d)}")
        elif m == "rip" and k == 2 and not has(d, SATELLITE):
            fail(f"rip ev2: deveria ter voltado ao satélite, está em {sorted(d)}")
        elif m == "ospf" and k == 3 and not has(d, VIA_R5):
            fail(f"ospf ev3: deveria ter migrado p/ via R5, está em {sorted(d)}")
        elif m == "ospf" and k == 4 and not has(d, BACKBONE):
            fail(f"ospf ev4: deveria ter VOLTADO ao backbone ao final, "
                 f"está em {sorted(d)} (adjacência R2-R3 demora ~45 s)")
        elif m == "larp" and k == 4 and not (has(d, VIA_R2) and DEGRADED_LINK not in d):
            fail(f"larp ev4: deveria ter SAÍDO de R1-R5 (degradada) via R2, "
                 f"está em {sorted(d)}")
        elif m == "larp" and k in (1, 2, 3) and not has(d, VIA_R5):
            fail(f"larp ev{k}: indiferente ao evento, mas saiu de R5: {sorted(d)}")
        else:
            ok(f"{m} ev{k} ({evname}): {sorted(d)}")

# a asserção-chave: LARP é a única solução cuja mudança de caminho no ev4 é
# causada pela LATÊNCIA (R1-R5 degradado a 200 ms).
#  - larp: caminho inicial via R5 -> final no backbone (mede o custo, sai de R5)
#  - rip : ev4 continua no satélite (cego à latência) — igual ao inicial
#  - ospf: final de novo no backbone = inicial; o desvio por R5 em 240..~285 é
#    a propagação do RESTAURO (adjacência R2-R3), não reação à degradação
print("-- asserção-chave (só o LARP reage à latência)")
for m in MODES:
    d0 = dominants[m]
    dfin = dominant_in(paths[m], 5 * FASE - 4 * SAMPLE_INTERVAL, 5 * FASE)
    if m == "larp":
        if (dfin is not None and d0 is not None
                and has(dfin, VIA_R2) and DEGRADED_LINK not in dfin
                and has(d0, VIA_R5)):
            ok("larp: saiu de R1-R5 DEPOIS da degradação de latência (única a reagir)")
        else:
            fail(f"larp: não migrou de R1-R5 (inicial {sorted(d0 or ())} -> final "
                 f"{sorted(dfin or ())}) — deveria reagir à latência")
    else:
        # rip: ev4 continua no satélite; ospf: final = inicial (backbone)
        expected = SATELLITE if m == "rip" else BACKBONE
        if dfin is not None and has(dfin, expected):
            ok(f"{m}: caminho final = esperado ({sorted(dfin)}) — cego à latência")
        else:
            fail(f"{m}: caminho final {sorted(dfin or ())} não é {expected}")

print("------------------------------")
if failures:
    print(f"OFFLINE FALHOU ({len(failures)})")
    sys.exit(1)
print("OFFLINE OK")
PY
}

# ------------------------------------------------------------------ main
if [ "${1:-}" = "--offline" ]; then
  offline "${2:-}"
  exit $?
elif [ $# -ge 1 ] && [[ "$1" =~ ^(rip|ospf|larp)$ ]]; then
  smoke "$1"
  exit $?
fi
echo "uso: verify.sh <rip|ospf|larp>   (smoke, lab de pé)" >&2
echo "     verify.sh --offline [FASE]  (sobre os CSVs, sem lab)" >&2
exit 1
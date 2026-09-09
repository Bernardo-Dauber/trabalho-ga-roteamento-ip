# Trabalho I — Roteamento IP
## Relatório de implementação

Fundamentos de Sistemas Operacionais — Unisinos
Entrega: 01/10/2026 até 19h (Moodle) · Apresentação: 10 min

---

## 1. Decisões fechadas

| Decisão | Escolha | Justificativa para a apresentação |
|---|---|---|
| Emulação | Containerlab + Docker | Topologia versionável em YAML, lab sobe em ~20s, cada nó é um Linux completo |
| Plataforma | FRRouting (FRR) | Sucessor direto do Quagga citado no enunciado; Quagga está descontinuado desde 2018 |
| Protocolo 1 | RIPv2 | Vetor de distância, métrica por saltos |
| Protocolo 2 | OSPFv2 | Estado de enlace, métrica por banda |
| Algoritmo próprio | LARP — estado de enlace com latência medida | Métrica dinâmica, medida em tempo real |
| Isolamento | Teardown completo por execução | Sem estado residual contaminando as métricas |
| Métricas | CSV + matplotlib, roteiro cronometrado | Gráficos reprodutíveis e prontos para slide |
| Execução | Individual | Cronograma na seção 12 já ajustado |

---

## 2. Ambiente — instalação no Zorin OS (base Ubuntu)

### 2.1 A armadilha das distros derivadas

O script de conveniência do Docker (`get.docker.com`) e o repositório oficial leem `VERSION_CODENAME` de `/etc/os-release`. No Zorin esse campo traz o codinome do **Zorin**, não do Ubuntu, e o repositório do Docker não tem pacote para ele — o `apt update` falha com 404 e a mensagem não deixa a causa óbvia.

A solução é usar `UBUNTU_CODENAME`, que o Zorin também expõe. Confirme antes de qualquer coisa:

```bash
grep -E 'VERSION_CODENAME|UBUNTU_CODENAME|PRETTY_NAME' /etc/os-release
```

Você deve ver algo como `UBUNTU_CODENAME=jammy` (Zorin 17) ou `noble` (Zorin 18). É esse valor que vai no repositório.

### 2.2 Docker Engine

Não use `apt install docker.io` — a versão dos repositórios do Ubuntu costuma ser antiga demais para o Containerlab.

```bash
# Remover pacotes conflitantes, se houver
for p in docker.io docker-doc docker-compose podman-docker containerd runc; do
  sudo apt remove -y $p 2>/dev/null
done

# Chave e repositório oficiais, usando UBUNTU_CODENAME
sudo apt update && sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $UBUNTU_CODENAME stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io \
                    docker-buildx-plugin docker-compose-plugin

sudo systemctl enable --now docker
sudo usermod -aG docker $USER
```

O `$UBUNTU_CODENAME` na terceira linha é o ponto inteiro desta seção. Se você copiar um tutorial de Ubuntu que usa `$VERSION_CODENAME`, quebra.

### 2.3 Containerlab e ferramentas

```bash
bash -c "$(curl -sL https://get.containerlab.dev)"

sudo apt install -y tcpdump tshark iperf3 traceroute \
                    python3-pip python3-matplotlib python3-pandas
```

Na instalação do `tshark` aparece um diálogo perguntando se usuários não-root podem capturar pacotes. Responda **sim** — sem isso o `tcpdump` do coletor precisa de `sudo` e o `docker exec` do `collect.py` fica inconsistente.

### 2.4 Verificação

```bash
docker run --rm hello-world
containerlab version
python3 -c "import matplotlib, pandas; print('ok')"
```

Se `docker` ainda pedir `sudo` depois do `usermod`, faça logout completo da sessão gráfica do Zorin — abrir um terminal novo não recarrega os grupos. `newgrp docker` resolve só na aba atual.

### 2.5 AppArmor

O Ubuntu (e portanto o Zorin) roda AppArmor por padrão, o que o Arch não faz. Ele não bloqueia containers Docker normais, mas o `larpd` manipula rotas via netlink dentro do container. Se você vir `Operation not permitted` no log do daemon mesmo com o container privilegiado, verifique:

```bash
sudo dmesg | grep -i apparmor | tail -20
```

Se aparecer bloqueio, adicione ao nó no `topology.clab.yml`:

```yaml
    R1: {kind: linux, binds: [...], cap-add: ["NET_ADMIN", "NET_RAW"]}
```

Na prática o Containerlab já sobe os nós com privilégios suficientes, então isso é diagnóstico preventivo — só volte aqui se o sintoma aparecer.

### Imagem base

Uma única imagem para todos os nós, em todos os modos.

`docker/Dockerfile`:

```dockerfile
FROM quay.io/frrouting/frr:9.1.0

RUN apk add --no-cache \
      python3 py3-pip iperf3 tcpdump traceroute iproute2 bind-tools \
 && pip3 install --break-system-packages pyroute2

COPY larpd.py /usr/local/bin/larpd
RUN chmod +x /usr/local/bin/larpd
```

```bash
cp src/larpd.py docker/
docker build -t frr-larp:latest docker/
```

---

## 3. Estrutura do repositório

```
trabalho-roteamento/
├── README.md                  # quickstart — o professor lê isto primeiro
├── docker/
│   ├── Dockerfile
│   └── larpd.py               # cópia gerada pelo build
├── topology.clab.yml          # topologia física
├── topology.py                # topologia como dado (fonte da verdade)
├── configs/
│   ├── rip/R1..R5/{frr.conf,daemons}
│   ├── ospf/R1..R5/{frr.conf,daemons}
│   └── larp/R1..R5/{frr.conf,daemons}
├── src/
│   ├── larpd.py               # daemon do algoritmo próprio
│   ├── gen_configs.py         # gera configs/ a partir de topology.py
│   ├── collect.py             # coletor de métricas
│   └── plot.py                # gráficos
├── scripts/
│   ├── run.sh                 # run.sh rip|ospf|larp
│   ├── scenario.sh            # roteiro cronometrado de eventos
│   └── impair.sh              # aplica netem nos enlaces
├── results/                   # CSVs das execuções
├── figs/                      # PNGs dos gráficos
└── docs/
    ├── relatorio.pdf
    └── apresentacao.pdf
```

---

## 4. Topologia e plano de endereçamento

### 4.1 Enlaces

| Enlace | Rede | Banda | Latência (netem) | Custo OSPF | Papel |
|---|---|---|---|---|---|
| R1–R2 | 10.0.12.0/30 | 100 Mbps | 30 ms | 1 | backbone |
| R2–R3 | 10.0.23.0/30 | 100 Mbps | 30 ms | 1 | backbone |
| R3–R4 | 10.0.34.0/30 | 100 Mbps | 30 ms | 1 | backbone |
| R1–R5 | 10.0.15.0/30 | 10 Mbps | 1 ms | 10 | metropolitano |
| R4–R5 | 10.0.45.0/30 | 10 Mbps | 1 ms | 10 | metropolitano |
| R2–R5 | 10.0.25.0/30 | 10 Mbps | 5 ms | 10 | metropolitano |
| R1–R4 | 10.0.14.0/30 | 1 Mbps | 100 ms | 100 | satélite |

A narrativa física: o backbone é fibra de longa distância — muita banda, muita distância, logo muita latência. Os enlaces metropolitanos são curtos e baratos — pouca banda, latência mínima. O satélite é o atalho topológico que parece ótimo para quem só conta saltos.

### 4.2 Endereços

| Nó | Loopback | LAN | Host da LAN |
|---|---|---|---|
| R1 | 10.255.0.1/32 | 192.168.1.0/24 | h1 = 192.168.1.10 |
| R2 | 10.255.0.2/32 | 192.168.2.0/24 | h2 = 192.168.2.10 |
| R3 | 10.255.0.3/32 | 192.168.3.0/24 | h3 = 192.168.3.10 |
| R4 | 10.255.0.4/32 | 192.168.4.0/24 | h4 = 192.168.4.10 |
| R5 | 10.255.0.5/32 | 192.168.5.0/24 | h5 = 192.168.5.10 |

Em cada `/30`, o roteador de menor número fica com `.1` e o de maior com `.2`. O gateway de cada LAN é `.1`.

### 4.3 Interfaces

| Nó | eth1 | eth2 | eth3 | eth4 |
|---|---|---|---|---|
| R1 | →R2 10.0.12.1/30 | →R5 10.0.15.1/30 | →R4 10.0.14.1/30 | LAN 192.168.1.1/24 |
| R2 | →R1 10.0.12.2/30 | →R3 10.0.23.1/30 | →R5 10.0.25.1/30 | LAN 192.168.2.1/24 |
| R3 | →R2 10.0.23.2/30 | →R4 10.0.34.1/30 | LAN 192.168.3.1/24 | — |
| R4 | →R3 10.0.34.2/30 | →R5 10.0.45.1/30 | →R1 10.0.14.2/30 | LAN 192.168.4.1/24 |
| R5 | →R4 10.0.45.2/30 | →R1 10.0.15.2/30 | →R2 10.0.25.2/30 | LAN 192.168.5.1/24 |

### 4.4 O resultado que a topologia foi desenhada para produzir

Caminho de `192.168.1.0/24` (h1) até `192.168.4.0/24` (h4):

| Solução | Caminho escolhido | Por quê | Latência real |
|---|---|---|---|
| RIP | R1 →satélite→ R4 | 1 salto, e RIP só conta saltos | ~100 ms |
| OSPF | R1→R2→R3→R4 | custo 3 contra 20 (via R5) e 100 (satélite) | ~90 ms |
| LARP | R1→R5→R4 | 2 ms medidos, contra 90 e 100 | ~2 ms |

Três respostas diferentes, cada uma tecnicamente correta dentro da própria métrica. Este é o slide central da apresentação.

---

## 5. `topology.py` — a fonte da verdade

Tudo (configs, netem, coletor) é gerado a partir deste arquivo. Mudou a topologia, mudou num lugar só.

```python
# topology.py
ROUTERS = ["R1", "R2", "R3", "R4", "R5"]

# (a, b): (rede, if_a, if_b, banda_mbit, latencia_ms, custo_ospf)
LINKS = {
    ("R1", "R2"): ("10.0.12.0/30", "eth1", "eth1", 100,  30,   1),
    ("R2", "R3"): ("10.0.23.0/30", "eth2", "eth1", 100,  30,   1),
    ("R3", "R4"): ("10.0.34.0/30", "eth2", "eth1", 100,  30,   1),
    ("R1", "R5"): ("10.0.15.0/30", "eth2", "eth2",  10,   1,  10),
    ("R4", "R5"): ("10.0.45.0/30", "eth2", "eth1",  10,   1,  10),
    ("R2", "R5"): ("10.0.25.0/30", "eth3", "eth3",  10,   5,  10),
    ("R1", "R4"): ("10.0.14.0/30", "eth3", "eth3",   1, 100, 100),
}

LANS = {
    "R1": ("192.168.1.0/24", "eth4"),
    "R2": ("192.168.2.0/24", "eth4"),
    "R3": ("192.168.3.0/24", "eth3"),
    "R4": ("192.168.4.0/24", "eth4"),
    "R5": ("192.168.5.0/24", "eth4"),
}

LOOPBACK = {r: f"10.255.0.{i+1}/32" for i, r in enumerate(ROUTERS)}


def addr_of(router, link):
    """Endereço /30 do roteador neste enlace: menor número fica com .1"""
    a, b = link
    net = LINKS[link][0].split("/")[0].rsplit(".", 1)[0]
    return f"{net}.1/30" if router == a else f"{net}.2/30"


def links_of(router):
    return [k for k in LINKS if router in k]


def iface_of(router, link):
    _, if_a, if_b, *_ = LINKS[link]
    return if_a if router == link[0] else if_b
```

---

## 6. `topology.clab.yml`

```yaml
name: routing-lab

topology:
  kinds:
    linux:
      image: frr-larp:latest

  nodes:
    R1: {kind: linux, binds: ["configs/${MODE}/R1:/etc/frr"]}
    R2: {kind: linux, binds: ["configs/${MODE}/R2:/etc/frr"]}
    R3: {kind: linux, binds: ["configs/${MODE}/R3:/etc/frr"]}
    R4: {kind: linux, binds: ["configs/${MODE}/R4:/etc/frr"]}
    R5: {kind: linux, binds: ["configs/${MODE}/R5:/etc/frr"]}

    h1: {kind: linux, image: alpine:3.19, exec: ["ip addr add 192.168.1.10/24 dev eth1", "ip link set eth1 up", "ip route add default via 192.168.1.1"]}
    h2: {kind: linux, image: alpine:3.19, exec: ["ip addr add 192.168.2.10/24 dev eth1", "ip link set eth1 up", "ip route add default via 192.168.2.1"]}
    h3: {kind: linux, image: alpine:3.19, exec: ["ip addr add 192.168.3.10/24 dev eth1", "ip link set eth1 up", "ip route add default via 192.168.3.1"]}
    h4: {kind: linux, image: alpine:3.19, exec: ["ip addr add 192.168.4.10/24 dev eth1", "ip link set eth1 up", "ip route add default via 192.168.4.1"]}
    h5: {kind: linux, image: alpine:3.19, exec: ["ip addr add 192.168.5.10/24 dev eth1", "ip link set eth1 up", "ip route add default via 192.168.5.1"]}

  links:
    - endpoints: ["R1:eth1", "R2:eth1"]
    - endpoints: ["R2:eth2", "R3:eth1"]
    - endpoints: ["R3:eth2", "R4:eth1"]
    - endpoints: ["R1:eth2", "R5:eth2"]
    - endpoints: ["R4:eth2", "R5:eth1"]
    - endpoints: ["R2:eth3", "R5:eth3"]
    - endpoints: ["R1:eth3", "R4:eth3"]
    - endpoints: ["R1:eth4", "h1:eth1"]
    - endpoints: ["R2:eth4", "h2:eth1"]
    - endpoints: ["R3:eth3", "h3:eth1"]
    - endpoints: ["R4:eth4", "h4:eth1"]
    - endpoints: ["R5:eth4", "h5:eth1"]
```

`${MODE}` é expandido pelo Containerlab a partir da variável de ambiente — é isso que faz o `run.sh rip` montar `configs/rip/` em vez de outro.

---

## 7. `src/gen_configs.py` — geração das configurações

```python
#!/usr/bin/env python3
"""Gera configs/{rip,ospf,larp}/R*/{frr.conf,daemons} a partir de topology.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from topology import ROUTERS, LINKS, LANS, LOOPBACK, addr_of, links_of, iface_of

DAEMONS = {
    "rip":  {"zebra": "yes", "ripd": "yes",  "ospfd": "no"},
    "ospf": {"zebra": "yes", "ripd": "no",   "ospfd": "yes"},
    "larp": {"zebra": "yes", "ripd": "no",   "ospfd": "no"},
}
ALL_DAEMONS = ["zebra", "bgpd", "ospfd", "ospf6d", "ripd", "ripngd",
               "isisd", "pimd", "ldpd", "nhrpd", "eigrpd", "babeld",
               "sharpd", "pbrd", "staticd", "bfdd", "fabricd", "vrrpd"]


def interfaces_block(r, mode):
    out = []
    out.append("interface lo")
    out.append(f" ip address {LOOPBACK[r]}")
    out.append("!")
    for link in links_of(r):
        ifn = iface_of(r, link)
        cost = LINKS[link][5]
        out.append(f"interface {ifn}")
        out.append(f" ip address {addr_of(r, link)}")
        if mode == "ospf":
            out.append(f" ip ospf cost {cost}")
        out.append("!")
    lan, lanif = LANS[r]
    lanaddr = lan.replace(".0/24", ".1/24")
    out.append(f"interface {lanif}")
    out.append(f" ip address {lanaddr}")
    if mode == "ospf":
        out.append(" ip ospf cost 1")
        out.append(" ip ospf passive")
    out.append("!")
    return out


def routing_block(r, mode):
    out = []
    nets = [LINKS[l][0] for l in links_of(r)] + [LANS[r][0]] + [LOOPBACK[r]]
    if mode == "rip":
        out.append("router rip")
        out.append(" version 2")
        for n in nets:
            out.append(f" network {n}")
        out.append(f" passive-interface {LANS[r][1]}")
        out.append("!")
    elif mode == "ospf":
        rid = LOOPBACK[r].split("/")[0]
        out.append("router ospf")
        out.append(f" ospf router-id {rid}")
        out.append(" auto-cost reference-bandwidth 100")
        for n in nets:
            out.append(f" network {n} area 0")
        out.append("!")
    # larp: nenhum protocolo no FRR — só zebra para endereçamento
    return out


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for mode in DAEMONS:
        for r in ROUTERS:
            d = os.path.join(root, "configs", mode, r)
            os.makedirs(d, exist_ok=True)

            lines = ["frr version 9.1", "frr defaults traditional",
                     f"hostname {r}", "log stdout", "no ipv6 forwarding", "!"]
            lines += interfaces_block(r, mode)
            lines += routing_block(r, mode)
            lines.append("line vty")
            with open(os.path.join(d, "frr.conf"), "w") as f:
                f.write("\n".join(lines) + "\n")

            with open(os.path.join(d, "daemons"), "w") as f:
                for dm in ALL_DAEMONS:
                    f.write(f"{dm}={DAEMONS[mode].get(dm, 'no')}\n")
                f.write('vtysh_enable=yes\nzebra_options="  -A 127.0.0.1 -s 90000000"\n')
                f.write('ripd_options="  -A 127.0.0.1"\nospfd_options="  -A 127.0.0.1"\n')
            print(f"gerado configs/{mode}/{r}")


if __name__ == "__main__":
    main()
```

Note o que o modo `larp` produz: um `frr.conf` só com endereçamento e um `daemons` com tudo desligado exceto `zebra`. Isso deixa visualmente evidente para o professor que RIP e OSPF não estão rodando junto com o algoritmo próprio — atende ao requisito do enunciado sem depender de você explicar.

---

## 8. LARP — o algoritmo próprio

### 8.1 Especificação (esta seção vira o texto do item 4 da avaliação)

**Nome:** LARP — Latency-Aware Routing Protocol.

**Classificação:** protocolo de estado de enlace, distribuído, com métrica ativa.

**Princípio de funcionamento.** Cada roteador mede continuamente a latência real de cada um dos seus enlaces, anuncia essas medições a toda a rede por inundação, monta um grafo completo da topologia e calcula localmente as rotas por Dijkstra. A diferença essencial em relação ao OSPF está na métrica: o OSPF usa um custo **estático**, derivado da banda nominal configurada, enquanto o LARP usa um custo **dinâmico**, derivado de RTT medido em tempo de execução.

**Critérios de seleção de rota.** Menor soma de latências medidas ao longo do caminho. Em empate, menor número de saltos; persistindo o empate, menor router-id — desempate determinístico para garantir que todos os nós cheguem à mesma decisão e não haja loop transitório.

**Descoberta de vizinhos.** A cada 2 s, cada roteador envia um `HELLO` em UDP porta 5555 para o endereço do outro lado de cada enlace `/30`. O vizinho responde com um `ECHO` que devolve o timestamp original. O emissor calcula `RTT = agora − ts_original` e o custo do enlace como `max(1, RTT/2)` em milissegundos. O valor entra numa média móvel exponencial com α = 0.3, para não reagir a um único pacote atrasado.

**Detecção de falha.** Três `HELLO` sem resposta — 6 s — declaram o vizinho morto. Escolha justificada: 6 s é rápido o bastante para uma demonstração de 5 minutos e lento o bastante para não gerar falso positivo com o jitter do `netem`.

**Difusão de estado (LSA).** Cada roteador mantém um número de sequência próprio. Ele emite um LSA quando: (a) um vizinho nasce ou morre; (b) o custo de um enlace varia mais de 20% em relação ao último valor anunciado; ou (c) passaram 30 s desde o último anúncio (refresh periódico). O LSA carrega o router-id de origem, o número de sequência, o mapa `vizinho → custo` e a lista de prefixos diretamente conectados.

O limiar de 20% é uma decisão de projeto deliberada e vale explicar na apresentação: sem ele, como a métrica é uma medição ruidosa e não um número configurado, qualquer variação de microssegundo geraria uma inundação. O limiar troca precisão por estabilidade — é o mesmo dilema que o OSPF resolve por não medir nada.

**Inundação.** Ao receber um LSA, o roteador compara o número de sequência com o que tem na base. Se for mais novo, armazena e retransmite para todos os vizinhos exceto aquele de quem recebeu (split horizon na inundação). Se for igual ou mais velho, descarta. Isso termina a inundação em tempo finito sem precisar de ACK.

**Cálculo e instalação.** Após qualquer mudança na base, roda Dijkstra a partir de si mesmo. Para cada prefixo remoto, identifica o primeiro salto no caminho mais curto e instala a rota via netlink com `proto 200`. O uso de um número de protocolo próprio permite remover exatamente as rotas do LARP sem tocar nas conectadas.

**Limitações assumidas (dizer isto na apresentação antes que perguntem):** sem autenticação; sem áreas, logo escalabilidade limitada pelo O(n²) da base de estado; sem suporte a múltiplos caminhos de custo igual; a métrica de latência pode oscilar sob carga, o que em rede real exigiria histerese mais forte.

### 8.2 `src/larpd.py`

```python
#!/usr/bin/env python3
"""larpd — Latency-Aware Routing Protocol daemon."""
import heapq
import json
import os
import socket
import subprocess
import sys
import threading
import time

PORT = 5555
HELLO_INTERVAL = 2.0
DEAD_AFTER = 6.0
LSA_REFRESH = 30.0
COST_THRESHOLD = 0.20
ALPHA = 0.3
RT_PROTO = 200


def log(*a):
    print(f"[{time.time():.3f}]", *a, flush=True)


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout


def discover_interfaces():
    """Retorna (p2p, stubs) lidos do próprio kernel."""
    import ipaddress
    out = json.loads(sh("ip -j -4 addr show"))
    p2p, stubs = [], []
    for link in out:
        name = link["ifname"]
        if name == "lo":
            continue
        for a in link.get("addr_info", []):
            net = ipaddress.ip_network(f"{a['local']}/{a['prefixlen']}", strict=False)
            if a["prefixlen"] == 30:
                peer = [str(h) for h in net.hosts() if str(h) != a["local"]][0]
                p2p.append({"iface": name, "local": a["local"], "peer": peer,
                            "net": str(net)})
            else:
                stubs.append(str(net))
    return p2p, stubs


class Larp:
    def __init__(self, rid):
        self.rid = rid
        self.p2p, self.stubs = discover_interfaces()
        self.neighbors = {}        # peer_ip -> {rid, cost, last_seen, iface}
        self.lsdb = {}             # rid -> {seq, links{}, stubs[]}
        self.seq = 0
        self.announced = {}        # rid_vizinho -> custo do último anúncio
        self.lock = threading.Lock()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", PORT))
        log(f"larpd {rid} up — {len(self.p2p)} enlaces, stubs={self.stubs}")

    # ---------- envio ----------
    def send(self, ip, msg):
        try:
            self.sock.sendto(json.dumps(msg).encode(), (ip, PORT))
        except OSError as e:
            log("send falhou", ip, e)

    def hello_loop(self):
        while True:
            for link in self.p2p:
                self.send(link["peer"], {"t": "hello", "rid": self.rid,
                                         "ts": time.time()})
            time.sleep(HELLO_INTERVAL)

    def maintenance_loop(self):
        last_refresh = 0.0
        while True:
            time.sleep(1.0)
            now = time.time()
            changed = False
            with self.lock:
                for ip in list(self.neighbors):
                    if now - self.neighbors[ip]["last_seen"] > DEAD_AFTER:
                        log("vizinho morto:", self.neighbors[ip]["rid"])
                        del self.neighbors[ip]
                        changed = True
            if changed or now - last_refresh > LSA_REFRESH:
                last_refresh = now
                self.originate_lsa()
                self.recompute()

    # ---------- recepção ----------
    def recv_loop(self):
        while True:
            data, addr = self.sock.recvfrom(65535)
            try:
                msg = json.loads(data.decode())
            except ValueError:
                continue
            t = msg.get("t")
            if t == "hello":
                self.send(addr[0], {"t": "echo", "rid": self.rid, "ts": msg["ts"]})
                self.touch(addr[0], msg["rid"])
            elif t == "echo":
                self.on_echo(addr[0], msg)
            elif t == "lsa":
                self.on_lsa(addr[0], msg)

    def touch(self, ip, rid):
        with self.lock:
            n = self.neighbors.setdefault(ip, {"rid": rid, "cost": None,
                                               "last_seen": 0.0, "iface": None})
            n["rid"] = rid
            n["last_seen"] = time.time()
            if n["iface"] is None:
                for l in self.p2p:
                    if l["peer"] == ip:
                        n["iface"] = l["iface"]

    def on_echo(self, ip, msg):
        rtt_ms = (time.time() - msg["ts"]) * 1000.0
        cost = max(1.0, rtt_ms / 2.0)
        self.touch(ip, msg["rid"])
        with self.lock:
            n = self.neighbors[ip]
            n["cost"] = cost if n["cost"] is None else (
                ALPHA * cost + (1 - ALPHA) * n["cost"])
            new = n["cost"]
            old = self.announced.get(n["rid"])
        if old is None or abs(new - old) / old > COST_THRESHOLD:
            self.originate_lsa()
            self.recompute()

    def on_lsa(self, from_ip, msg):
        origin, seq = msg["origin"], msg["seq"]
        with self.lock:
            known = self.lsdb.get(origin)
            if known and seq <= known["seq"]:
                return
            self.lsdb[origin] = {"seq": seq, "links": msg["links"],
                                 "stubs": msg["stubs"]}
            peers = [ip for ip in self.neighbors if ip != from_ip]
        for ip in peers:
            self.send(ip, msg)
        self.recompute()

    # ---------- estado ----------
    def originate_lsa(self):
        with self.lock:
            self.seq += 1
            links = {n["rid"]: round(n["cost"], 3)
                     for n in self.neighbors.values() if n["cost"] is not None}
            self.announced = dict(links)
            lsa = {"t": "lsa", "origin": self.rid, "seq": self.seq,
                   "links": links, "stubs": self.stubs}
            self.lsdb[self.rid] = {"seq": self.seq, "links": links,
                                   "stubs": self.stubs}
            peers = list(self.neighbors)
        for ip in peers:
            self.send(ip, lsa)

    def dijkstra(self):
        dist = {self.rid: 0.0}
        first = {}
        pq = [(0.0, self.rid, None)]
        seen = set()
        while pq:
            d, u, fh = heapq.heappop(pq)
            if u in seen:
                continue
            seen.add(u)
            if fh:
                first[u] = fh
            for v, c in self.lsdb.get(u, {}).get("links", {}).items():
                nd = d + c
                if nd < dist.get(v, float("inf")):
                    dist[v] = nd
                    heapq.heappush(pq, (nd, v, fh or v))
        return dist, first

    def recompute(self):
        with self.lock:
            dist, first = self.dijkstra()
            rid_to_ip = {n["rid"]: (ip, n["iface"])
                         for ip, n in self.neighbors.items()}
            lsdb = dict(self.lsdb)
            mine = set(self.stubs)

        desired = {}
        for rid, entry in lsdb.items():
            if rid == self.rid:
                continue
            hop = first.get(rid)
            if hop is None or hop not in rid_to_ip:
                continue
            gw, iface = rid_to_ip[hop]
            for prefix in entry["stubs"]:
                if prefix in mine:
                    continue
                cur = desired.get(prefix)
                if cur is None or dist[rid] < cur[2]:
                    desired[prefix] = (gw, iface, dist[rid])

        sh(f"ip route flush proto {RT_PROTO}")
        for prefix, (gw, iface, cost) in desired.items():
            sh(f"ip route replace {prefix} via {gw} dev {iface} proto {RT_PROTO}")
        log("rotas:", {p: v[0] for p, v in desired.items()})

    def run(self):
        for fn in (self.recv_loop, self.hello_loop, self.maintenance_loop):
            threading.Thread(target=fn, daemon=True).start()
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            sh(f"ip route flush proto {RT_PROTO}")


if __name__ == "__main__":
    rid = os.environ.get("LARP_RID") or sys.argv[1]
    Larp(rid).run()
```

### 8.3 Subir o daemon

```bash
for i in 1 2 3 4 5; do
  docker exec -d clab-routing-lab-R$i \
    sh -c "LARP_RID=10.255.0.$i larpd > /var/log/larpd.log 2>&1"
done
```

### 8.4 Ordem de teste (não pule)

1. Teste `discover_interfaces()` isolado dentro de um container — confirme que os `/30` e a LAN aparecem certos.
2. Suba o daemon em **dois** roteadores vizinhos apenas. Confirme HELLO/ECHO e custo estabilizando perto do valor do `netem`.
3. Suba em **três** em linha. Confirme que a inundação chega ao terceiro e que o do meio não retransmite em loop.
4. Só então os cinco.

Depurar inundação com cinco nós de uma vez é a forma mais rápida de perder um dia inteiro.

---

## 9. Coleta de métricas

### 9.1 `scripts/impair.sh`

```bash
#!/usr/bin/env bash
# Aplica banda e latência em cada enlace conforme topology.py
set -e
apply() {  # nó iface latencia_ms banda_mbit
  containerlab tools netem set -n clab-routing-lab-$1 -i $2 --delay ${3}ms --rate ${4}
}
apply R1 eth1 30 100mbit ; apply R2 eth1 30 100mbit
apply R2 eth2 30 100mbit ; apply R3 eth1 30 100mbit
apply R3 eth2 30 100mbit ; apply R4 eth1 30 100mbit
apply R1 eth2  1  10mbit ; apply R5 eth2  1  10mbit
apply R4 eth2  1  10mbit ; apply R5 eth1  1  10mbit
apply R2 eth3  5  10mbit ; apply R5 eth3  5  10mbit
apply R1 eth3 100  1mbit ; apply R4 eth3 100  1mbit
echo "impairments aplicados"
```

### 9.2 `scripts/run.sh`

```bash
#!/usr/bin/env bash
# run.sh rip|ospf|larp
set -e
MODE=$1
[[ "$MODE" =~ ^(rip|ospf|larp)$ ]] || { echo "uso: run.sh rip|ospf|larp"; exit 1; }

sudo containerlab destroy -t topology.clab.yml --cleanup 2>/dev/null || true
python3 src/gen_configs.py
MODE=$MODE sudo -E containerlab deploy -t topology.clab.yml
sleep 5
bash scripts/impair.sh

if [ "$MODE" = "larp" ]; then
  for i in 1 2 3 4 5; do
    docker exec -d clab-routing-lab-R$i \
      sh -c "LARP_RID=10.255.0.$i larpd > /var/log/larpd.log 2>&1"
  done
fi

echo "modo $MODE ativo — aguardando convergência inicial"
sleep 30
```

### 9.3 `src/collect.py`

```python
#!/usr/bin/env python3
"""Coletor de métricas. Uso: collect.py <modo> <duracao_s>"""
import csv, os, re, subprocess, sys, threading, time

MODE = sys.argv[1]
DURATION = int(sys.argv[2])
ROUTERS = [f"R{i}" for i in range(1, 6)]
OUT = f"results/{MODE}"
os.makedirs(OUT, exist_ok=True)

FILTER = {"rip": "udp port 520", "ospf": "proto 89", "larp": "udp port 5555"}[MODE]


def dexec(node, cmd):
    return subprocess.run(["docker", "exec", f"clab-routing-lab-{node}", "sh", "-c", cmd],
                          capture_output=True, text=True).stdout


def table_sizes():
    """Tamanho da tabela de roteamento ao longo do tempo."""
    with open(f"{OUT}/table.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["t", "router", "rotas"])
        t0 = time.time()
        while time.time() - t0 < DURATION:
            t = round(time.time() - t0, 1)
            for r in ROUTERS:
                n = len([l for l in dexec(r, "ip route show").splitlines() if l.strip()])
                w.writerow([t, r, n])
            f.flush()
            time.sleep(1.0)


def control_traffic():
    """Pacotes e bytes de controle vistos em R1."""
    p = subprocess.Popen(
        ["docker", "exec", "clab-routing-lab-R1", "tcpdump", "-l", "-n", "-i", "any",
         "-tt", "-q", FILTER],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    with open(f"{OUT}/control.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["t_abs", "bytes"])
        for line in p.stdout:
            m = re.search(r"length (\d+)", line)
            ts = line.split()[0] if line.split() else None
            if m and ts:
                w.writerow([ts, m.group(1)]); f.flush()


def latency():
    """RTT fim a fim h1 -> h4, 5 amostras/s."""
    p = subprocess.Popen(
        ["docker", "exec", "clab-routing-lab-h1", "ping", "-i", "0.2", "-D",
         "192.168.4.10"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    with open(f"{OUT}/latency.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["t_abs", "rtt_ms"])
        for line in p.stdout:
            m = re.search(r"\[(\d+\.\d+)\].*time=([\d.]+) ms", line)
            if m:
                w.writerow([m.group(1), m.group(2)]); f.flush()


def paths():
    """Caminho escolhido, amostrado a cada 5s — evidência do slide central."""
    with open(f"{OUT}/path.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["t", "hops"])
        t0 = time.time()
        while time.time() - t0 < DURATION:
            out = dexec("h1", "traceroute -n -q1 -w1 192.168.4.10")
            hops = " ".join(re.findall(r"\d+\.\d+\.\d+\.\d+", out))
            w.writerow([round(time.time() - t0, 1), hops]); f.flush()
            time.sleep(5.0)


if __name__ == "__main__":
    ts = [threading.Thread(target=fn, daemon=True)
          for fn in (table_sizes, control_traffic, latency, paths)]
    for t in ts: t.start()
    time.sleep(DURATION)
    print(f"coleta de {MODE} concluída em {OUT}/")
```

Os pacotes perdidos no `latency.csv` são a métrica de convergência: cada lacuna de 0.2 s na série temporal é 0.2 s de indisponibilidade. Não precisa de instrumentação extra — a ausência de dado *é* o dado.

### 9.4 `scripts/scenario.sh` — o roteiro cronometrado

```bash
#!/usr/bin/env bash
# scenario.sh rip|ospf|larp — 300s de eventos idênticos nas três execuções
set -e
MODE=$1
bash scripts/run.sh $MODE
python3 src/collect.py $MODE 300 &
COLLECTOR=$!

down() { sudo ip link set $(sudo containerlab inspect -t topology.clab.yml -f json \
         | python3 -c "import json,sys;print('')") down 2>/dev/null || \
         docker exec clab-routing-lab-$1 ip link set $2 down; }
up()   { docker exec clab-routing-lab-$1 ip link set $2 up; }

sleep 60  ; echo "t=60  derrubando satélite R1-R4"  ; down R1 eth3
sleep 60  ; echo "t=120 restaurando satélite"        ; up   R1 eth3
sleep 60  ; echo "t=180 derrubando backbone R2-R3"   ; down R2 eth2
sleep 60  ; echo "t=240 restaurando + degradando R1-R5 para 200ms"
            up R2 eth2
            containerlab tools netem set -n clab-routing-lab-R1 -i eth2 --delay 200ms --rate 10mbit
sleep 60  ; echo "t=300 fim"

wait $COLLECTOR
```

Cada evento estressa uma solução diferente, e essa é a graça:

| Evento | RIP | OSPF | LARP |
|---|---|---|---|
| t=60 queda do satélite | perde a rota que usava — convergência lenta e visível | indiferente, não usava | indiferente, não usava |
| t=180 queda do backbone | indiferente | perde a rota que usava — reconverge para via R5 | indiferente |
| t=240 degradação de R1-R5 | cego, não vê latência | cego, custo é estático | reconverge — única solução que reage |

Isso responde diretamente o que o enunciado pede sobre "comportamento em situações de mudança da topologia", com evidência para cada uma das três soluções.

### 9.5 `src/plot.py` — os gráficos

Quatro figuras, uma por métrica, com as três soluções sobrepostas e linhas verticais marcando os eventos:

```python
#!/usr/bin/env python3
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd, os

MODES = ["rip", "ospf", "larp"]
LABEL = {"rip": "RIPv2", "ospf": "OSPFv2", "larp": "LARP (proposto)"}
EVENTS = [(60, "queda satélite"), (120, "restauro"),
          (180, "queda backbone"), (240, "degradação R1-R5")]
os.makedirs("figs", exist_ok=True)


def marks(ax):
    for t, lbl in EVENTS:
        ax.axvline(t, color="gray", ls="--", lw=0.8)
        ax.text(t + 2, ax.get_ylim()[1] * 0.95, lbl, fontsize=7, rotation=90,
                va="top", color="gray")


def fig_table():
    fig, ax = plt.subplots(figsize=(8, 4))
    for m in MODES:
        d = pd.read_csv(f"results/{m}/table.csv")
        d = d.groupby("t")["rotas"].mean()
        ax.plot(d.index, d.values, label=LABEL[m])
    ax.set_xlabel("tempo (s)"); ax.set_ylabel("entradas na tabela (média dos 5 nós)")
    ax.set_title("Tamanho da tabela de roteamento"); ax.legend(); marks(ax)
    fig.tight_layout(); fig.savefig("figs/tabela.png", dpi=160)


def fig_control():
    fig, ax = plt.subplots(figsize=(8, 4))
    for m in MODES:
        d = pd.read_csv(f"results/{m}/control.csv")
        d["t"] = d["t_abs"] - d["t_abs"].min()
        s = d.groupby(d["t"].astype(int))["bytes"].sum().rolling(5).mean()
        ax.plot(s.index, s.values, label=LABEL[m])
    ax.set_xlabel("tempo (s)"); ax.set_ylabel("bytes de controle / s (média móvel 5s)")
    ax.set_title("Consumo de banda pelo plano de controle"); ax.legend(); marks(ax)
    fig.tight_layout(); fig.savefig("figs/controle.png", dpi=160)


def fig_latency():
    fig, ax = plt.subplots(figsize=(8, 4))
    for m in MODES:
        d = pd.read_csv(f"results/{m}/latency.csv")
        d["t"] = d["t_abs"] - d["t_abs"].min()
        ax.plot(d["t"], d["rtt_ms"], label=LABEL[m], lw=0.8)
    ax.set_xlabel("tempo (s)"); ax.set_ylabel("RTT h1→h4 (ms)")
    ax.set_title("Latência fim a fim — lacunas indicam indisponibilidade")
    ax.legend(); marks(ax)
    fig.tight_layout(); fig.savefig("figs/latencia.png", dpi=160)


def fig_convergence():
    """Tempo sem conectividade por evento, derivado das lacunas do ping."""
    rows = []
    for m in MODES:
        d = pd.read_csv(f"results/{m}/latency.csv")
        d["t"] = d["t_abs"] - d["t_abs"].min()
        gaps = d["t"].diff()
        for t_evt, lbl in EVENTS:
            w = d[(d["t"] > t_evt) & (d["t"] < t_evt + 60)]
            g = gaps.loc[w.index]
            rows.append({"modo": LABEL[m], "evento": lbl,
                         "downtime": max(0.0, g.max() - 0.2) if len(g) else 0.0})
    p = pd.DataFrame(rows).pivot(index="evento", columns="modo", values="downtime")
    ax = p.plot.bar(figsize=(8, 4), rot=15)
    ax.set_ylabel("indisponibilidade (s)"); ax.set_title("Tempo de convergência por evento")
    ax.figure.tight_layout(); ax.figure.savefig("figs/convergencia.png", dpi=160)


if __name__ == "__main__":
    fig_table(); fig_control(); fig_latency(); fig_convergence()
    print("figuras em figs/")
```

Resultados esperados, para você saber se algo deu errado: RIP com tráfego de controle constante e alto (tabela inteira a cada 30 s, independente de haver mudança); OSPF baixo em regime e com picos nos eventos; LARP intermediário e constante por causa dos HELLOs de 2 s. Na convergência, RIP na casa de dezenas de segundos, OSPF em poucos segundos, LARP em ~6 s (o `DEAD_AFTER`). Se o RIP convergir em 3 s, alguma coisa está errada na sua medição.

---

## 10. Validação antes de gravar o vídeo

```bash
# Caminho escolhido por cada solução (o slide central)
docker exec clab-routing-lab-h1 traceroute -n 192.168.4.10

# Esperado — RIP:  192.168.1.1 → 10.0.14.2 → 192.168.4.10
# Esperado — OSPF: 192.168.1.1 → 10.0.12.2 → 10.0.23.2 → 10.0.34.2 → ...
# Esperado — LARP: 192.168.1.1 → 10.0.15.2 → 10.0.45.1 → 192.168.4.10

# Estado dos protocolos
docker exec clab-routing-lab-R1 vtysh -c "show ip rip"
docker exec clab-routing-lab-R1 vtysh -c "show ip ospf neighbor"
docker exec clab-routing-lab-R1 vtysh -c "show ip ospf route"
docker exec clab-routing-lab-R1 tail -20 /var/log/larpd.log

# Conectividade total (todos contra todos)
for i in 1 2 3 4 5; do for j in 1 2 3 4 5; do
  [ $i -ne $j ] && docker exec clab-routing-lab-h$i ping -c1 -W1 192.168.$j.10 >/dev/null \
    && echo "h$i->h$j OK" || echo "h$i->h$j FALHOU"
done; done
```

Se os três traceroutes derem o mesmo caminho, revise os valores de `netem` e os custos OSPF — o contraste é o produto central do trabalho.

---

## 11. Entregáveis

### README.md — mínimo aceitável

O enunciado pede "a descrição de sua utilização". O professor deve conseguir reproduzir sem te perguntar nada:

1. Pré-requisitos, com versões (Docker, Containerlab, Python).
2. Build da imagem — um comando.
3. Execução — `sudo bash scripts/scenario.sh ospf` e nada mais.
4. Diagrama da topologia (exporte a figura) e tabela de endereçamento.
5. Descrição do LARP: princípio, métrica, formato das mensagens, critérios de seleção.
6. Resultados: as quatro figuras embutidas com dois parágrafos de análise cada.
7. Link para o vídeo.

### Vídeo — roteiro de 5 a 6 minutos

| Tempo | Conteúdo |
|---|---|
| 0:00–0:30 | Topologia na tela, o que cada enlace representa |
| 0:30–1:30 | `run.sh rip`, mostrar `show ip rip`, traceroute pelo satélite |
| 1:30–2:30 | `run.sh ospf`, mostrar `show ip ospf route`, traceroute pelo backbone |
| 2:30–3:30 | `run.sh larp`, log do daemon com os custos medidos, traceroute via R5 |
| 3:30–5:00 | Teste de falha: ping rodando, derruba enlace, tempo até voltar em cada solução |
| 5:00–5:30 | Os quatro gráficos |

Grave com `wf-recorder` ou OBS. Terminal em fonte grande — vídeo de terminal ilegível é reclamação comum de professor.

### Apresentação — 10 minutos, e o item 10 vale 1.0

Oito slides, não mais:

1. Objetivo e escolha da plataforma (FRR como sucessor do Quagga) — 1 min
2. Topologia e endereçamento — 1 min
3. RIPv2: princípio e configuração — 1 min
4. OSPFv2: princípio e configuração — 1 min
5. LARP: métrica, mensagens, critérios de seleção — 2 min
6. **Os três caminhos diferentes para h1→h4** — 1,5 min
7. Gráficos e análise — 1,5 min
8. Conclusão: qual solução para qual cenário — 1 min

Ensaie com cronômetro pelo menos duas vezes. Dez minutos passam rápido e o slide 5 é o que você vai querer esticar.

---

## 12. Cronograma — 24 dias, individual

| Datas | Entrega | Por que nesta ordem |
|---|---|---|
| 7–9 set | Docker, Containerlab, imagem, topologia sobe, vizinhos se pingam | Sem isto nada mais existe |
| 10–16 set | **`larpd.py` funcionando nos 5 nós** | Único item com risco real de não funcionar — vai primeiro |
| 17–19 set | Configs RIP e OSPF, validação dos três caminhos | Trinta minutos cada; podem esperar sem risco |
| 20–23 set | Coletor, `scenario.sh`, três execuções, quatro gráficos | Precisa das três soluções prontas |
| 24–26 set | README completo e vídeo | |
| 27–29 set | Slides e dois ensaios cronometrados | |
| 30 set | Buffer | Algo vai dar errado; reserve o dia |
| 1 out, até 19h | Submissão no Moodle + push final no GitHub | |

O marco que importa: **se em 16/9 o `larpd` não estiver instalando rotas nos cinco nós, corte para a versão centralizada** (um processo no host que lê a topologia, roda Dijkstra e empurra rotas por `docker exec`). Perde elegância, mantém os 2.0 dos itens 4 e 5. Decidir isso em 16/9 é gestão de risco; descobrir em 29/9 é perder nota.

---

## 13. Riscos e mitigações

| Risco | Sinal de alerta | Mitigação |
|---|---|---|
| Inundação de LSA em loop | CPU a 100%, log rolando sem parar | Testar com 2 e 3 nós antes de 5; conferir a checagem de número de sequência |
| `netem` não aplica no Containerlab | Latências medidas todas iguais | Alternativa: `docker exec ... tc qdisc add dev ethN root netem delay Xms` |
| Rotas do LARP conflitando com as do zebra | Tráfego indo por caminho inesperado | `proto 200` isola; conferir com `ip route show proto 200` |
| Três execuções com timing diferente | Eventos desalinhados nos gráficos | `scenario.sh` é a única forma de executar — nunca rodar comandos soltos |
| Apresentação estourando 10 min | — | Dois ensaios cronometrados; o item 10 vale 1.0 inteiro |

---

## 14. Mapa dos itens de avaliação

| Item | Valor | Onde está resolvido |
|---|---|---|
| 1. Organização da apresentação | 1.0 | Seção 11, oito slides |
| 2. Instalar e configurar a plataforma | 1.0 | Seções 2 e 7 |
| 3. Topologias física e lógica | 1.0 | Seções 4, 6 e o diagrama |
| 4. Propor o algoritmo, justificando | 1.0 | Seção 8.1 |
| 5. Configurar os dois protocolos e implementar o algoritmo | 1.0 | Seções 7, 8.2 e o isolamento por modo |
| 6. Coletar métricas | 1.0 | Seção 9.3, quatro métricas |
| 7. Comparar com gráficos | 1.0 | Seção 9.5, quatro figuras |
| 8. Vídeo | 1.0 | Seção 11, roteiro |
| 9. Apresentação e demonstração | 1.0 | Seção 11 |
| 10. Respeito ao tempo | 1.0 | Ensaio cronometrado |

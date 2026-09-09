# Roteamento IP — Lab Containerlab/FRR + LARP

Trabalho I — Fundamentos de Sistemas Operacionais (Redes 2) · Unisinos.

Lab de **5 roteadores FRR + 5 hosts Alpine** em Containerlab, com três modos de
roteamento isolados (`rip` | `ospf` | `larp`) sobre a **mesma** topologia. Este
README é o **rascunho de M1**; a versão completa (diagrama, tabela de
endereçamento, descrição do LARP, figuras e análise) chega no marco M4.

> Design record: `relatorio-trabalho-roteamento.md` · Spec: `specs/SPEC-roteamento-ip.md`.

## Status do marco

**M1 — preparado, validação do lab pendente de privilégio.** Imagem `frr-larp:latest`
buildada, `topology.py` como fonte da verdade, manifestos/configs/impairments
gerados, pings de vizinhança derivados do gerador. **Bloqueio conhecido**: o
Containerlab (CLI `deploy`/`destroy`/`inspect`) exige root ou SUID para criar os
enlaces veth — o grupo `docker` não basta. Veja "Nota sobre privilégios" abaixo.
O `verify.sh` por modo é de M2/M3 (D14).

## Pré-requisitos

- **Zorin OS 18.1 / Ubuntu noble** (`UBUNTU_CODENAME=noble`)
- **Docker Engine** (testado em 29.7.2) com o usuário no grupo `docker`
- **Containerlab** (testado em 0.79.0), instalado em modo usuário por `bootstrap.sh`
- **Python 3** (testado em 3.12) — `pytest`/`matplotlib` opcionais (best-effort, M2/M4)

Confirme o contexto Docker (armadilha nº 1): `docker context show` deve dizer
`default`. Se estiver `desktop-linux` (socket morto), rode `docker context use default`.

## Roteiro rápido

```bash
# 1. Preparo do host (idempotente; não usa sudo)
bash scripts/bootstrap.sh

# 2. Build da imagem única
bash scripts/build.sh

# 3. Subir o lab (destrói o lab anterior, regenera configs, deploy)
bash scripts/run.sh larp        # ou rip / ospf

# 4. Pings de vizinhança (R–R e R–host) — evidência do gate M1
bash scripts/check_pings.sh

# 5. Derrubar tudo sem resíduo
containerlab destroy -t topology.clab.yml --cleanup
```

## Estrutura do repositório

```
├── topology.py              # fonte da verdade (topologia + endereçamento)
├── topology.clab.yml        # GERADO por src/gen_configs.py  (não editar à mão)
├── configs/                 # GERADO: rip|ospf|larp/R1..R5/{frr.conf,daemons}
├── src/
│   ├── gen_configs.py       # gerador único (configs + manifesto + impair)
│   └── larpd.py             # daemon LARP (stub em M1; implementação em M2)
├── docker/Dockerfile        # imagem única frr-larp:latest (FRR 9.1.0 + ferramentas)
├── scripts/
│   ├── bootstrap.sh         # preparo idempotente do host (sem sudo)
│   ├── build.sh             # build da imagem
│   ├── run.sh               # subir o lab por modo
│   ├── check_pings.sh       # pings de vizinhança derivados de topology.py
│   └── impair.sh            # GERADO: aplica netem (banda/latência) nos enlaces
├── results/  figs/          # ignorados até M4 (D17)
└── specs/  relatorio-trabalho-roteamento.md   # design record (não alterar)
```

## Arquivos gerados

`topology.clab.yml`, `configs/**` e `scripts/impair.sh` são **derivados** de
`topology.py`. Regenerar (sempre que mudar a topologia):

```bash
python3 src/gen_configs.py
```

Não edite esses arquivos à mão — edite `topology.py` e regenere (D3).

## Nota sobre privilégios

O Containerlab (v0.79.0) exige **root ou SUID** mesmo com o usuário no grupo
`docker` (checagem interna `CheckAndGetRootPrivs`; os enlaces são veth criados no
netns do host). Neste host `sudo` exige senha — os scripts **nunca** chamam
`sudo` nem travam esperando. Opções para destravar o lab (decisão do usuário):

1. **SUID no binário (uma vez):** `sudo chown root:root ~/containerlab/bin/containerlab && sudo chmod u+s ~/containerlab/bin/containerlab` — a partir daí roda sem `sudo`.
2. **`sudo bash scripts/run.sh <modo>`** na demonstração (interativo).

Além disso, o FRR 9.1.0 (imagem do relatório) exige `CAP_SYS_ADMIN` no container
(`privs_init` do zebra morre sem ele — verificado neste host). O gerador já
emite `cap-add: [NET_ADMIN, NET_RAW, SYS_ADMIN]` (D5 + divergência documentada
em `src/gen_configs.py`).

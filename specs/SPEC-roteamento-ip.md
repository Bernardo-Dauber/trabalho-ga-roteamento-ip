---
title: "Trabalho I — Roteamento IP: implementação do lab Containerlab/FRR com protocolo próprio LARP"
disciplina: Fundamentos de Sistemas Operacionais (Redes 2) — Unisinos
status: ready-for-agent
tipo: spec de implementação (PRD)
documento de design: relatorio-trabalho-roteamento.md (registro de decisões e protótipo; citado por seção)
seams aprovadas:
  - primária: topologia viva fim-a-fim (smoke `verify.sh <modo>` + verificação offline dos resultados)
  - secundária: testes unitários da lógica pura do LARP (pytest, sem Docker)
fora de seam (deliberado): golden-file de configs geradas
data: 2026-09-07 (ciclo 2026/2)
---

# Trabalho I — Roteamento IP (spec de implementação)

> Documento-irmão do relatório de implementação (`relatorio-trabalho-roteamento.md`).
> O relatório é o **registro de design e protótipo**; esta spec é a **ordem de serviço
> para implementar** o que lá foi definido. Toda seção citada como "§N" refere-se ao relatório.
> Quando esta spec decide algo que o relatório deixa em aberto, a decisão está marcada como **[abre]**.

## Declaração do problema

O trabalho acadêmico exige implementar e comparar três soluções de roteamento IP sobre a
**mesma** topologia física: (1) RIPv2, (2) OSPFv2 — ambos configurados em um daemon real — e
(3) um **algoritmo de roteamento próprio**, proposto e justificado, implementado de verdade.
A comparação precisa ser quantitativa (métricas coletadas e grafadas) e o professor precisa
**reproduzir tudo** sem assistência.

Hoje o repositório contém apenas o relatório de design: não há código, imagem, topologia
subindo, protocolos configurados, algoritmo implementado, coletor de métricas, gráficos,
README nem roteiro de demonstração. O host de desenvolvimento (Zorin 18.1 / Ubuntu noble)
tem Docker funcional (usuário no grupo `docker`) mas **não tem Containerlab instalado**,
**não tem matplotlib nem pytest**, e **`sudo` exige senha** — o que inviabiliza scripts que
assumam `sudo` silencioso.

O objetivo desta spec é fechar, com profundidade, **o que** implementar, **em que ordem**
(com critérios de saída verificáveis), **onde** testar (seams) e **o que fica fora** — para
que a implementação caminhe sozinha até o estado "reproduzível pelo professor", cobrindo os
10 itens de avaliação (§14).

## Solução

Um repositório autocontido e reproduzível em três camadas:

1. **Infraestrutura versionável** — uma topologia de 5 roteadores + 5 hosts, expressa numa
   única fonte da verdade (`topology.py`, §5), da qual derivam o manifesto Containerlab, os
   impairments (`netem`) e todas as checagens de consistência. O lab sobe com um comando.
2. **Três soluções de roteamento isoladas por "modo"** (`rip` | `ospf` | `larp`) — configs
   FRR geradas (§7), onde o modo `larp` deixa **visível** que RIP/OSPF estão desligados
   (daemons `no`, só zebra), atendendo o requisito do enunciado sem depender de explicação.
3. **O LARP — Latency-Aware Routing Protocol** (§8) — daemon próprio, distribuído, de estado
   de enlace com métrica ativa de latência, instalando rotas reais por netlink com `proto 200`.

Sobre isso, uma camada de **evidência**: cenário cronometrado idêntico nos três modos
(§9.4), coletor de 4 métricas em CSV (§9.3), 4 figuras comparativas (§9.5), e — novo nesta
spec — um **harness de verificação** que afirma o comportamento observável (caminhos
distintos, conectividade, reações a eventos, limites de convergência).

O produto central a ser provado: para `h1 → h4` as três soluções escolhem **caminhos
diferentes, cada um correto na própria métrica** (§4.4), e a mudança de topologia durante o
cenário produz reações distintas e esperadas (§9.4) — RIP só reage à queda do satélite,
OSPF à queda do backbone, LARP é o único que reage à degradação de latência.

## Histórias de usuário

### Estudante que executa os experimentos

1. Como estudante, eu quero instalar o ambiente com um roteiro verificável, para que eu não
   perca dias com a armadilha de distros derivadas do Ubuntu (§2.1).
2. Como estudante, eu quero que a topologia esteja declarada em **um único lugar**, para que
   mudar um enlace não me obrigue a editar configs, manifesto e impairments em paralelo.
3. Como estudante, eu quero subir o lab com um comando por modo (`run.sh rip|ospf|larp`),
   para que as três execuções sejam comparáveis e o roteiro da demonstração seja curto.
4. Como estudante, eu quero que cada execução comece de um teardown completo, para que não
   haja estado residual (rotas, netem, containers) contaminando as métricas do modo seguinte.
5. Como estudante, eu quero que o modo `larp` desligue RIP e OSPF nos daemons, para que o
   professor veja na config que o algoritmo próprio não é enfeitado por um protocolo rodando.
6. Como estudante, eu quero que cada enlace tenha banda e latência reais aplicadas por
   `netem`, para que as métricas de cada solução reflitam a narrativa física (fibra longa =
   muita banda e latência; satélite = atalho barato em saltos, caro em latência).
7. Como estudante, eu quero derrubar e restaurar enlaces em tempos cronometrados idênticos
   nos três modos, para que os gráficos de convergência sejam comparáveis evento a evento.
8. Como estudante, eu quero verificar num passe o estado dos protocolos (`show ip rip`,
   `show ip ospf route`, log do LARP), para que a demonstração ao vivo flua sem improviso.
9. Como estudante, eu quero uma checagem de conectividade todos-contra-todos, para saber na
   hora se a execução está sã antes de gravar ou coletar.
10. Como estudante, eu quero rodar o cenário inteiro **sempre pelo mesmo script** (§9.4),
    para que a única forma de executar produza eventos alinhados nos três conjuntos de dados.

### Professor que avalia e reproduz

11. Como professor, eu quero reproduzir o trabalho com os pré-requisitos declarados e
    comandos mínimos (build de imagem + `scenario.sh <modo>`), para que eu não precise de
    assistência do aluno.
12. Como professor, eu quero que as três soluções escolham **caminhos distintos e
    previsíveis** para `h1 → h4`, para que a diferença entre métricas fique visível num
    traceroute (RIP via satélite, OSPF via backbone, LARP via R5).
13. Como professor, eu quero que RIP e OSPF usem daemons reais (FRR, sucessor do Quagga
    citado no enunciado), para que a configuração valha como "configurar os protocolos".
14. Como professor, eu quero ver o algoritmo próprio documentado (princípio, métrica,
    formato de mensagens, critérios de seleção) **e** funcionando, para avaliar o item 4/5
    com evidência, não com slide.
15. Como professor, eu quero que o modo `larp` rode sem nenhum daemon de roteamento
    dinâmico além do próprio, para que a implementação do aluno seja honesta.
16. Como professor, eu quero que a queda de um enlace durante o cenário produza
    indisponibilidade mensurável e convergência em tempos plausíveis por solução (RIP na
    casa de dezenas de segundos, OSPF em poucos segundos, LARP ~6 s), para que os dados
    confirmem a teoria de cada protocolo.
17. Como professor, eu quero que a degradação de latência de um enlace só mude a rota do
    LARP, para que fique provado que métrica dinâmica vê o que métrica estática não vê.
18. Como professor, eu quero tabelas CSV cruas e quatro figuras PNG reproduzíveis, para que
    eu possa conferir os números e não só a estética dos gráficos.
19. Como professor, eu quero um README com diagrama da topologia, tabela de endereçamento,
    descrição do LARP e as figuras com análise, para que o relatório escrito e o repositório
    se sustentem sozinhos.

### Estudante que analisa e apresenta

20. Como estudante, eu quero quatro gráficos sobrepostos (tabela, controle, latência,
    convergência) com marcadores verticais nos eventos, para que o slide de comparação se
    monte direto das figuras.
21. Como estudante, eu quero que as lacunas na série de ping sejam tratadas como métrica de
    indisponibilidade, para que convergência seja medida sem instrumentação extra.
22. Como estudante, eu quero um log do daemon LARP com os custos medidos por enlace, para
    mostrar na gravação que a métrica é medida em tempo real e converge perto do netem.
23. Como estudante, eu quero que os resultados da execução de demonstração fiquem
    commitados junto com as figuras, para que README e apresentação citem dados reais.
24. Como estudante, eu quero um resumo de execução (modo, commit, versões de ferramentas)
    gravado a cada coleta, para que a reprodutibilidade das figuras seja rastreável.

### Estudante desenvolvedor (loop de implementação)

25. Como desenvolvedor, eu quero testar o `larpd` em 2 nós, depois 3, depois 5 (§8.4), para
    que um bug de inundação não seja depurado com a topologia inteira de uma vez.
26. Como desenvolvedor, eu quero que a lógica pura do LARP (Dijkstra com desempate,
    EWMA, limiar, deduplicação de LSA) seja testável sem Docker nem root, para que decisões
    determinísticas sejam pinadas em testes e o E2E não seja a única rede de segurança.
27. Como desenvolvedor, eu quero um smoke de verificação rápido por modo (conectividade +
    caminho esperado), para saber em segundos se a execução está correta antes de rodar os
    300 s do cenário.
28. Como desenvolvedor, eu quero uma verificação offline dos CSVs após o cenário, para que
    as reações esperadas por evento (tabela §9.4) sejam afirmadas sem manter o lab de pé.
29. Como desenvolvedor, eu quero falhas localizáveis: se o E2E quebra, os testes unitários
    do LARP indicam se a causa é decisão interna (desempate/EWMA/seq) ou integração.
30. Como desenvolvedor, eu quero rodar a suíte sem depender de `sudo` silencioso, porque
    este host pede senha — containerlab precisa de root/SUID, nunca `sudo` mudo.

## Decisões de implementação

### D1 — O relatório é o registro de design; o código nasce do zero [abre]
O repositório não tem código nem git. O relatório (§§3–9) define estrutura-alvo, topologia e
protótipo de cada artefato. A implementação deve **reproduzir fielmente** o relatório e só
divergir onde esta spec (D4, D9, D10, D12, D14, D17, D18) decide algo em aberto — registrando
a divergência no próprio código/README para o relatório não virar uma promessa vazia.
Decisão: inicializar git na fase M1 e commitar por marco (D18), para que cada figura e
config entregue seja rastreável a um commit.

### D2 — Bootstrap do host, verificado; Containerlab exige root ou SUID [abre, revisado em M1]
Fatos do host (verificados): Zorin 18.1 (`UBUNTU_CODENAME=noble`), Docker 29.7.2 com o
usuário no grupo `docker`, **Containerlab ausente**, **matplotlib ausente**, **pytest
ausente**, pandas 3.0.3 presente, `sudo` exige senha.
Decisões:
- Instalar Containerlab pela via oficial (versão 0.79.0, em `~/containerlab/bin`) e
  **validar** com um lab de 2 nós antes de seguir (critério de saída de M1).
- **Correção empírica (M1):** o Containerlab **não roda pelo grupo `docker`** — `deploy`/
  `destroy`/`inspect`/`tools netem` exigem `euid=0` ou binário com SUID root
  (`CheckAndGetRootPrivs`) e criam veth no netns do host (precisa `CAP_NET_ADMIN` no host).
  Caminho padrão adotado: **SUID root no binário** (concessão única, feita pelo usuário com
  `sudo chown root:root ~/containerlab/bin/containerlab && sudo chmod u+s ~/containerlab/bin/containerlab`),
  que mantém os scripts sem `sudo` dali em diante. Alternativa para o host de demonstração:
  rodar `sudo bash scripts/run.sh <modo>` interativo. Os scripts nunca tentam `sudo -n`
  (falharia: senha obrigatória) nem travam esperando senha; se o binário não tiver SUID,
  o wrapper falha com mensagem acionável apontando o comando acima.
- Dependências Python do host: matplotlib e pytest instalados em modo usuário (PEP 668:
  `--break-system-packages` quando via pip). Nada disso entra na imagem dos nós.
- O comando do professor continua "um comando" (§11 do relatório) **no host já preparado**;
  o preparo fica documentado e verificado por um script idempotente de ambiente, não por
  página de tutorial.

### D3 — `topology.py` é a fonte da verdade; o manifesto é checado, não regerado
A topologia física e o endereçamento vivem em `topology.py` (§5). O manifesto Containerlab e
os comandos `netem` repetem esses dados em outras linguagens — repetição é fonte de drift
(risco real: "path errado" que o professor vê). Para não divergir do relatório (que mostra o
manifesto estático e legível, §6), a decisão é **gerar, não checar, o quê**:
- Decisão: manter `topology.clab.yml` e `impair.sh` como artefatos **gerados a partir de
  `topology.py`** por um gerador único (estende o `gen_configs.py` de §7 para emitir também o
  manifesto e os impairments), mantendo o formato literal do relatório na saída.
- O manifesto gerado preserva o placeholder `${MODE}` nos binds (expansão do Containerlab) e
  o bloco `kinds.linux` com `cap-add` (D5).
- **Correção empírica (M1):** a expansão `${MODE}` exige a variável no ambiente **de cada
  invocação** do Containerlab (deploy expande, mas `inspect` falha sem a env) — o `run.sh`
  prefixa `MODE=$MODE` em destroy/deploy/impair/inspect.
- **Correção empírica (M1):** `containerlab tools netem set --rate` aceita **kbit inteiro**,
  não `100mbit` (ParseUint error) — o gerador converte banda_mbit → kbit (×1000).
- Consequência: editar a topologia = editar um arquivo; regenerar = um comando; o README
  explica que o manifesto é derivado. Fica descartada a "config duplicada à mão".

### D4 — Uma única imagem para todos os nós e modos
Imagem `frr-larp:latest` (§2, Dockerfile): FRR 9.1.0 + Python 3, iperf3, tcpdump, traceroute,
iproute2, bind-tools e pyroute2 (mantido por fidelidade ao relatório, embora o `larpd` use
`iproute2` via subprocess e não dependa de pyroute2). O `larpd.py` é copiado para a imagem no
build; o build copia do `src/` (um comando, via script de build).
O **entrypoint padrão da imagem FRR** (`docker-start`) lê `/etc/frr` montado e sobe os
daemons declarados no `daemons` — é isso que faz zebra/ripd/ospfd rodarem nos nós `linux` do
Containerlab sem camada extra. O `larpd` roda **no mesmo container** dos roteadores, via
`docker exec -d` no `run.sh` (modo `larp`), com log em arquivo no container.
Validação de M2/M3: `ps` dentro do nó mostra exatamente os daemons esperados por modo.

### D5 — Privilégios dos nós e fallback AppArmor [revisado em M1]
Os nós `linux` precisam de capacidades para zebra/FRR, `larpd` e `tc`. **Correção empírica
(M1):** com só `NET_ADMIN`/`NET_RAW`, o FRR 9.1.0 morre com
`privs_init: initial cap_set_proc failed: Operation not permitted` — zebra/mgmtd exigem
`CAP_SYS_ADMIN` neste host (testado também com FRR 10.5.1). Decisão: declarar
`cap-add: ["NET_ADMIN", "NET_RAW", "SYS_ADMIN"]` no bloco `kinds.linux` do manifesto
(D5 + §2.5 previa ajuste de privilégios), documentado no código e no README. Se surgir
`Operation not permitted` no log do `larpd`, seguir o diagnóstico AppArmor do §2.5
(`dmesg`), mas isso é contingência, não trabalho planejado.

### D6 — O `larpd` é um arquivo único, em duas camadas [abre]
O protótipo §8.2 é um único arquivo com I/O acoplado (socket, `ip` shell, threads no
construtor). Para a seam secundária (testes sem Docker), a lógica pura precisa ser importável
sem efeitos colaterais.
Decisão: manter **um arquivo** (o Dockerfile copia um arquivo só, §2), mas dividido em:
- **Núcleo puro** — estruturas/classes que operam sobre dados passados como argumento e
  devolvem resultados (nunca tocam socket, subprocess ou thread): atualização EWMA de custo,
  decisão de anunciar (limiar), deduplicação de LSA, decisão de inundação (split horizon),
  Dijkstra com desempate (D7) e o conjunto de rotas desejadas a instalar (prefixos stub
  remotos → {gateway, iface}).
- **Camada de I/O (daemon)** — descoberta de interfaces lendo o kernel (`ip -j -4 addr`),
  socket UDP 5555, timers (HELLO 2 s, manutenção 1 s), e instalação de rotas por
  `ip route ... proto 200` / `ip route flush proto 200`. Threads e socket só nascem em
  `run()` / `main`, nunca no import.
Testes importam o núcleo puro; o E2E exercita a camada de I/O dentro dos containers.

### D7 — Contrato de mensagens e constantes (do protótipo §8.2)
Formato fixo (JSON sobre UDP/5555), pinado nesta spec porque o núcleo puro e a camada de I/O
dependem dele:
```jsonc
// HELLO, a cada 2 s, para o peer do outro lado de cada /30:
{ "t": "hello", "rid": "<router-id>", "ts": <epoch float> }
// ECHO, resposta imediata devolvendo o ts original:
{ "t": "echo",  "rid": "<router-id>", "ts": <ts original> }
// LSA: emitido em vizinho nasce/morre, custo varia > 20%, ou refresh de 30 s:
{ "t": "lsa", "origin": "<router-id>", "seq": <int>,
  "links": { "<rid-vizinho>": <custo ms> }, "stubs": ["192.168.1.0/24", "10.255.0.1/32"] }
```
Constantes do protótipo mantidas: `PORT=5555`, `HELLO_INTERVAL=2.0`,
`DEAD_AFTER=6.0` (3 HELLOs perdidos), `LSA_REFRESH=30.0`, `COST_THRESHOLD=0.20`,
`ALPHA=0.3`, `RT_PROTO=200`.
Semântica pinada: custo do enlace = `max(1, RTT/2)` ms (amostra); custo suavizado por EWMA
`α=0.3`; anuncia quando `|novo − antigo|/antigo > 0.20` ou quando não há anúncio anterior; a
inundação retransmite o LSA a todos os vizinhos **exceto** o de origem e descarta LSA com
`seq <=` ao conhecido; vizinho morre após 6 s sem HELLO; refresh periódico a cada 30 s
garante que a base não estagne. O limiar de 20% é a decisão de projeto deliberada que o
relatório manda explicar na apresentação (estabilidade × precisão de uma métrica ruidosa).

### D8 — Instalação de rotas isolada por `proto 200`
Rotas do LARP usam `proto 200` (número de protocolo próprio): o recompute derruba e
reinstala **somente** `proto 200`, sem tocar nas conectadas; nada conflita com zebra (que no
modo `larp` não anuncia rota dinâmica). Prefixos-alvo = stubs remotos do LSDB; os stubs
próprios são excluídos. Gateway de cada prefixo = o **primeiro salto** do caminho de menor
custo. Validação E2E: `ip route show proto 200` nos 5 nós lista exatamente os 4 stubs
remotos (cada nó tem 5 LANS + loopbacks; enxerga 4 stubs alheios + seus próprios conectados).

### D9 — Dijkstra com desempate determinístico [abre]
O relatório (§8.1) define: menor soma de latências; empate → menos saltos; empate → menor
router-id — "desempate determinístico para que todos cheguem à mesma decisão". O protótipo
§8.2 compara só distância, o que deixa o desempate dependente do heap — insuficiente.
Decisão: comparar caminhos pela tupla **(latência acumulada, nº de saltos, router-id do
próximo salto)** e escolher o mínimo lexicográfico. Com LSDB idêntico em todos os nós
(garantido pela inundação com seq), a escolha converge para o mesmo primeiro salto por
prefixo; rotas de custo igual que compartilham o mesmo próximo salto não bifurcam. O
comparador vive no núcleo puro e é testado na seam secundária com grafos de empate
artificiais.

### D10 — Impairments e leitura de métricas: relativos, não absolutos [abre]
`netem` aplicado simétrico nas duas pontas de cada enlace (ex.: R1–R2 = 30 ms em cada
egresso ⇒ RTT ~60 ms, custo LARP ~30 ms). A topologia foi desenhada para **ordens de
grandeza** distintas (1–5–30–100 ms), e é isso que as asserções devem usar.
Decisão: nenhum teste afirma milissegundos exatos. O que se afirma: (a) identidade dos
caminhos (hops) por modo, que é topológica e determinística; (b) *ordering* relativo das
latências fim-a-fim (RIP ≫ LARP no regime inicial; OSPF entre os dois); (c) janelas de
indisponibilidade por evento (D13); (d) reação a up/down, que é booleana. Tolerâncias do
verificador ficam num único lugar (constantes do harness) e são calibradas na fase M4 com a
execução real antes de serem travadas.

### D11 — Coletores e CSVs: esquema fixo, ausência de dado = dado
Os quatro CSVs de §9.3 têm esquema fixo (`table.csv`, `control.csv`, `latency.csv`,
`path.csv`), coletados pelo mesmo processo: `table` amostra a contagem de rotas por nó a 1 Hz;
`control` captura tráfego de controle em R1 com o filtro do modo (`udp 520` / `proto 89` /
`udp 5555`) e soma bytes; `latency` pinge h1→h4 a 5 Hz com timestamp absoluto; `path` faz
traceroute h1→h4 a cada 5 s. Lacunas na série de ping = indisponibilidade (§9.3, sem
instrumentação extra). Decisões:
- Toda coleta grava também um **registro de execução** (modo, timestamp, versões de
  docker/containerlab/python e commit do repo) — rastreabilidade das figuras (história 24).
- `control.csv` guarda `(t_abs, bytes)` por pacote; a conversão para bytes/s por segundo é
  responsabilidade do plotador (média móvel 5 s), não do coletor.
- Datas absolutas do ping (`-D`) e do tcpdump (`-tt`) são normalizadas em `t − t_min` no
  plotador para sobrepor os três modos na mesma linha do tempo.

### D12 — Cenário cronometrado é a única via de execução; duração parametrizável [abre]
`scenario.sh <modo>` (teardown → deploy → impairments → `larpd` se `larp` → coletor por
300 s) com eventos em 60/120/180/240 s (§9.4). O risco "três execuções com timing diferente"
é mitigado tornando o scenario a **única** forma de gerar resultados (regra do relatório §13).
Para o loop de desenvolvimento, a duração da fase é um parâmetro (`FASE=60` default → 300 s
totais; fases curtas, ex. 15 s, para iterar) — o coletor e o verificador offline recebem a
mesma duração, e apenas execuções com `FASE=60` alimentam `figs/` e resultados commitados.
Eventos mantêm a ordem e a semântica do relatório em qualquer duração; os tempos fixos do
gráfico (`EVENTS`) só valem para a duração padrão.

### D13 — Expectativa de convergência por evento (contrato do harness)
Tabela §9.4 vira contrato verificável. Por evento e por modo define-se a reação esperada:
- **t=60 queda do satélite (R1–R4):** RIP perde a rota usada e reconverge (via R5, 2 saltos);
  OSPF e LARP indiferentes. Janela de indisponibilidade de RIP tolerada na ordem de dezenas
  de segundos (timers RIP); OSPF/LARP sem lacuna relevante.
- **t=120 restauro do satélite:** RIP volta ao caminho de 1 salto; demais indiferentes.
- **t=180 queda do backbone (R2–R3):** OSPF reconverge via R5 (custo 20); RIP e LARP
  indiferentes (não usavam o enlace). OSPF em poucos segundos.
- **t=240 restauro do backbone + degradação de R1–R5 para 200 ms:** dois eventos quase
  simultâneos com causas distintas — o contrato os separa. (a) OSPF troca de caminho
  (volta de R5 para o backbone) **por causa do restauro**, evento topológico: o custo
  estático cai de 20 para 3; a degradação de latência não o afeta. (b) LARP troca de
  caminho **por causa da degradação**: mede o custo de R1–R5 subir ≫20% (RTT/2 ~100 ms,
  contra ~1 ms antes) e o caminho via R5 deixa de ser o mínimo — sai de R5 para o backbone
  (~90 ms medidos). RIP permanece no satélite (1 salto), cego à latência.
  A asserção-chave do slide central: **LARP é a única solução cuja mudança de caminho é
  causada pela latência** — no verificador, LARP troca de caminho *depois* da degradação,
  RIP não troca por ela e OSPF só troca pelo restauro do backbone. Nenhuma solução deve
  perder conectividade permanente; lacunas do LARP nesta janela na ordem de ~DEAD_AFTER +
  margem.
Os valores numéricos das janelas são constantes do verificador offline (D14), calibrados em
M4. Se o RIP convergir em 3 s, a medição está errada (§9.5) — o harness deve falhar nesse
caso, não passar.

### D14 — Harness de verificação (seam primária) [novo artefato, abre]
Dois níveis, ambos sobre comportamento observável (nunca sobre internals):
1. **Smoke por modo** (`verify.sh <modo>`, lab de pé, segundos): conectividade full-mesh
   (5×5 pings), caminho inicial esperado de h1→h4 (RIP passa por `10.0.14.x`; OSPF por
   `10.0.12.x→10.0.23.x→10.0.34.x`; LARP por `10.0.15.x→10.0.45.x`), checagem de honestidade
   no modo `larp` (sem processos ripd/ospfd; `show ip rip`/`show ip ospf` vazios), e presença
   do log do daemon com custos medidos. É o portão de M2/M3.
2. **Verificação offline dos resultados** (após `scenario.sh`): lê os CSVs e afirma (a)
   janelas de indisponibilidade por evento dentro das tolerâncias de D13 (lacunas do ping),
   (b) caminho dominante por janela bate com o esperado do modo (moda dos hops do
   `path.csv`), (c) os três modos têm caminho inicial **distinto** entre si. Roda sem lab.
O smoke usa nomes de container resolvidos via `containerlab inspect` (com fallback ao padrão
`clab-routing-lab-<nó>`) para não quebrar se o prefixo mudar. O harness é entregável e citado
no README como "como o trabalho foi verificado".

### D15 — Testes unitários do LARP (seam secundária) [novo artefato]
`pytest`, sem Docker e sem root, sobre o núcleo puro (D6). Catálogo mínimo:
- **EWMA + limiar:** sequência de amostras converge; anuncia só na 1ª medição e quando a
  variação passa de 20%; pequenas oscilações (<20%) não anunciam.
- **Deduplicação de LSA / inundação:** LSA com `seq` menor/igual é descartado e não
  retransmitido; LSA novo é armazenado e retransmitido para todos menos a origem (split
  horizon); loop de 3 nós termina com a base idêntica nos três.
- **Dijkstra com desempate (D9):** o grafo da topologia real (custos derivados dos netem de
  §4.1) produz R1→R4 via R5 (2 ms) e não via satélite; grafos de empate artificial escolhem
  menos saltos e depois menor próximo salto, de forma idêntica a partir de qualquer nó.
- **Descoberta de interfaces:** parsing de um payload `ip -j -4 addr` fixo (fixture) separa
  `/30` (p2p, com peer) de stubs (LAN/loopback) — mesma regra que o daemon usa.
Prior art: não há testes no repo (greenfield); a sequência de subida 2→3→5 nós do §8.4 é o
prior art *vivo* da integração e vira passo explícito de M2.

### D16 — Artefatos para vídeo e slides ficam prontos, mas fora do código
O que a implementação entrega para o estudante gravar/apresentar depois: cenário com echos
cronometrados no terminal (o roteiro de vídeo §11 sai de graça das mensagens do
`scenario.sh`), estado dos protocolos verificável por comandos curtos, figuras e CSVs
commitados, e um rascunho de README com a estrutura de análise que os slides vão usar.
Slides, vídeo e PDF **não** são implementados aqui (Fora de escopo).

### D17 — Repositório e artefatos commitados
`results/` (3 modos × 4 CSVs + registro de execução) e `figs/` (4 figuras + diagrama da
topologia) são commitados **depois** de uma execução padrão validada pelo harness (D14).
Rascunhos de desenvolvimento não entram. Diagrama da topologia: gerado por script a partir de
`topology.py` (matplotlib, sem graphviz) e embutido no README — também alimenta o slide 2.

### D18 — Marcos de implementação com critérios de saída verificáveis
A ordem do cronograma do relatório (§12) vira portões da implementação:
- **M1 — Ambiente e lab de pé:** Containerlab instalado (SUID root concedido) e validado
  com lab de 2 nós, imagem buildada, lab de 5
  roteadores + 5 hosts sobe, pings de vizinhança OK, `verify.sh` de smoke ainda não aplicável
  a modo. Saída: topologia sobe e se destrói sem resíduo.
- **M2 — LARP nos 5 nós:** núcleo puro + testes verdes; subida 2 → 3 → 5 nós; custos
  estabilizam perto do netem; `proto 200` com os 4 stubs remotos em cada nó; smoke `larp`
  verde (sem ripd/ospfd; caminho via R5).
- **M3 — RIP e OSPF + três caminhos:** configs geradas, smoke `rip` e `ospf` verdes, os três
  traceroutes de h1→h4 **diferentes e esperados** (§10). É o marco do slide central.
- **M4 — Evidência:** cenário completo (FASE=60) nos três modos, verificador offline verde,
  quatro figuras + diagrama, calibração das tolerâncias (D13), README completo.
- **M5 — Artefatos finais:** resultados/figuras commitados, registro de execução, revisão
  contra a tabela de avaliação §14.
Saída de cada marco falha **vermelha** quando o critério não bate — nunca "seguir mesmo
assim" sem registro explícito.

## Decisões de teste

- **Filosofia:** testar comportamento externo observável, nunca implementação interna. Um bom
  teste desta feature é aquele que *reproduz a evidência que o professor vai olhar*: o
  traceroute de h1→h4 escolhe o caminho X no modo X; a queda do enlace Y produz lacuna de
  ping e reconvergência dentro da janela do protocolo; o modo `larp` não tem ripd/ospfd. Um
  teste ruim é o que afirma milissegundos exatos, bytes exatos de CSV, ou detalhes de
  implementação que podem mudar sem mudar o comportamento.
- **Seam primária (E2E, lab vivo + offline):** cobre topologia, configs geradas, FRR, netem,
  `larpd` integrado, coletor, plotador e o próprio cenário — tudo que é observável de fora.
  Subdividida em smoke (rápido, por modo, lab de pé) e verificação offline dos CSVs (após a
  execução, sem lab). É a única seam que valida o "produto central" (três caminhos
  distintos + reações por evento).
- **Seam secundária (unit, núcleo puro do LARP):** existe porque certas falhas do LARP só
  apareceriam no E2E como gráfico estranho ou flakiness de tempo (desempate não
  determinístico, limiar errado, inundação em loop). Pinar essas decisões em teste puro
  permite localizar a causa sem caçar em 5 containers. É a única exceção à regra de "não
  testar internals": testa-se o *contrato* do núcleo (entrada → saída), não seus passos.
- **Módulos testados:** núcleo puro do LARP (unit); tudo o mais via E2E (gen_configs, coletor
  e plotador são exercitados indiretamente — config errada ⇒ caminho errado ⇒ smoke vermelho;
  coletor errado ⇒ CSV/figura errados ⇒ verificador offline vermelho). O harness de
  verificação é tratado como entregável de primeira classe, com asserções declarativas.
- **Prior art:** repo greenfield (sem testes existentes). Como prior art de *integração*
  vale a sequência de subida do próprio relatório (§8.4: isolar `discover_interfaces`, 2
  vizinhos, 3 em linha, depois 5) — vira procedimento explícito do M2, não dica. Convenção de
  testes: `pytest`, fixtures com payloads fixos de `ip -j`, sem rede e sem root.
- **Anti-flakiness:** nenhuma asserção depende de tempo de relógio absoluto do host; janelas
  são relativas aos eventos do cenário; amostras de caminho usam moda por janela; tolerâncias
  vivem em constantes únicas calibradas em M4 e travadas depois.

## Fora de escopo

- **Slides, vídeo e PDF** da apresentação — a implementação prepara os insumos (figuras,
  CSVs, logs, comandos de estado, ecos do cenário), mas a montagem é manual (§16/D16).
- **Segurança do LARP** (autenticação de mensagens) e **escalabilidade** (áreas, LSDB O(n²))
  — assumidas como limitações declaradas na apresentação (§8.1).
- **Múltiplos caminhos de custo igual (ECMP)** e **roteamento IPv6/dual-stack** — o lab é
  IPv4 puro (`no ipv6 forwarding` nas configs) e o LARP instala uma rota por prefixo.
- **Reinício de daemon com `seq` resetado** — mitigado pelo refresh periódico de 30 s; o
  comportamento durante reinício quente do `larpd` não é objeto de garantia nesta entrega.
- **Fallback centralizado do LARP** (processo no host que empurra rotas) — é contingência de
  risco do §12, **não** escopo; só entra se M2 falhar e for decidido explicitamente.
- **Suporte multi-plataforma** do README além do Zorin/Ubuntu testado; e **exatidão
  metrológica** de latência (o lab prova ordenação e reação, não precisão).
- **Automação de gravação/apresentação** e qualquer integração com Moodle/GitHub além do push
  final do repositório.

## Notas adicionais

- **Fatos do host que condicionam a implementação** (verificados em 07/09): Zorin 18.1
  (`UBUNTU_CODENAME=noble`), Docker 29.7.2 + usuário no grupo `docker`, Containerlab ausente,
  matplotlib/pytest ausentes (pandas 3.0.3 presente), `sudo` exige senha, sem graphviz. O
  bootstrap de M1 cobre exatamente essas lacunas e é o primeiro critério de saída.
- **Ordem de risco:** o `larpd` é o único item com risco real (cronograma do relatório coloca
  ele primeiro, §12). Por isso M2 vem antes de M3: configs RIP/OSPF levam meia hora cada;
  depurar inundação com 5 nós de uma vez custa um dia.
- **Mapa de avaliação (§14):** itens 2–3 → M1/D3; item 5 (configurar protocolos + implementar
  algoritmo com isolamento por modo) → M2+M3; itens 4 → §8.1/D7; itens 6–7 → M4/D11; itens
  1/8/9/10 → insumos de D16 + roteiro de apresentação. O harness de D14 é o mecanismo que faz
  cada marco "entregar item de avaliação" de forma verificável.
- **Divergências desta spec em relação ao relatório** (para o relatório continuar a fonte de
  verdade da *narrativa*): manifesto e impairments passam a ser gerados (D3), `larpd` ganha
  núcleo puro testável (D6), desempate do Dijkstra fica explícito (D9), Containerlab via
  SUID em vez de `sudo` (D2, corrigido em M1 — o grupo `docker` não basta),
  como padrão (D2), harness de verificação e testes unitários são artefatos novos (D14/D15).
- **Execução da demonstração:** `scenario.sh <modo>` com `FASE=60` é o único caminho para os
  números do relatório; qualquer execução alternativa gera resultados de desenvolvimento que
  não alimentam `figs/` nem o commit final.

#!/usr/bin/env bash
# bootstrap.sh — preparo idempotente do host para o lab Containerlab (marco M1).
#
# Nunca usa sudo (sudo exige senha neste host). O que o script não puder fazer
# por permissão, ele ORIENTA com a mensagem acionável em vez de tentar sudo -n.
#
# O que faz:
#   1. valida o OS (esperado Ubuntu noble / Zorin 18); senão avisa e segue
#   2. conserta o contexto Docker (default = daemon real em /var/run/docker.sock)
#   3. valida o grupo docker
#   4. instala o Containerlab em modo usuário (~/containerlab/bin), se ausente
#   5. deps Python do host (best-effort, não-gate do M1): pytest, matplotlib
#   6. imprime sumário de versões
set -euo pipefail

warn() { printf '\033[33m[aviso]\033[0m %s\n' "$*" >&2; }
ok()   { printf '\033[32m[ok]\033[0m %s\n' "$*"; }
die()  { printf '\033[31m[erro]\033[0m %s\n' "$*" >&2; exit 1; }

echo "==> bootstrap.sh — ambiente Containerlab sem sudo"

# ---------------------------------------------------------------- 1. OS
echo "--- [1/6] OS"
os_line=$(grep -E 'UBUNTU_CODENAME|PRETTY_NAME' /etc/os-release || true)
echo "$os_line"
case "$os_line" in
  *UBUNTU_CODENAME=noble*) ok "distro derivada de Ubuntu noble (esperado)" ;;
  *) warn "codinome esperado 'noble'; vi algo diferente. Seguindo mesmo assim." ;;
esac

# ---------------------------------------------------------------- 2. Docker context
echo "--- [2/6] contexto Docker"
# O daemon real deste host é o socket do Docker Engine (contexto 'default').
# O contexto 'desktop-linux' aponta para um socket morto — sintoma típico de
# "Cannot connect to the Docker daemon" sem causa real.
active=$(docker context ls --format '{{if eq .Current true}}{{.Name}}{{end}}' 2>/dev/null || echo "")
if [ -n "$active" ] && [ "$active" != "default" ]; then
  warn "contexto ativo é '$active' (socket morto?) — trocando para 'default'"
  docker context use default
fi
export DOCKER_CONTEXT=default
if docker info >/dev/null 2>&1; then
  ok "docker info OK (daemon $(docker info --format '{{.ServerVersion}}'))"
else
  die "docker info falhou. Se o erro é de socket: confira 'docker context ls' \
e rode 'docker context use default'. Se o daemon está parado: inicie via systemd \
('systemctl start docker') ou dockerd. Não tente sudo -n."
fi

# ---------------------------------------------------------------- 3. Grupo docker
echo "--- [3/6] grupo docker"
groups_now=$(id -nG)
if echo "$groups_now" | tr ' ' '\n' | grep -qx 'docker'; then
  ok "usuário pertence ao grupo docker"
else
  die "usuário NÃO está no grupo docker. Rode (uma vez): 'sudo usermod -aG docker \$USER' \
e faça logout completo da sessão (ou 'newgrp docker' na aba atual) antes de reexecutar."
fi

# ---------------------------------------------------------------- 4. Containerlab
echo "--- [4/6] Containerlab (instalação em modo usuário)"
CLAB_BIN_DIR="$HOME/containerlab/bin"
if command -v containerlab >/dev/null 2>&1; then
  CLAB_EXE="$(command -v containerlab)"
  ok "containerlab já instalado em $CLAB_EXE"
elif [ -x "$CLAB_BIN_DIR/containerlab" ]; then
  ok "containerlab já instalado em $CLAB_BIN_DIR/containerlab"
else
  warn "containerlab ausente — baixando release oficial para $CLAB_BIN_DIR"
  mkdir -p "$CLAB_BIN_DIR"
  CLAB_VER=""
  for attempt in 1 2 3; do
    CLAB_VER=$(curl -fsSL --retry 3 https://api.github.com/repos/srl-labs/containerlab/releases/latest \
      | python3 -c "import json,sys;print(json.load(sys.stdin)['tag_name'].lstrip('v'))" 2>/dev/null \
      || true)
    [ -n "$CLAB_VER" ] && break
    warn "tentativa $attempt de obter a versão mais recente falhou; nova tentativa"
    sleep 2
  done
  [ -z "$CLAB_VER" ] && die "não consegui obter a versão do containerlab (rede?). Baixe o \
release em https://github.com/srl-labs/containerlab/releases e repita."
  curl -fsSL --retry 3 -o /tmp/clab.tar.gz \
    "https://github.com/srl-labs/containerlab/releases/download/v${CLAB_VER}/containerlab_${CLAB_VER}_linux_amd64.tar.gz"
  tar -xzf /tmp/clab.tar.gz -C "$CLAB_BIN_DIR" containerlab
  chmod +x "$CLAB_BIN_DIR/containerlab"
  rm -f /tmp/clab.tar.gz
  ok "containerlab ${CLAB_VER} instalado em $CLAB_BIN_DIR"
fi

# PATH no ~/.bashrc (idempotente)
RC_LINE='export PATH="$HOME/containerlab/bin:$PATH"'
if [ -f "$HOME/.bashrc" ] && grep -qF 'containerlab/bin' "$HOME/.bashrc"; then
  ok "PATH do containerlab já presente em ~/.bashrc"
else
  printf '\n# Containerlab (instalado pelo scripts/bootstrap.sh, sem sudo)\n%s\n' "$RC_LINE" >> "$HOME/.bashrc"
  ok "linha de PATH adicionada a ~/.bashrc"
fi
export PATH="$HOME/containerlab/bin:$PATH"

# ---------------------------------------------------------------- 5. Deps Python (best-effort)
echo "--- [5/6] deps Python do host (best-effort — não bloqueiam o M1)"
if python3 -m pip --version >/dev/null 2>&1; then
  for pkg in pytest matplotlib; do
    if python3 -c "import $pkg" >/dev/null 2>&1; then
      ok "python3 módulo '$pkg' já presente"
    else
      if python3 -m pip install --user --break-system-packages "$pkg" >/dev/null 2>&1; then
        ok "python3 módulo '$pkg' instalado (user)"
      else
        warn "falha ao instalar '$pkg' (rede/índice?). Necessário só em M2/M4 — siga."
      fi
    fi
  done
else
  warn "python3 -m pip não disponível — deps Python adiadas para M2 (registre no fim)."
fi

# ---------------------------------------------------------------- 6. Sumário
echo "--- [6/6] sumário de versões"
echo "containerlab : $(containerlab version 2>/dev/null | grep -i version | head -1 || echo '?')"
echo "docker server: $(docker version --format '{{.Server.Version}}')"
echo "python3      : $(python3 --version 2>&1)"
echo
ok "bootstrap concluído. Em shell nova: 'containerlab version' deve funcionar, \
'docker context show' -> default."

#!/usr/bin/env python3
"""Gerador único dos artefatos derivados de topology.py (D3).

Regenerar = `python3 src/gen_configs.py`

Emite:
  - configs/{rip,ospf,larp}/R*/{frr.conf,daemons}   (fiel ao §7 do relatório)
  - topology.clab.yml                                (manifesto, formato do §6)
  - scripts/impair.sh                                (netem, formato do §9.1)

Nada disso deve ser editado à mão: edite topology.py e regenere.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from topology import ROUTERS, LINKS, LANS, LOOPBACK, addr_of, links_of, iface_of

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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


def gen_configs():
    for mode in DAEMONS:
        for r in ROUTERS:
            d = os.path.join(ROOT, "configs", mode, r)
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


def _host_exec(r):
    """exec do host h<k>: endereço, up da eth1 e default via o gateway da LAN."""
    k = r[1:]
    return [
        f"ip addr add 192.168.{k}.10/24 dev eth1",
        "ip link set eth1 up",
        f"ip route replace default via 192.168.{k}.1",
    ]


def gen_manifest():
    """Emit topology.clab.yml no formato literal do §6 (preservando ${MODE})."""
    out = []
    out.append("name: routing-lab")
    out.append("")
    out.append("topology:")
    out.append("  kinds:")
    out.append("    linux:")
    out.append("      image: frr-larp:latest")
    # D5: NET_ADMIN/NET_RAW para rotas do larpd e tc do netem; SYS_ADMIN é
    # exigido pelo privs_init do FRR 9.1.0 (zebra morre sem ele — verificado
    # empiricamente neste host: kernel 7.0.0-30-generic). Divergência pequena e
    # documentada: o §6/§2.5 do relatório previa só NET_ADMIN/NET_RAW.
    out.append('      cap-add: ["NET_ADMIN", "NET_RAW", "SYS_ADMIN"]')
    out.append("")
    out.append("  nodes:")
    for r in ROUTERS:
        binds = json.dumps([f"configs/${{MODE}}/{r}:/etc/frr"])
        out.append(f"    {r}: {{kind: linux, binds: {binds}}}")
    for r in ROUTERS:
        k = r[1:]
        exec_list = json.dumps(_host_exec(r))
        out.append(f"    h{k}: {{kind: linux, image: alpine:3.19, exec: {exec_list}}}")
    out.append("")
    out.append("  links:")
    # enlaces R–R na ordem do §6 (a ordem define os nomes eth dentro dos nós)
    for (a, b) in LINKS:
        out.append(f'    - endpoints: ["{a}:{iface_of(a, (a, b))}", "{b}:{iface_of(b, (a, b))}"]')
    for r in ROUTERS:
        k = r[1:]
        lanif = LANS[r][1]
        out.append(f'    - endpoints: ["{r}:{lanif}", "h{k}:eth1"]')
    out.append("")

    path = os.path.join(ROOT, "topology.clab.yml")
    with open(path, "w") as f:
        f.write("\n".join(out))
    print(f"gerado {path}")


def gen_impair():
    """Emit scripts/impair.sh (§9.1): uma chamada netem por ponta dos enlaces R–R.

    Divergência empírica: o `--rate` do containerlab 0.79.0 é um inteiro em kbit
    ("100mbit" → ParseUint error). Convertemos banda_mbit → kbit (× 1000).
    """
    out = []
    out.append("#!/usr/bin/env bash")
    out.append("# Aplica banda e latência em cada enlace conforme topology.py (gerado)")
    out.append("set -e")
    out.append("apply() {  # nó iface latencia_ms banda_kbit")
    out.append("  containerlab tools netem set -n clab-routing-lab-$1 -i $2 --delay ${3}ms --rate ${4}")
    out.append("}")
    for (a, b) in LINKS:
        lat = LINKS[(a, b)][4]
        bw_kbit = LINKS[(a, b)][3] * 1000   # mbit → kbit (CLI do containerlab)
        ia = iface_of(a, (a, b))
        ib = iface_of(b, (a, b))
        out.append(f"apply {a} {ia} {lat} {bw_kbit} ; apply {b} {ib} {lat} {bw_kbit}")
    out.append('echo "impairments aplicados"')
    out.append("")

    path = os.path.join(ROOT, "scripts", "impair.sh")
    with open(path, "w") as f:
        f.write("\n".join(out))
    print(f"gerado {path}")


def main():
    gen_configs()
    gen_manifest()
    gen_impair()


if __name__ == "__main__":
    main()

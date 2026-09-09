# topology.py — fonte da verdade da topologia física e do endereçamento.
#
# Tudo (configs, manifesto Containerlab, impairments netem, checagens de
# consistência) é gerado a partir deste arquivo. Mudou a topologia, mudou num
# lugar só (D3). NÃO alterar os valores: são consumidos pelo gerador, pelo
# coletor e pelo README.
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

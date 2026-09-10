#!/usr/bin/env python3
"""LARP: protocolo de estado de enlace, distribuído e de métrica ativa de latência.
O daemon mede enlaces por ECHO/HELLO, inunda LSAs e calcula caminhos mínimos.
As rotas escolhidas são instaladas no kernel com o protocolo 200."""
import heapq
import ipaddress
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


def ewma_update(old, sample, alpha=ALPHA):
    return sample if old is None else alpha * sample + (1.0 - alpha) * old


def should_announce(old_cost, new_cost, threshold=COST_THRESHOLD):
    return (old_cost is None or old_cost == 0 or
            abs(new_cost - old_cost) / old_cost > threshold)


def lsa_is_newer(known_seq, incoming_seq):
    return known_seq is None or incoming_seq > known_seq


def flood_peers(peer_ips, from_ip):
    return [peer for peer in peer_ips if peer != from_ip]


def _lsa_value(lsdb, rid):
    value = lsdb.get(rid, {})
    return value if isinstance(value, dict) else {}


def dijkstra(lsdb, rid):
    """Calcula distância e primeiro salto usando a ordem de desempate da spec."""
    dist = {rid: 0.0}
    first_hop = {rid: None}
    hops = {rid: 0}
    queue = [(0.0, 0, "", rid)]
    while queue:
        cost, count, first, node = heapq.heappop(queue)
        current_key = (dist[node], hops[node], first_hop[node] or "")
        if (cost, count, first) != current_key:
            continue
        links = _lsa_value(lsdb, node).get("links", {})
        for target, weight in links.items():
            if not isinstance(weight, (int, float)):
                continue
            target_first = target if node == rid else first_hop[node]
            candidate = (cost + float(weight), count + 1, target_first or "")
            old = (dist.get(target, float("inf")), hops.get(target, 10 ** 9),
                   first_hop.get(target) or "")
            if candidate < old:
                dist[target] = candidate[0]
                hops[target] = candidate[1]
                first_hop[target] = target_first
                heapq.heappush(queue, (candidate[0], candidate[1],
                                       candidate[2], target))
    return dist, first_hop


def desired_routes(rid, lsdb, neighbors, my_stubs):
    dist, first_hop = dijkstra(lsdb, rid)
    own = set(my_stubs)
    candidates = {}
    for owner, record in lsdb.items():
        if owner == rid or owner not in dist:
            continue
        hop = first_hop.get(owner)
        if not hop or hop not in neighbors:
            continue
        for prefix in _lsa_value(lsdb, owner).get("stubs", []):
            if prefix in own:
                continue
            key = (dist[owner], _path_hops(lsdb, rid, owner), owner)
            candidates.setdefault(prefix, []).append((key, hop))
    routes = {}
    for prefix, options in candidates.items():
        _, hop = min(options, key=lambda item: item[0])
        info = neighbors[hop]
        if isinstance(info, dict):
            routes[prefix] = (info["peer"], info["iface"])
        else:
            routes[prefix] = tuple(info)
    return routes


def _path_hops(lsdb, source, target):
    dist, first = dijkstra(lsdb, source)
    if target not in dist:
        return 10 ** 9
    # Recompute hop count without exposing it as part of the public result.
    pending = [(0.0, 0, source)]
    best = {source: (0.0, 0)}
    while pending:
        cost, hops, node = heapq.heappop(pending)
        if node == target:
            return hops
        if (cost, hops) != best[node]:
            continue
        for nxt, weight in _lsa_value(lsdb, node).get("links", {}).items():
            if not isinstance(weight, (int, float)):
                continue
            candidate = (cost + float(weight), hops + 1)
            if nxt not in best or candidate < best[nxt]:
                best[nxt] = candidate
                heapq.heappush(pending, (candidate[0], candidate[1], nxt))
    return 10 ** 9


def parse_addr_output(json_text):
    data = json.loads(json_text)
    p2p = []
    stubs = []
    for interface in data:
        name = interface.get("ifname", interface.get("name"))
        if name == "lo":
            continue
        for address in interface.get("addr_info", []):
            if address.get("family", "inet") != "inet":
                continue
            local = address["local"]
            prefixlen = int(address["prefixlen"])
            network = ipaddress.ip_network("%s/%d" % (local, prefixlen),
                                           strict=False)
            if prefixlen == 30:
                hosts = [str(host) for host in network.hosts()]
                peer = next(host for host in hosts if host != local)
                p2p.append({"iface": name, "local": local, "peer": peer,
                            "net": str(network)})
            else:
                stubs.append(str(network))
    return p2p, stubs


def merge_p2p(existing, discovered):
    """Adiciona enlaces descobertos sem duplicar os já conhecidos."""
    merged = list(existing)
    known = {(item["iface"], item["local"], item["peer"], item["net"])
             for item in existing}
    for item in discovered:
        key = (item["iface"], item["local"], item["peer"], item["net"])
        if key not in known:
            merged.append(item)
            known.add(key)
    return merged


def discover_interfaces():
    output = subprocess.check_output(["ip", "-j", "-4", "addr", "show"],
                                     text=True)
    return parse_addr_output(output)


class LarpDaemon:
    def __init__(self, rid):
        self.rid = rid
        self.p2p, self.my_stubs = discover_interfaces()
        for _ in range(15):
            if self.p2p:
                break
            time.sleep(2.0)
            discovered, stubs = discover_interfaces()
            self.p2p = merge_p2p(self.p2p, discovered)
            self.my_stubs = sorted(set(self.my_stubs).union(stubs))
        self.sock = None
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.neighbors = {}
        self.by_ip = {}
        self.pending = {}
        self.lsdb = {rid: {"seq": 0, "links": {}, "stubs": self.my_stubs}}
        self.seq = 0
        self.last_lsa = 0.0
        self.installed_routes = None
        self.maintenance_ticks = 0

    def send(self, message, address):
        self.sock.sendto(json.dumps(message).encode(), (address, PORT))

    def originate_lsa(self):
        self.seq += 1
        links = {key: value["cost"] for key, value in self.neighbors.items()
                 if value["cost"] is not None}
        lsa = {"t": "lsa", "origin": self.rid, "seq": self.seq,
               "links": links, "stubs": self.my_stubs}
        self.lsdb[self.rid] = lsa
        self.last_lsa = time.time()
        peers = [value["ip"] for value in self.neighbors.values()]
        for peer in peers:
            self.send(lsa, peer)

    def recompute(self):
        with self.lock:
            routes = desired_routes(self.rid, self.lsdb, self.neighbors,
                                     self.my_stubs)
        if routes == self.installed_routes:
            return
        subprocess.check_call(["ip", "route", "flush", "proto", str(RT_PROTO)])
        print("rotas: %s" % routes, flush=True)
        for prefix, (gateway, interface) in sorted(routes.items()):
            subprocess.check_call(["ip", "route", "replace", prefix, "via",
                                   gateway, "dev", interface, "proto",
                                   str(RT_PROTO)])
            print("route %s via %s dev %s" % (prefix, gateway, interface),
                  flush=True)
        self.installed_routes = routes

    def recv_loop(self):
        while not self.stop_event.is_set():
            try:
                packet, address = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            message = json.loads(packet.decode())
            kind = message.get("t")
            if kind == "hello":
                self.handle_hello(message, address[0])
            elif kind == "echo":
                self.handle_echo(message, address[0])
            elif kind == "lsa":
                self.handle_lsa(message, address[0])

    def handle_hello(self, message, source):
        self.send({"t": "echo", "rid": self.rid, "ts": message["ts"]},
                  source)
        rid = message.get("rid")
        link = next((item for item in self.p2p if item["peer"] == source), None)
        if link is None:
            return
        with self.lock:
            old = self.neighbors.get(rid)
            self.neighbors[rid] = {"ip": source, "iface": link["iface"],
                                   "peer": source,
                                   "cost": old["cost"] if old else None,
                                   "last_seen": time.time()}
            self.by_ip[source] = rid

    def handle_echo(self, message, source):
        sent = message["ts"]
        sample = max(1.0, (time.time() - sent) * 1000.0 / 2.0)
        link = next((item for item in self.p2p if item["peer"] == source), None)
        if link is None:
            return
        rid = self.by_ip.get(source, message.get("rid"))
        if rid is None:
            return
        with self.lock:
            neighbor = self.neighbors.get(rid)
            old = neighbor["cost"] if neighbor else None
            if neighbor is None:
                neighbor = {"ip": source, "iface": link["iface"],
                            "peer": source, "cost": None}
                self.neighbors[rid] = neighbor
            neighbor["last_seen"] = time.time()
            neighbor["cost"] = ewma_update(old, sample)
            self.by_ip[source] = rid
            changed = should_announce(old, neighbor["cost"])
            print("custo %s: %.3f ms" % (rid, neighbor["cost"]), flush=True)
        if changed:
            self.originate_lsa()
            self.recompute()

    def handle_lsa(self, message, source):
        origin = message["origin"]
        with self.lock:
            known = self.lsdb.get(origin, {}).get("seq")
            if not lsa_is_newer(known, message["seq"]):
                return
            self.lsdb[origin] = message
            peers = flood_peers([item["ip"] for item in self.neighbors.values()],
                                source)
        for peer in peers:
            self.send(message, peer)
        self.recompute()

    def hello_loop(self):
        while not self.stop_event.wait(HELLO_INTERVAL):
            now = time.time()
            for link in self.p2p:
                timestamp = time.time()
                self.pending[link["peer"]] = timestamp
                self.send({"t": "hello", "rid": self.rid, "ts": timestamp},
                          link["peer"])

    def maintenance_loop(self):
        while not self.stop_event.wait(1.0):
            now = time.time()
            self.maintenance_ticks += 1
            if self.maintenance_ticks % 10 == 0:
                discovered, stubs = discover_interfaces()
                with self.lock:
                    self.p2p = merge_p2p(self.p2p, discovered)
                    self.my_stubs = sorted(set(self.my_stubs).union(stubs))
            changed = False
            with self.lock:
                dead = [rid for rid, item in self.neighbors.items()
                        if now - item["last_seen"] > DEAD_AFTER]
                for rid in dead:
                    self.by_ip.pop(self.neighbors[rid]["ip"], None)
                    del self.neighbors[rid]
                    changed = True
                refresh = now - self.last_lsa > LSA_REFRESH
            if changed or refresh:
                self.originate_lsa()
                self.recompute()

    def run(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(1.0)
        self.sock.bind(("0.0.0.0", PORT))
        print("larpd up — %d enlaces" % len(self.p2p), flush=True)
        threads = [threading.Thread(target=self.recv_loop),
                   threading.Thread(target=self.hello_loop),
                   threading.Thread(target=self.maintenance_loop)]
        for thread in threads:
            thread.daemon = True
            thread.start()
        try:
            self.originate_lsa()
            self.recompute()
            while not self.stop_event.wait(1.0):
                pass
        finally:
            self.stop_event.set()
            if self.sock:
                self.sock.close()
            subprocess.call(["ip", "route", "flush", "proto", str(RT_PROTO)])


def main():
    rid = os.environ.get("LARP_RID") or (sys.argv[1] if len(sys.argv) > 1
                                         else None)
    if not rid:
        print("uso: larpd <router-id>", file=sys.stderr, flush=True)
        return 2
    try:
        LarpDaemon(rid).run()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

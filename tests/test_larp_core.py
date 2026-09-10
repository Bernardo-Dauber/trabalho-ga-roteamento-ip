import json
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from larpd import (LarpDaemon, dijkstra, ewma_update, flood_peers,
                   lsa_is_newer, merge_p2p, parse_addr_output,
                   should_announce)


def test_ewma_and_announcement_threshold():
    cost = None
    for sample in (10.0, 20.0, 30.0):
        cost = ewma_update(cost, sample)
    assert cost == 18.1
    assert should_announce(None, 10.0)
    assert not should_announce(10.0, 11.9)
    assert should_announce(10.0, 12.1)


def test_lsa_deduplication_and_flood_split_horizon():
    assert lsa_is_newer(None, 1)
    assert lsa_is_newer(2, 3)
    assert not lsa_is_newer(3, 3)
    assert flood_peers(["10.0.0.2", "10.0.0.6"], "10.0.0.2") == [
        "10.0.0.6"
    ]


def test_dijkstra_real_topology():
    links = {
        "R1": {"R2": 30, "R5": 1, "R4": 100},
        "R2": {"R1": 30, "R3": 30},
        "R3": {"R2": 30, "R4": 30},
        "R4": {"R3": 30, "R5": 1, "R1": 100},
        "R5": {"R1": 1, "R4": 1},
    }
    lsdb = {rid: {"links": value, "stubs": []} for rid, value in links.items()}
    dist, first = dijkstra(lsdb, "R1")
    assert dist["R4"] == 2
    assert first["R4"] == "R5"
    assert dist["R3"] == 32
    assert first["R3"] == "R5"


def test_dijkstra_tie_breaking_is_deterministic():
    lsdb = {
        "A": {"links": {"B": 2, "C": 1, "E": 2}, "stubs": []},
        "B": {"links": {"D": 2}, "stubs": []},
        "C": {"links": {"D": 3}, "stubs": []},
        "E": {"links": {"D": 2}, "stubs": []},
        "D": {"links": {}, "stubs": []},
    }
    dist, first = dijkstra(lsdb, "A")
    assert dist["D"] == 4
    assert first["D"] == "B"
    for rid in lsdb:
        assert dijkstra(lsdb, rid)[0].get(rid) == 0


def test_dijkstra_ignores_unknown_link_cost():
    lsdb = {
        "R1": {"links": {"R2": None, "R3": "unknown"}, "stubs": []},
        "R2": {"links": {}, "stubs": []},
        "R3": {"links": {}, "stubs": []},
    }
    dist, first = dijkstra(lsdb, "R1")
    assert dist == {"R1": 0.0}
    assert first == {"R1": None}


def test_merge_p2p_adopts_late_link_without_duplicates():
    first = [{"iface": "eth1", "local": "10.0.0.1", "peer": "10.0.0.2",
              "net": "10.0.0.0/30"}]
    late = [{"iface": "eth1", "local": "10.0.0.1", "peer": "10.0.0.2",
             "net": "10.0.0.0/30"},
            {"iface": "eth2", "local": "10.0.0.5", "peer": "10.0.0.6",
             "net": "10.0.0.4/30"}]

    merged = merge_p2p(first, late)

    assert merged == first + [late[1]]


def test_parse_addr_output():
    fixture = [
        {"ifname": "eth0", "addr_info": [
            {"family": "inet", "local": "10.0.0.1", "prefixlen": 30}]},
        {"ifname": "eth1", "addr_info": [
            {"family": "inet", "local": "192.168.1.1", "prefixlen": 24}]},
        {"ifname": "lo", "addr_info": [
            {"family": "inet", "local": "10.255.0.1", "prefixlen": 32}]},
    ]
    p2p, stubs = parse_addr_output(json.dumps(fixture))
    assert p2p == [{"iface": "eth0", "local": "10.0.0.1",
                    "peer": "10.0.0.2", "net": "10.0.0.0/30"}]
    assert stubs == ["192.168.1.0/24"]


def test_echo_registers_known_neighbor_before_updating_cost(monkeypatch):
    daemon = LarpDaemon.__new__(LarpDaemon)
    daemon.p2p = [{"iface": "eth0", "peer": "10.0.0.2"}]
    daemon.neighbors = {}
    daemon.by_ip = {}
    daemon.lock = threading.Lock()
    daemon.originate_lsa = lambda: None
    daemon.recompute = lambda: None
    monkeypatch.setattr("larpd.time.time", lambda: 10.0)

    daemon.handle_echo({"rid": "R2", "ts": 9.0}, "10.0.0.2")

    assert daemon.neighbors["R2"] == {
        "ip": "10.0.0.2",
        "iface": "eth0",
        "peer": "10.0.0.2",
        "cost": 500.0,
        "last_seen": 10.0,
    }


def test_originate_lsa_excludes_neighbors_without_cost():
    daemon = LarpDaemon.__new__(LarpDaemon)
    daemon.seq = 0
    daemon.rid = "R1"
    daemon.my_stubs = ["192.168.1.0/24"]
    daemon.lsdb = {}
    daemon.neighbors = {
        "R2": {"cost": None, "ip": "10.0.0.2"},
        "R3": {"cost": 4.5, "ip": "10.0.0.6"},
    }
    daemon.last_lsa = 0.0
    daemon.send = lambda message, address: None

    daemon.originate_lsa()

    assert daemon.lsdb["R1"]["links"] == {"R3": 4.5}

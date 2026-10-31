#!/usr/bin/env python3
"""Write a small SYNTHETIC capture file for testing the replay pipeline.

It is not real traffic and says nothing about detection quality. It contains:
  - DNS lookups from a home device (normal),
  - several short HTTPS-style TCP sessions (normal),
  - one host sweeping many ports with SYN packets (a port scan, which rules should flag).

Usage:  python3 scripts/make_sample_pcap.py samples/synthetic_home.pcap
Requires: pip install scapy
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

from scapy.all import IP, TCP, UDP, DNS, DNSQR, Ether, wrpcap  # type: ignore[attr-defined]

LAN_CLIENT = "192.168.1.20"
SCANNER = "192.168.1.66"
RESOLVER = "192.168.1.1"
WEB_SERVERS = ["142.250.72.14", "104.16.132.229", "151.101.1.69"]


def _dns(packets: list, src: str, name: str, t: float) -> None:
    query = (
        Ether()
        / IP(src=src, dst=RESOLVER)
        / UDP(sport=random.randint(40000, 60000), dport=53)
        / DNS(rd=1, qd=DNSQR(qname=name))
    )
    query.time = t
    packets.append(query)


def _tcp_session(packets: list, src: str, dst: str, dport: int, t: float) -> None:
    sport = random.randint(40000, 60000)
    seq_c, seq_s = 1000, 5000
    steps = [
        (src, dst, TCP(sport=sport, dport=dport, flags="S", seq=seq_c), b""),
        (dst, src, TCP(sport=dport, dport=sport, flags="SA", seq=seq_s, ack=seq_c + 1), b""),
        (src, dst, TCP(sport=sport, dport=dport, flags="A", seq=seq_c + 1, ack=seq_s + 1), b""),
        (src, dst, TCP(sport=sport, dport=dport, flags="PA", seq=seq_c + 1, ack=seq_s + 1), b"x" * 300),
        (dst, src, TCP(sport=dport, dport=sport, flags="PA", seq=seq_s + 1, ack=seq_c + 301), b"y" * 1200),
        (src, dst, TCP(sport=sport, dport=dport, flags="FA", seq=seq_c + 301, ack=seq_s + 1201), b""),
        (dst, src, TCP(sport=dport, dport=sport, flags="FA", seq=seq_s + 1201, ack=seq_c + 302), b""),
    ]
    for i, (s, d, tcp, payload) in enumerate(steps):
        pkt = Ether() / IP(src=s, dst=d) / tcp / payload
        pkt.time = t + i * 0.02
        packets.append(pkt)


def _port_scan(packets: list, t: float) -> None:
    target = WEB_SERVERS[0]
    for i, port in enumerate(range(1, 301)):
        pkt = Ether() / IP(src=SCANNER, dst=target) / TCP(sport=50000, dport=port, flags="S")
        pkt.time = t + i * 0.005
        packets.append(pkt)


def build(path: Path) -> int:
    random.seed(7)
    packets: list = []
    t = 1_790_000_000.0  # fixed, so the file is reproducible
    for i, name in enumerate(["www.example.com", "mail.example.org", "cdn.example.net"]):
        _dns(packets, LAN_CLIENT, name, t + i)
    for i, dst in enumerate(WEB_SERVERS):
        _tcp_session(packets, LAN_CLIENT, dst, 443, t + 10 + i * 2)
    _port_scan(packets, t + 60)
    packets.sort(key=lambda p: float(p.time))
    path.parent.mkdir(parents=True, exist_ok=True)
    wrpcap(str(path), packets)
    return len(packets)


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "samples/synthetic_home.pcap")
    print(f"wrote {build(out)} packets to {out}")

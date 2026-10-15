#!/usr/bin/env python3
"""IPv4 A2S_INFO query, including Steam's optional challenge exchange."""

import argparse
import json
import socket
import sys

REQUEST = b"\xff\xff\xff\xffTSource Engine Query\x00"


def query(host, port=15637, timeout=2):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.send(REQUEST)
        packet = sock.recv(65535)
        if packet[:5] == b"\xff\xff\xff\xffA":
            if len(packet) != 9:
                raise ValueError("Invalid Steam challenge")
            sock.send(REQUEST + packet[5:])
            packet = sock.recv(65535)
    if packet[:5] != b"\xff\xff\xff\xffI" or len(packet) < 6:
        raise ValueError("No valid A2S_INFO response (fragmented replies unsupported)")
    offset = 6
    fields = []
    for _ in range(4):
        end = packet.find(b"\x00", offset)
        if end < 0:
            raise ValueError("Truncated A2S_INFO string")
        fields.append(packet[offset:end].decode("utf-8", errors="replace"))
        offset = end + 1
    if len(packet) < offset + 9:
        raise ValueError("Truncated A2S_INFO fields")
    return {"name": fields[0], "map": fields[1], "game": fields[3],
            "players": packet[offset + 2], "max_players": packet[offset + 3],
            "password_protected": bool(packet[offset + 7])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host")
    parser.add_argument("port", nargs="?", type=int, default=15637)
    parser.add_argument("--timeout", type=float, default=2)
    args = parser.parse_args()
    try:
        print(json.dumps(query(args.host, args.port, args.timeout)))
    except (OSError, ValueError) as exc:
        print(f"Query failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

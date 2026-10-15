import socket
import struct
import threading
import unittest

from scripts.query import query


class QueryTests(unittest.TestCase):
    def serve(self, challenge=False, invalid=False):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        sock.settimeout(3)
        port = sock.getsockname()[1]
        errors = []

        def respond():
            try:
                request, address = sock.recvfrom(4096)
                self.assertEqual(request, b"\xff\xff\xff\xffTSource Engine Query\x00")
                if challenge:
                    sock.sendto(b"\xff\xff\xff\xffA1234", address)
                    request, address = sock.recvfrom(4096)
                    self.assertTrue(request.endswith(b"1234"))
                packet = (b"\xff\xff\xff\xffI\x11World\x00map\x00folder\x00Enshrouded\x00"
                          + struct.pack("<H", 0) + b"\x02\x08\x00dl\x01\x00" + b"1.0\x00")
                sock.sendto(b"bad" if invalid else packet, address)
            except Exception as exc:
                errors.append(exc)
            finally:
                sock.close()

        thread = threading.Thread(target=respond, daemon=True)
        thread.start()
        return port, thread, errors

    def test_real_udp_info_with_and_without_challenge(self):
        for challenge in (False, True):
            port, thread, errors = self.serve(challenge=challenge)
            info = query("127.0.0.1", port, timeout=1)
            thread.join(3)
            self.assertEqual(errors, [])
            self.assertEqual(info["name"], "World")
            self.assertEqual(info["players"], 2)
            self.assertEqual(info["max_players"], 8)
            self.assertTrue(info["password_protected"])

    def test_malformed_response_is_not_healthy(self):
        port, thread, errors = self.serve(invalid=True)
        with self.assertRaises(ValueError):
            query("127.0.0.1", port, timeout=1)
        thread.join(3)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()

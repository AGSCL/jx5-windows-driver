import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "analyze_att", Path(__file__).resolve().parents[1] / "tools" / "analyze_att.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def acl(payload, boundary=2, handle=512):
    return (handle | boundary << 12).to_bytes(2, "little") + len(payload).to_bytes(2, "little") + payload


class ReassemblyTests(unittest.TestCase):
    def test_fragmented_response_exceeding_mtu_is_not_truncated(self):
        response = b"\x0d" + bytes(range(126))
        l2cap = len(response).to_bytes(2, "little") + b"\x04\x00" + response
        assembler = module.Reassembler()
        output = None
        for offset in range(0, len(l2cap), 27):
            output = assembler.feed("3", acl(l2cap[offset:offset + 27], 2 if offset == 0 else 1), "t")
            if offset + 27 < len(l2cap):
                self.assertIsNone(output)
        self.assertEqual(output, ("t", "3", 512, 4, response))
        self.assertFalse(assembler.buffers)

    def test_directions_are_independent(self):
        assembler = module.Reassembler()
        self.assertIsNone(assembler.feed("3", acl(b"\x03\x00\x04\x00\x0b"), "rx"))
        sent = assembler.feed("4", acl(b"\x03\x00\x04\x00\x0a\x42\x00", 0), "tx")
        self.assertEqual(sent[-1], b"\x0a\x42\x00")
        received = assembler.feed("3", acl(b"\x01\x02", 1), "rx-end")
        self.assertEqual(received[-1], b"\x0b\x01\x02")

    def test_redacted_payload_cannot_form_valid_packet(self):
        assembler = module.Reassembler()
        raw = acl(b"\x07\x00\x06\x00\x01\x02\x03\x04\x05\x06\x07")
        self.assertIsNone(assembler.feed("3", raw[:9], "t"))
        self.assertEqual(assembler.excluded["short_or_redacted_acl"], 1)


if __name__ == "__main__":
    unittest.main()

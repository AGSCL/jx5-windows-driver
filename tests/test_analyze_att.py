import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

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


class HidItemsTests(unittest.TestCase):
    def test_real_capture_is_not_repetition_or_rotation(self):
        fixture = json.loads((Path(__file__).parent / "fixtures/jx05_report_map.json").read_text())
        values = [bytes.fromhex(row["value_hex"]) for row in fixture["responses"]]
        prefix, extra = values[0] + values[1], values[2]
        self.assertEqual((len(prefix), len(extra)), (126, 126))
        self.assertNotEqual(prefix, extra)
        self.assertFalse(any(prefix[n:] + prefix[:n] == extra for n in range(len(prefix))))
        self.assertEqual(extra[:18], prefix[63:81])
        self.assertNotEqual(extra[18], prefix[81])
        self.assertEqual(module.parse_hid_items(prefix), {
            "collections": 3, "report_ids": [1, 3], "reports": [
                {"id": 1, "type": "Input", "bits": 32},
                {"id": 3, "type": "Input", "bits": 24}]})
        with self.assertRaises(ValueError):
            module.parse_hid_items(prefix + extra)

    def test_four_byte_size_and_global_push_pop(self):
        data = bytes.fromhex('a101850175089501a4850275049602008100b48100c0')
        # The low size bits 11 represent four bytes, not three.
        data = data.replace(bytes.fromhex('7508'), bytes.fromhex('7708000000'))
        self.assertEqual(module.parse_hid_items(data)["reports"], [
            {"id": 1, "type": "Input", "bits": 8},
            {"id": 2, "type": "Input", "bits": 8}])

    def test_incomplete_or_unsupported_items_do_not_validate(self):
        for data in ('75', '77080000', 'a101', 'c0', 'b4', '8500', 'fe0000',
                     '0c', 'a1018100c0', 'a10175089501810085018100c0'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                module.parse_hid_items(bytes.fromhex(data))


class CapturedReferenceTests(unittest.TestCase):
    def analyze_packets(self, packets):
        namespace = '{' + module.NS['e'] + '}'
        root = ET.Element('Events')
        for packet in packets:
            event = ET.SubElement(root, namespace + 'Event')
            system = ET.SubElement(event, namespace + 'System')
            ET.SubElement(system, namespace + 'TimeCreated', SystemTime=packet['time'])
            fields = ET.SubElement(event, namespace + 'EventData')
            ET.SubElement(fields, namespace + 'Data', Name='BIP_Type').text = packet['direction']
            payload = bytes.fromhex(packet['hex'])
            l2cap = len(payload).to_bytes(2, 'little') + b'\x04\x00' + payload
            ET.SubElement(fields, namespace + 'Data', Name='BIP_Data').text = acl(l2cap).hex()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'capture.xml'
            ET.ElementTree(root).write(path, encoding='utf-8')
            return module.analyze(path, 0x200)

    def test_real_reference_reads_disprove_complete_prefix(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/jx05_att_phase0.json').read_text())
        result = self.analyze_packets(fixture['packets'])
        self.assertEqual(result['mtu'], 64)
        self.assertEqual(len(result['report_map_reads']), 21)
        self.assertEqual(len(result['oversize_att']), 7)
        self.assertEqual({(r['report_handle'], r['descriptor_handle'], r['id'], r['type'])
                          for r in result['report_references']}, {
            ('0x27', '0x29', 1, 'Input'), ('0x2b', '0x2d', 2, 'Input'),
            ('0x2f', '0x30', 1, 'Output'), ('0x32', '0x34', 3, 'Input'),
            ('0x36', '0x38', 4, 'Input'), ('0x3a', '0x3c', 5, 'Input'),
            ('0x3e', '0x40', 6, 'Input')})
        self.assertEqual({(r['id'], r['type']) for r in result['references_missing_from_prefix']},
                         {(2, 'Input'), (4, 'Input'), (5, 'Input'), (6, 'Input'), (1, 'Output')})

    def test_missing_mtu_is_unknown_and_invalid_reference_is_not_inferred(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/jx05_att_phase0.json').read_text())
        packets = [dict(p) for p in fixture['packets'] if p['hex'][:2] not in ('02', '03')]
        for packet in packets:
            if packet['hex'] == '0b0601':
                packet['hex'] = '0b0600'
        result = self.analyze_packets(packets)
        self.assertIsNone(result['mtu'])
        self.assertFalse(result['oversize_att'])
        self.assertTrue(all(r['within_mtu'] is None for r in result['report_map_reads']))
        self.assertEqual(len(result['report_references']), 6)
        self.assertNotIn(6, [r['id'] for r in result['report_references']])


if __name__ == "__main__":
    unittest.main()

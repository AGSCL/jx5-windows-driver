"""Reassemble ATT from Windows BTHPORT tracerpt XML, without exporting SMP keys.

Usage: python tools/analyze_att.py capture.xml --handle 0x200
The HCI connection handle must be identified from the connection-complete event.
This is an offline investigation tool, not a Windows driver.
"""
import argparse
import collections
import json
import xml.etree.ElementTree as ET

NS = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}


class Reassembler:
    def __init__(self):
        self.buffers = {}
        self.excluded = collections.Counter()

    def feed(self, direction, raw, time):
        if len(raw) < 4:
            self.excluded["short_header"] += 1
            return None
        flags = int.from_bytes(raw[:2], "little")
        handle, boundary = flags & 0xFFF, (flags >> 12) & 3
        key = direction, handle
        if len(raw) - 4 != int.from_bytes(raw[2:4], "little"):
            self.buffers.pop(key, None)
            self.excluded["short_or_redacted_acl"] += 1
            return None
        if boundary == 1:
            if key not in self.buffers:
                self.excluded["orphan_continuation"] += 1
                return None
            self.buffers[key][1].extend(raw[4:])
        else:
            if key in self.buffers:
                self.excluded["interrupted_packet"] += 1
            self.buffers[key] = (time, bytearray(raw[4:]))
        start, buf = self.buffers[key]
        if len(buf) < 4:
            return None
        size = int.from_bytes(buf[:2], "little") + 4
        if len(buf) < size:
            return None
        del self.buffers[key]
        if len(buf) != size:
            self.excluded["invalid_l2cap_length"] += 1
            return None
        return start, direction, handle, int.from_bytes(buf[2:4], "little"), bytes(buf[4:])


def analyze(path, selected_handle):
    assembly = Reassembler()
    requested_mtu = None
    mtu = 23
    pending = None
    result = {"handle": hex(selected_handle), "mtu": mtu,
              "characteristics": {}, "report_map_reads": [],
              "oversize_att": [], "report_map_prefix_hex": None}
    # 0x0042 is established as Report Map by characteristic discovery in this
    # capture. Derive it from that discovery rather than hard-coding it.
    report_map_handle = None
    prefix = bytearray()
    for _, event in ET.iterparse(path, events=("end",)):
        if event.tag != "{" + NS["e"] + "}Event":
            continue
        fields = {d.get("Name"): d.text for d in event.findall(".//e:EventData//e:Data", NS)}
        system = event.find("e:System", NS)
        time = system.find("e:TimeCreated", NS).get("SystemTime")
        direction = fields.get("BIP_Type")
        raw = fields.get("BIP_Data")
        event.clear()
        if direction not in ("3", "4") or not raw:
            continue
        packet = assembly.feed(direction, bytes.fromhex(raw.removeprefix("0x")), time)
        if not packet:
            continue
        time, direction, handle, cid, data = packet
        if handle != selected_handle or cid != 4 or not data:
            continue
        if len(data) > mtu:
            result["oversize_att"].append({"time": time, "bytes": len(data), "mtu": mtu})
        if direction == "4":
            # Requests used here are serialized on the fixed ATT bearer.
            if data[0] in (0x02, 0x04, 0x06, 0x08, 0x0A, 0x0C, 0x10, 0x12):
                pending = data
            if data[0] == 2 and len(data) == 3:
                requested_mtu = int.from_bytes(data[1:], "little")
            continue
        if data[0] == 3 and len(data) == 3 and requested_mtu is not None:
            mtu = min(requested_mtu, int.from_bytes(data[1:], "little"))
            result["mtu"] = mtu
        if (data[0] == 9 and len(data) >= 2 and data[1] == 7
                and pending and pending[0] == 8 and pending[5:] == b"\x03\x28"):
            for offset in range(2, len(data) - 6, 7):
                entry = data[offset:offset + 7]
                value_handle = int.from_bytes(entry[3:5], "little")
                uuid = int.from_bytes(entry[5:7], "little")
                result["characteristics"][hex(value_handle)] = {
                    "uuid": hex(uuid), "properties": hex(entry[2])}
                if uuid == 0x2A4B:
                    report_map_handle = value_handle
        if (pending and pending[0] in (0x0A, 0x0C)
                and int.from_bytes(pending[1:3], "little") == report_map_handle
                and data[0] == (0x0B if pending[0] == 0x0A else 0x0D)):
            offset = 0 if pending[0] == 0x0A else int.from_bytes(pending[3:5], "little")
            result["report_map_reads"].append({"time": time, "offset": offset,
                "att_bytes": len(data), "value_bytes": len(data) - 1,
                "within_mtu": len(data) <= mtu})
            # Preserve only the first contiguous prefix whose responses fit the
            # negotiated MTU. Do not claim this is the complete descriptor.
            if offset == len(prefix) and len(data) <= mtu:
                prefix.extend(data[1:])
    result["report_map_handle"] = hex(report_map_handle) if report_map_handle is not None else None
    result["report_map_prefix_hex"] = prefix.hex()
    result["excluded_packets"] = dict(assembly.excluded)
    result["incomplete_packets"] = len(assembly.buffers)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xml")
    parser.add_argument("--handle", required=True, type=lambda value: int(value, 0))
    args = parser.parse_args()
    print(json.dumps(analyze(args.xml, args.handle), indent=2))

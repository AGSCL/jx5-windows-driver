"""Decode this JX-05's captured reports; no keyboard or device operations."""


class Gestures:
    def __init__(self):
        self.reset()

    def reset(self):
        self.start = self.last = None
        self.armed = False
        self.consumer = 0
        self.time = None
        self.hold_y = self.hold_action = self.hold_emitted = None
        self.hold_seed = False
        self.center_time = None
        self.repeat_start = self.repeat_button = None
        self.held_seconds = 0

    def feed(self, data, now):
        if self.time is not None and (now < self.time or now - self.time > 1):
            self.reset()
        self.time = now
        self.held_seconds = 0
        if not data or data[0] != 3:
            self.repeat_start = self.repeat_button = None
        if data == bytes.fromhex('0107f40119') and self.start is None and not self.hold_seed:
            if self.center_time is None:
                self.center_time = now
            return None
        if self.center_time is not None:
            elapsed = now - self.center_time
            self.center_time = None
            if data == bytes.fromhex('0100f40119') and elapsed <= 1:
                self.reset()
                return 'center'
        if len(data) in (4, 5) and data[0] == 3:
            # ID3 has 24 bits; Raw Input's fifth byte is unspecified padding.
            value = int.from_bytes(data[1:4], 'little')
            previous, self.consumer = self.consumer, value
            self.start = self.last = None
            self.armed = False
            self.hold_seed = False
            if previous == 0:
                button = {1: 'lower', 2: 'upper'}.get(value)
                if button:
                    if button != self.repeat_button:
                        self.repeat_button, self.repeat_start = button, now
                    # Firmware sends zero between repeats; silence/another gesture ends the hold.
                    self.held_seconds = now - self.repeat_start
                return button
            return None
        if len(data) != 5 or data[0] != 1:
            self.reset()
            return None
        x = data[2] | ((data[3] & 15) << 8)
        y = (data[3] >> 4) | (data[4] << 4)
        if data[1] == 7 and (x, y) == (500, 160):
            self.start = self.last = None
            self.armed = False
            self.hold_seed = True
            # The ring releases/restarts contacts during a continuous hold.
            self.hold_y = self.hold_action = None
            return None
        if data[1] == 15 and x == 500 and self.hold_seed:
            if self.hold_action is None and self.hold_y is not None and abs(y - self.hold_y) >= 5:
                self.hold_action = 'left' if y > self.hold_y else 'right'
            self.hold_y = y
            if self.hold_action and (self.hold_emitted is None or now - self.hold_emitted >= .75):
                self.hold_emitted = now
                return self.hold_action
            return None
        if not data[1] & 1:
            self.hold_seed = False
        if data[1] == 8:
            self.start = self.last = None
            self.armed = False
            return None
        if data[1] >> 3:
            self.reset()
            return None
        if data[1] & 1:
            if self.start is None and self.armed:
                self.start = (x, y)
                self.armed = False
            if self.start is not None:
                self.last = (x, y)
            return None
        start, last = self.start, self.last
        self.start = self.last = None
        self.armed = data[1] == 0 or (start is None and self.armed)
        if start is not None and last is not None:
            dx, dy = last[0] - start[0], last[1] - start[1]
            # Calibrated from confirmed short presses: dy +850 / -620, dx zero.
            if abs(dx) <= 80 and abs(dy) >= 100:
                return 'upper' if dy > 0 else 'lower'
            if abs(dy) <= 80 and abs(dx) >= 100:
                return 'left' if dx > 0 else 'right'
        return None

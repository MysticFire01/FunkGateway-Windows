"""Source-agnostic self-return detection, ported from Linux protection concepts.

This is a standalone policy engine; callers must explicitly route their
outbound TX-end events and inbound RX start/end events through it. It does
not key hardware, alter routing, or declare a real transmission lost.
"""
from collections import deque
from dataclasses import dataclass
import time


@dataclass(frozen=True)
class ReturnDecision:
    block: bool
    event: str = ""  # "return", "long_rx", "guard_expired", or ""
    escalate: bool = False
    duration_ms: int = 0


class ReturnGuard:
    """Hold *whole* RX passages that begin within the post-TX guard window.

    A long passage is classified separately from a short return; it must
    never be counted toward repeated-return escalation.
    """

    def __init__(self, guard_ms=3500, max_tail_ms=2500,
                 real_passage_ms=5000, window_s=30, count_limit=3,
                 clock=None):
        self.guard_ms = max(0, int(guard_ms))
        self.max_tail_ms = max(100, int(max_tail_ms))
        self.real_passage_ms = max(500, int(real_passage_ms))
        self.window_s = max(5, int(window_s))
        self.count_limit = max(1, int(count_limit))
        self.clock = clock or time.monotonic
        self.guard_until = 0.0
        self.rx_started = None
        self.rx_blocked = False
        self.return_events = deque()

    def clear(self):
        self.guard_until = 0.0
        self.rx_started = None
        self.rx_blocked = False
        self.return_events.clear()

    def tx_finished(self, enabled=True):
        """Call on selected *local* TX completion, not remote RX."""
        if enabled:
            self.guard_until = self.clock() + self.guard_ms / 1000.0

    def rx_changed(self, active):
        now = self.clock()
        if active:
            if self.rx_started is not None:
                return ReturnDecision(self.rx_blocked)
            self.rx_started = now
            self.rx_blocked = bool(self.guard_ms and now <= self.guard_until)
            return ReturnDecision(self.rx_blocked)
        if self.rx_started is None:
            return ReturnDecision(False)
        duration = max(0, round((now - self.rx_started) * 1000))
        blocked = self.rx_blocked
        self.rx_started = None
        self.rx_blocked = False
        if not blocked:
            return ReturnDecision(False, duration_ms=duration)
        if duration >= self.real_passage_ms:
            return ReturnDecision(False, "long_rx", duration_ms=duration)
        if duration > self.max_tail_ms:
            return ReturnDecision(False, "uncertain_rx", duration_ms=duration)
        self.return_events.append(now)
        while self.return_events and now - self.return_events[0] > self.window_s:
            self.return_events.popleft()
        return ReturnDecision(False, "return",
                              len(self.return_events) >= self.count_limit,
                              duration)

    def should_forward_rx(self):
        return not self.rx_blocked

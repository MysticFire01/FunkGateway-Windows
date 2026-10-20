"""Offline policy tests; no soundcard or radio required."""
import unittest
from funkgateway.return_guard import ReturnGuard


class ReturnGuardTests(unittest.TestCase):
    def setUp(self):
        self.now = [100.0]
        self.guard = ReturnGuard(clock=lambda: self.now[0])

    def advance(self, seconds):
        self.now[0] += seconds

    def test_short_echo_blocked_and_counted(self):
        self.guard.tx_finished()
        self.advance(.2)
        self.assertTrue(self.guard.rx_changed(True).block)
        self.advance(.4)
        event = self.guard.rx_changed(False)
        self.assertEqual(event.event, "return")
        self.assertFalse(event.escalate)

    def test_long_real_transmission_not_counted(self):
        self.guard.tx_finished()
        self.advance(.2)
        self.assertTrue(self.guard.rx_changed(True).block)
        self.advance(6)
        event = self.guard.rx_changed(False)
        self.assertEqual(event.event, "long_rx")
        self.assertEqual(len(self.guard.return_events), 0)

    def test_new_rx_outside_guard_allowed(self):
        self.guard.tx_finished()
        self.advance(4)
        self.assertFalse(self.guard.rx_changed(True).block)
        self.assertTrue(self.guard.should_forward_rx())

    def test_three_returns_trigger_escalation(self):
        for count in range(3):
            self.guard.tx_finished()
            self.advance(.1)
            self.assertTrue(self.guard.rx_changed(True).block)
            self.advance(.2)
            event = self.guard.rx_changed(False)
            self.assertEqual(event.escalate, count == 2)

    def test_short_rx_remains_blocked_past_guard_deadline(self):
        self.guard.tx_finished()
        self.advance(3.4)
        self.assertTrue(self.guard.rx_changed(True).block)
        self.advance(2)
        self.assertFalse(self.guard.should_forward_rx())
        self.assertEqual(self.guard.rx_changed(False).event, "return")


if __name__ == "__main__":
    unittest.main()

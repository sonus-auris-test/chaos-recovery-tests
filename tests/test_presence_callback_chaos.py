import random
import unittest
from dataclasses import dataclass


@dataclass
class PresenceHarness:
    phase: str = "idle"
    generation: int = 0
    retry_attempt: int = 0
    authentications: int = 0
    heartbeats: int = 0

    def configure(self) -> int:
        self.generation += 1
        self.phase = "connecting"
        self.retry_attempt = 0
        return self.generation

    def close(self) -> None:
        self.generation += 1
        self.phase = "closed"
        self.retry_attempt = 0

    def event(self, generation: int, kind: str) -> None:
        if generation != self.generation:
            return
        if kind == "ready" and self.phase == "connecting":
            self.phase = "authenticating"
            self.authentications += 1
        elif kind == "authenticated" and self.phase == "authenticating":
            self.phase = "connected"
            self.retry_attempt = 0
        elif kind == "heartbeat" and self.phase == "connected":
            self.heartbeats += 1
        elif kind in {"error", "done"} and self.phase in {
            "connecting",
            "authenticating",
            "connected",
        }:
            self.generation += 1
            self.phase = "waiting"
            self.retry_attempt = min(self.retry_attempt + 1, 7)
        elif kind == "retry" and self.phase == "waiting":
            self.generation += 1
            self.phase = "connecting"

    def invariant(self) -> bool:
        if self.generation < 0 or not 0 <= self.retry_attempt <= 7:
            return False
        if self.phase in {"idle", "closed"} and self.retry_attempt != 0:
            return False
        if self.phase == "waiting" and self.retry_attempt == 0:
            return False
        return self.phase in {
            "idle",
            "connecting",
            "authenticating",
            "connected",
            "waiting",
            "closed",
        }


class PresenceCallbackChaosTests(unittest.TestCase):
    def test_delayed_old_callbacks_never_mutate_the_replacement(self) -> None:
        callback_kinds = ["ready", "authenticated", "heartbeat", "error", "done"]
        for seed in range(100):
            randomizer = random.Random(seed)
            harness = PresenceHarness()
            delayed: list[tuple[int, str]] = []

            for _step in range(250):
                decision = randomizer.random()
                if decision < 0.18 or harness.phase in {"idle", "closed"}:
                    old_generation = harness.generation
                    current_generation = harness.configure()
                    if old_generation > 0:
                        delayed.extend(
                            (old_generation, kind)
                            for kind in randomizer.sample(
                                callback_kinds,
                                k=randomizer.randrange(1, len(callback_kinds) + 1),
                            )
                        )
                    self.assertGreater(current_generation, old_generation)
                elif decision < 0.24:
                    harness.close()
                else:
                    kind = randomizer.choice(callback_kinds + ["retry"])
                    generation = (
                        harness.generation
                        if randomizer.random() < 0.65
                        else max(0, harness.generation - randomizer.randrange(1, 5))
                    )
                    harness.event(generation, kind)

                if delayed and randomizer.random() < 0.45:
                    randomizer.shuffle(delayed)
                    generation, kind = delayed.pop()
                    before = PresenceHarness(**vars(harness))
                    harness.event(generation, kind)
                    if generation != before.generation:
                        self.assertEqual(harness, before, f"seed={seed} kind={kind}")

                self.assertTrue(harness.invariant(), f"seed={seed} state={harness}")

            randomizer.shuffle(delayed)
            for generation, kind in delayed:
                before = PresenceHarness(**vars(harness))
                harness.event(generation, kind)
                if generation != before.generation:
                    self.assertEqual(harness, before, f"seed={seed} kind={kind}")

    def test_close_invalidates_ready_error_and_retry_callbacks(self) -> None:
        harness = PresenceHarness()
        generation = harness.configure()
        harness.close()
        closed = PresenceHarness(**vars(harness))

        for kind in ("ready", "authenticated", "heartbeat", "error", "done", "retry"):
            harness.event(generation, kind)
            self.assertEqual(harness, closed, kind)


if __name__ == "__main__":
    unittest.main()

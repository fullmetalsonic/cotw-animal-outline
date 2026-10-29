"""Independent mode dispatch and death transitions; fake APIs only."""
import copy
import struct
import unittest
from unittest.mock import Mock, patch

import outline_mod as mod


def row(current=20.0, name="pheasant"):
    return dict(wrapper="0x20000", character="0x30000", definition="0x40000",
                vtable_rva="0x1a60028", state_cc=123, flags_d4=5,
                hp_178=(20.0, current),
                definition_path_c0=f"animations/hp_ragdoll/birds/{name}/a.ragdoll")


class ValidationMemory:
    base = 0x140000000

    def __init__(self, current):
        self.current = current
        self.target = row()

    def qword(self, address):
        return {self.base + mod.probe.SINGLETON_RVA: 0x50000,
                0x50000 + 0xB8: 0x60000, 0x20000: 0x30000,
                0x30000: self.base + 0x1A60028, 0x40000 + 0xC0: 0x70000}[address]

    def read(self, address, size):
        if address == 0x20000:
            raw = bytearray(0xD8)
            struct.pack_into("<Q", raw, 0, 0x30000)
            struct.pack_into("<Q", raw, 0x28, 0x40000)
            struct.pack_into("<I", raw, 0xCC, 123)
            struct.pack_into("<I", raw, 0xD4, 5)
            return bytes(raw)
        if address == 0x20000 + 0x178:
            return struct.pack("<2f", 20.0, self.current)
        return self.target["definition_path_c0"].encode().ljust(size, b"\0")


class OneIteration:
    def __init__(self, limit=1):
        self.done = False
        self.limit = limit
        self.ticks = 0

    def is_set(self):
        return self.done

    def set(self):
        self.done = True

    def wait(self, delay):
        self.ticks += 1
        self.done = self.ticks >= self.limit
        return self.done


class ModeTests(unittest.TestCase):
    def worker_backend(self):
        backend = Mock(color="white", writer=1)
        eligibility = mod.LiveBackend.__new__(mod.LiveBackend)
        backend.eligible = eligibility.eligible
        backend.eligible_corpse = eligibility.eligible_corpse
        backend.snapshot.return_value = ([row()], (1, 2), {})
        backend.refresh_corpses.return_value = 0
        return backend

    def test_ninja_transition_keeps_all_selections_and_recovers(self):
        backend = self.worker_backend()
        backend.refresh_ninja.side_effect = [mod.TransientNinjaState("vehicle rebinding"), None]
        worker = mod.ModWorker()
        worker.stopping = OneIteration(limit=2)
        for selection in (worker.requested, worker.corpse_requested, worker.ninja_requested, worker.pet_requested, worker.hellhound_requested):
            selection.set()
        with patch.object(mod, "LiveBackend", return_value=backend):
            worker.run()
        self.assertTrue(all(e.is_set() for e in
                            (worker.requested, worker.corpse_requested, worker.ninja_requested, worker.pet_requested, worker.hellhound_requested)))
        self.assertEqual(backend.write.call_count, 2)
        self.assertEqual(backend.refresh_corpses.call_count, 2)
        self.assertEqual(backend.refresh_ninja.call_count, 2)
        waiting, recovered = worker.messages.get_nowait(), worker.messages.get_nowait()
        self.assertEqual(waiting[0], "모드 ON")
        self.assertEqual(waiting[3], "사체 ON")
        self.assertEqual(waiting[5], "닌자 ON · 상태 전환 대기")
        self.assertEqual(recovered[5], "닌자 ON")
        self.assertEqual(waiting[6], "반려견 윤곽 ON")

    def test_pet_transition_keeps_other_modes_and_recovers(self):
        backend = self.worker_backend()
        backend.refresh_pet.side_effect = [mod.TransientPetState("pet respawning"), None]
        worker = mod.ModWorker()
        worker.stopping = OneIteration(limit=2)
        for selection in (worker.requested, worker.corpse_requested, worker.ninja_requested, worker.pet_requested, worker.hellhound_requested):
            selection.set()
        with patch.object(mod, "LiveBackend", return_value=backend):
            worker.run()
        self.assertTrue(all(e.is_set() for e in
                            (worker.requested, worker.corpse_requested, worker.ninja_requested, worker.pet_requested, worker.hellhound_requested)))
        self.assertEqual(backend.write.call_count, 2)
        self.assertEqual(backend.refresh_corpses.call_count, 2)
        self.assertEqual(backend.refresh_ninja.call_count, 2)
        self.assertEqual(backend.refresh_pet.call_count, 2)
        waiting, recovered = worker.messages.get_nowait(), worker.messages.get_nowait()
        self.assertEqual(waiting[0], "모드 ON")
        self.assertEqual(waiting[3], "사체 ON")
        self.assertEqual(waiting[5], "닌자 ON")
        self.assertEqual(waiting[6], "반려견 윤곽 ON · 연결 대기")
        self.assertEqual(recovered[6], "반려견 윤곽 ON")

    def test_hellhound_transition_keeps_five_selections_and_recovers(self):
        backend = self.worker_backend()
        backend.refresh_hellhound.side_effect = [mod.TransientHellhoundState("retriever rebinding"), None]
        worker = mod.ModWorker()
        worker.stopping = OneIteration(limit=2)
        selections = (worker.requested, worker.corpse_requested, worker.ninja_requested,
                      worker.pet_requested, worker.hellhound_requested)
        self.assertFalse(any(e.is_set() for e in selections))
        for selection in selections:
            selection.set()
        with patch.object(mod, "LiveBackend", return_value=backend):
            worker.run()
        self.assertTrue(all(e.is_set() for e in selections))
        for method in (backend.write, backend.refresh_corpses, backend.refresh_ninja,
                       backend.refresh_pet, backend.refresh_hellhound):
            self.assertEqual(method.call_count, 2)
        waiting, recovered = worker.messages.get_nowait(), worker.messages.get_nowait()
        self.assertEqual(len(waiting), 8)
        self.assertEqual(waiting[7], "헬하운드 ON · 연결 대기")
        self.assertEqual(recovered[7], "헬하운드 ON")
        self.assertEqual(waiting[5:7], ("닌자 ON", "반려견 윤곽 ON"))

    def test_hellhound_fatal_error_does_not_become_transition_waiting(self):
        backend = self.worker_backend()
        backend.refresh_hellhound.side_effect = OSError("failed native write")
        worker = mod.ModWorker()
        worker.stopping = OneIteration()
        selections = (worker.requested, worker.corpse_requested, worker.ninja_requested,
                      worker.pet_requested, worker.hellhound_requested)
        for selection in selections:
            selection.set()
        with patch.object(mod, "LiveBackend", return_value=backend):
            worker.run()
        self.assertFalse(any(e.is_set() for e in selections))
        self.assertEqual(worker.messages.get_nowait()[7], "헬하운드 OFF")
        backend.close.assert_called_once()

    def test_all_backends_close_even_when_an_earlier_keeper_fails(self):
        backend = mod.LiveBackend.__new__(mod.LiveBackend)
        backend.writer = 99
        backend.game = Mock()
        backend.corpse_renderer = Mock()
        backend.ninja_mode = Mock()
        backend.pet_keeper = Mock()
        backend.hellhound_mode = Mock()
        backend.corpse_renderer.close.side_effect = OSError("lease disconnected")
        backend.corpse_writer, backend.ninja_writer, backend.pet_writer, backend.hellhound_writer = 11, 12, 13, 14
        with patch.object(mod.K, "CloseHandle", return_value=True) as close:
            with self.assertRaises(OSError):
                backend.close()
        backend.ninja_mode.close.assert_called_once()
        backend.pet_keeper.close.assert_called_once()
        backend.hellhound_mode.close.assert_called_once()
        backend.game.close.assert_called_once()
        self.assertEqual(sorted(c.args[0] for c in close.call_args_list), [11, 12, 13, 14, 99])

    def test_unverified_ninja_failure_still_turns_modes_off(self):
        backend = self.worker_backend()
        backend.refresh_ninja.side_effect = RuntimeError("foreign patch")
        worker = mod.ModWorker()
        worker.stopping = OneIteration()
        for selection in (worker.requested, worker.corpse_requested, worker.ninja_requested, worker.pet_requested, worker.hellhound_requested):
            selection.set()
        with patch.object(mod, "LiveBackend", return_value=backend):
            worker.run()
        self.assertFalse(any(e.is_set() for e in
                             (worker.requested, worker.corpse_requested, worker.ninja_requested, worker.pet_requested, worker.hellhound_requested)))
        self.assertEqual(worker.messages.get_nowait()[5], "닌자 OFF")

    def test_live_and_dead_routes_are_disjoint_and_exclude_pets(self):
        backend = mod.LiveBackend.__new__(mod.LiveBackend)
        live, dead, pet = row(), row(0), row(0, "bloodhound")
        self.assertTrue(backend.eligible(live))
        self.assertFalse(backend.eligible_corpse(live))
        self.assertFalse(backend.eligible(dead))
        self.assertTrue(backend.eligible_corpse(dead))
        self.assertFalse(backend.eligible(pet))
        self.assertFalse(backend.eligible_corpse(pet))
        for health in (None, (0, 0), (20, float("nan")), (float("inf"), 1)):
            invalid = dict(live, hp_178=health)
            self.assertFalse(backend.eligible(invalid))
            self.assertFalse(backend.eligible_corpse(invalid))

    def test_health_transition_is_checked_again_before_writing(self):
        backend = mod.LiveBackend.__new__(mod.LiveBackend)
        backend.game = ValidationMemory(0)
        context = (0x50000, 0x60000)
        with self.assertRaises(mod.StaleTarget):
            backend.validate(row(20), context)
        backend.validate(row(0), context, corpse=True)
        backend.game.current = 20
        with self.assertRaises(mod.StaleTarget):
            backend.validate(row(0), context, corpse=True)
        backend.validate(row(20), context)

    def test_color_and_off_controls_are_independent(self):
        worker = mod.ModWorker()
        worker.requested.set()
        worker.controller.enable((1, 2))
        worker.corpse_requested.set()
        worker.ninja_requested.set()
        worker.pet_requested.set()
        worker.hellhound_requested.set()
        worker.set_corpse_color((1, 0, 0.5))
        self.assertTrue(worker.requested.is_set())
        self.assertTrue(worker.controller.enabled)
        self.assertFalse(worker.corpse_requested.is_set())
        self.assertTrue(worker.ninja_requested.is_set())
        worker.corpse_requested.set()
        worker.set_color("blue")
        self.assertFalse(worker.requested.is_set())
        self.assertTrue(worker.corpse_requested.is_set())
        self.assertTrue(worker.ninja_requested.is_set())
        worker.requested.set()
        worker.corpse_off()
        self.assertTrue(worker.requested.is_set())
        worker.corpse_requested.set()
        worker.ninja_off()
        self.assertTrue(worker.requested.is_set())
        self.assertTrue(worker.corpse_requested.is_set())
        self.assertTrue(worker.pet_requested.is_set())
        worker.pet_off()
        self.assertTrue(worker.requested.is_set())
        self.assertTrue(worker.corpse_requested.is_set())
        self.assertFalse(worker.pet_requested.is_set())
        worker.pet_requested.set()
        worker.hellhound_off()
        self.assertTrue(worker.requested.is_set())
        self.assertTrue(worker.corpse_requested.is_set())
        self.assertTrue(worker.pet_requested.is_set())
        self.assertFalse(worker.hellhound_requested.is_set())
        worker.hellhound_requested.set()
        worker.ninja_requested.set()
        worker.close()
        self.assertFalse(worker.requested.is_set())
        self.assertFalse(worker.corpse_requested.is_set())
        self.assertFalse(worker.ninja_requested.is_set())
        self.assertFalse(worker.pet_requested.is_set())
        self.assertFalse(worker.hellhound_requested.is_set())

    def test_invalid_corpse_color_keeps_existing_selection(self):
        worker = mod.ModWorker()
        original = worker.corpse_color
        for color in ((-1, 0, 0), (1, 1, 2), (1, 2), (float("nan"), 0, 0)):
            with self.assertRaises(ValueError):
                worker.set_corpse_color(color)
            self.assertEqual(worker.corpse_color, original)

    def test_worker_routes_each_mode_without_cross_writes(self):
        real_backend = mod.LiveBackend
        combinations = [(live, corpse, ninja, pet, hellhound) for live in (False, True) for corpse in (False, True)
                        for ninja in (False, True) for pet in (False, True) for hellhound in (False, True)]
        for live_on, corpse_on, ninja_on, pet_on, hellhound_on in combinations:
            with self.subTest(live=live_on, corpse=corpse_on, ninja=ninja_on, pet=pet_on, hellhound=hellhound_on):
                created = []

                class Backend:
                    eligible = real_backend.eligible
                    eligible_corpse = real_backend.eligible_corpse
                    wild_candidate = real_backend.wild_candidate

                    def __init__(self, color):
                        self.color, self.writer = color, None
                        self.live_writes, self.corpse_writes = [], []
                        self.ninja_updates = 0
                        self.pet_updates = 0
                        self.hellhound_updates = 0
                        self.closed = False
                        created.append(self)

                    def check(self): pass
                    def stop_corpses(self): pass
                    def stop_ninja(self): pass
                    def stop_pet(self): pass
                    def stop_hellhound(self): pass
                    def validate(self, target, context): pass
                    def start_writing(self): self.writer = 1
                    def stop_writing(self): self.writer = None
                    def set_color(self, color): self.color = color
                    def close(self): self.closed = True

                    def refresh_ninja(self):
                        self.ninja_updates += 1

                    def refresh_pet(self):
                        self.pet_updates += 1

                    def refresh_hellhound(self):
                        self.hellhound_updates += 1

                    def snapshot(self):
                        targets = [row(), row(0), row(0, "bloodhound")]
                        return targets, (1, 2), {}

                    def write(self, target):
                        self.live_writes.append(copy.deepcopy(target))

                    def refresh_corpses(self, targets, context, color):
                        self.corpse_writes.extend(copy.deepcopy(t) for t in targets if self.eligible_corpse(t))
                        return len(self.corpse_writes)

                worker = mod.ModWorker()
                worker.stopping = OneIteration()
                if live_on:
                    worker.requested.set()
                if corpse_on:
                    worker.corpse_requested.set()
                if ninja_on:
                    worker.ninja_requested.set()
                if pet_on:
                    worker.pet_requested.set()
                if hellhound_on:
                    worker.hellhound_requested.set()
                with patch.object(mod, "LiveBackend", Backend):
                    worker.run()
                self.assertEqual(len(created), 1)
                backend = created[0]
                self.assertEqual(len(backend.live_writes), int(live_on))
                self.assertEqual(len(backend.corpse_writes), int(corpse_on))
                self.assertEqual(backend.ninja_updates, int(ninja_on))
                self.assertEqual(backend.pet_updates, int(pet_on))
                self.assertEqual(backend.hellhound_updates, int(hellhound_on))
                self.assertTrue(backend.closed)


if __name__ == "__main__":
    unittest.main()

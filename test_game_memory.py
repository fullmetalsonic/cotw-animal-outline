"""Path and failure-boundary tests; never attach to or start the real game."""
import ctypes as C
import hashlib
import io
from pathlib import Path
import unittest
from unittest.mock import patch

import game_memory as memory


class FakeKernel:
    def __init__(self, path, processes=None, query_ok=True, module_ok=True):
        self.path = path
        self.processes = processes if processes is not None else [(321, memory.EXE_NAME)]
        self.query_ok, self.module_ok = query_ok, module_ok
        self.closed, self.access = [], []
        self.index = 0

    def CreateToolhelp32Snapshot(self, flags, pid):
        return 11 if flags == 2 else 22

    def _process(self, pointer):
        if self.index >= len(self.processes):
            return False
        entry = C.cast(pointer, C.POINTER(memory.ProcessEntry)).contents
        entry.pid, entry.exe = self.processes[self.index]
        return True

    def Process32FirstW(self, handle, pointer):
        self.index = 0
        return self._process(pointer)

    def Process32NextW(self, handle, pointer):
        self.index += 1
        return self._process(pointer)

    def Module32FirstW(self, handle, pointer):
        if not self.module_ok:
            return False
        entry = C.cast(pointer, C.POINTER(memory.ModuleEntry)).contents
        entry.name = memory.EXE_NAME
        entry.path = r"C:\unused-truncated-module-path\theHunterCotW_F.exe"
        entry.base, entry.size = 0x140000000, 0x3000000
        return True

    def Module32NextW(self, handle, pointer):
        return False

    def OpenProcess(self, access, inherit, pid):
        self.access.append((access, pid))
        return 33

    def QueryFullProcessImageNameW(self, handle, flags, output, length):
        if not self.query_ok:
            C.set_last_error(5)
            return False
        output.value = self.path
        length._obj.value = len(self.path)
        return True

    def CloseHandle(self, handle):
        self.closed.append(handle)
        return True


class GameDiscoveryTests(unittest.TestCase):
    contents = b"isolated test fixture; not a game executable"

    def create(self, kernel, expected=None):
        opened = []

        def open_fixture(path, *args, **kwargs):
            opened.append(str(path))
            return io.BytesIO(self.contents)

        expected = expected or hashlib.sha256(self.contents).hexdigest()
        with patch.object(memory, "K", kernel), patch.object(memory, "EXPECTED_SHA256", expected), \
                patch.object(Path, "open", autospec=True, side_effect=open_fixture):
            result = memory.GameMemory()
        return result, opened

    def test_other_drives_spaces_and_korean_paths(self):
        paths = [r"D:\SteamLibrary\steamapps\common\theHunterCotW\theHunterCotW_F.exe",
                 r"E:\Games With Spaces\theHunterCotW\theHunterCotW_F.exe",
                 r"F:\게임 모음\스팀 라이브러리\theHunterCotW_F.exe"]
        for path in paths:
            with self.subTest(path=path):
                kernel = FakeKernel(path)
                game, opened = self.create(kernel)
                self.assertEqual(str(game.exe), path)
                self.assertEqual(opened, [path])
                self.assertEqual(kernel.access, [(0x410, 321)])
                self.assertEqual(game.base, 0x140000000)
                with patch.object(memory, "K", kernel):
                    game.close()
                self.assertEqual(kernel.closed, [11, 22, 33])

    def test_no_game_does_not_try_a_default_disk_path(self):
        kernel = FakeKernel("unused", processes=[])
        with patch.object(memory, "K", kernel), patch.object(Path, "open") as opened:
            with self.assertRaisesRegex(RuntimeError, "0개"):
                memory.GameMemory()
            opened.assert_not_called()
        self.assertEqual(kernel.closed, [11])

    def test_two_games_fail_before_opening_a_process(self):
        kernel = FakeKernel("unused", processes=[(1, memory.EXE_NAME), (2, memory.EXE_NAME)])
        with self.assertRaises(RuntimeError):
            self.create(kernel)
        self.assertEqual(kernel.access, [])

    def test_unsupported_hash_closes_the_process(self):
        kernel = FakeKernel(r"D:\Games\theHunterCotW_F.exe")
        with self.assertRaisesRegex(RuntimeError, "지원하지 않는 게임 버전"):
            self.create(kernel, expected="0" * 64)
        self.assertEqual(kernel.closed, [11, 22, 33])

    def test_failed_path_query_closes_the_process(self):
        kernel = FakeKernel("unused", query_ok=False)
        with self.assertRaises(OSError):
            self.create(kernel)
        self.assertEqual(kernel.closed, [11, 22, 33])

    def test_missing_module_closes_both_snapshots(self):
        kernel = FakeKernel("unused", module_ok=False)
        with self.assertRaisesRegex(RuntimeError, "모듈"):
            self.create(kernel)
        self.assertEqual(kernel.closed, [11, 22])


if __name__ == "__main__":
    unittest.main()

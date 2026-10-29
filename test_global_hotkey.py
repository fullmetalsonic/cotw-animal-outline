"""Native registration/message lifecycle, without injecting keyboard input."""
import ctypes as C
from ctypes import wintypes as W
import unittest
from unittest.mock import Mock

from global_hotkey import GlobalHotkey,HOTKEY_ID,HOTKEY_MODIFIERS,HOTKEY_VK,WM_HOTKEY


class HotkeyTests(unittest.TestCase):
    def setup_hotkey(self,registered=True):
        api=Mock()
        api.RegisterHotKey.return_value=registered
        kernel=Mock()
        kernel.GetCurrentThreadId.return_value=123
        return GlobalHotkey(user32=api,kernel32=kernel),api

    def test_registered_key_routes_only_owned_message_and_unregisters(self):
        hotkey,api=self.setup_hotkey()
        messages=iter([(WM_HOTKEY,HOTKEY_ID+1),(WM_HOTKEY,HOTKEY_ID),(0,0)])
        def receive(pointer,*unused):
            message,key=next(messages)
            if not message:return 0
            msg=C.cast(pointer,C.POINTER(W.MSG)).contents
            msg.message,msg.wParam=message,key
            return 1
        api.GetMessageW.side_effect=receive
        hotkey.run()
        api.RegisterHotKey.assert_called_once_with(None,HOTKEY_ID,HOTKEY_MODIFIERS,HOTKEY_VK)
        self.assertEqual([hotkey.events.get_nowait()[0] for _ in range(2)],["ready","toggle"])
        self.assertTrue(hotkey.events.empty())
        api.UnregisterHotKey.assert_called_once_with(None,HOTKEY_ID)

    def test_conflict_reports_unavailable_without_unregistering_someone_else(self):
        hotkey,api=self.setup_hotkey(False)
        hotkey.run()
        self.assertEqual(hotkey.events.get_nowait()[0],"unavailable")
        api.GetMessageW.assert_not_called()
        api.UnregisterHotKey.assert_not_called()

    def test_close_before_start_and_message_error_release_only_owned_key(self):
        hotkey,api=self.setup_hotkey()
        hotkey.close()
        api.PostThreadMessageW.assert_not_called()
        hotkey.run()
        api.GetMessageW.assert_not_called()
        api.UnregisterHotKey.assert_called_once()
        second,api=self.setup_hotkey()
        api.GetMessageW.return_value=-1
        second.run()
        self.assertEqual(second.events.get_nowait()[0],"ready")
        self.assertEqual(second.events.get_nowait()[0],"unavailable")
        second.close()
        api.PostThreadMessageW.assert_called_once_with(123,0x12,0,0)
        api.UnregisterHotKey.assert_called_once()


if __name__=="__main__":
    unittest.main()

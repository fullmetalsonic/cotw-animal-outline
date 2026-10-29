"""Both halves expire together on publication, playback, or cleanup failure."""
import unittest
from unittest.mock import Mock,patch
import silencer_mode as m


class SilencerModeTests(unittest.TestCase):
    def mode(self):
        ai,audio=Mock(),Mock()
        audio.stats.return_value={"failed":0}
        with patch.object(m,"SilencerAiMode",return_value=ai),patch.object(m,"SilencerAudioMode",return_value=audio):
            mode=m.SilencerMode(None,None)
        return mode,ai,audio

    def test_publication_error_and_new_native_audio_failure_disable_both_halves(self):
        for half in ("ai","audio"):
            with self.subTest(half=half):
                mode,ai,audio=self.mode()
                getattr(mode,half).publish.side_effect=OSError("lost process")
                with self.assertRaises(OSError):mode.publish()
                ai.disable.assert_called_once()
                audio.disable.assert_called_once()
        mode,ai,audio=self.mode()
        mode.publish()
        audio.stats.return_value={"failed":1}
        with self.assertRaisesRegex(RuntimeError,"audio replacement failed"):mode.publish()
        ai.disable.assert_called_once()
        audio.disable.assert_called_once()

    def test_cleanup_failure_in_one_half_does_not_leave_the_other_active(self):
        mode,ai,audio=self.mode()
        ai.disable.side_effect=OSError("lease write")
        with self.assertRaises(OSError):mode.disable()
        audio.disable.assert_called_once()
        ai.close.side_effect=OSError("restore write")
        with self.assertRaises(OSError):mode.close()
        audio.close.assert_called_once()

    def test_first_shot_error_is_not_mistaken_for_a_historical_counter(self):
        mode,ai,audio=self.mode()
        audio.stats.side_effect=[{"failed":4},{"failed":5}]
        with self.assertRaisesRegex(RuntimeError,"audio replacement failed"):mode.publish()
        audio.install.assert_called_once()
        ai.disable.assert_called_once()
        audio.disable.assert_called_once()

    def test_off_interval_failures_do_not_disable_the_next_activation(self):
        mode,ai,audio=self.mode()
        mode.publish()
        mode.disable()
        audio.stats.return_value={"failed":1}
        mode.publish()
        self.assertEqual(mode.audio_failures,1)
        self.assertEqual(audio.install.call_count,2)
        audio.stats.return_value={"failed":2}
        with self.assertRaisesRegex(RuntimeError,"audio replacement failed"):mode.publish()
        self.assertIsNone(mode.audio_failures)


if __name__=="__main__":unittest.main()

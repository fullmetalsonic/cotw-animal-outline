"""One user switch owns both player audio and the native AI sound profile."""
from silencer_ai_mode import SilencerAiMode
from silencer_audio_mode import SilencerAudioMode


class SilencerMode:
    def __init__(self, game, writer):
        self.ai = SilencerAiMode(game, writer)
        self.audio = SilencerAudioMode(game, writer)
        self.audio_failures = None

    def publish(self):
        try:
            if self.audio_failures is None:
                self.audio.install()
                self.audio_failures = self.audio.stats().get("failed",0)
            self.ai.publish()
            self.audio.publish()
            failures = self.audio.stats().get("failed")
            if self.audio_failures is not None and failures is not None and failures > self.audio_failures:
                raise RuntimeError("Silencer audio replacement failed; original sounds have been restored")
            if failures is not None:
                self.audio_failures = failures
        except Exception:
            self.disable()
            raise

    def disable(self):
        try:
            self.ai.disable()
        finally:
            try:
                self.audio.disable()
            finally:
                self.audio_failures = None

    def close(self):
        try:
            self.ai.close()
        finally:
            self.audio.close()

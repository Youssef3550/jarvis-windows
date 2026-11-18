"""Unit tests for tts.py voice selection. No model download: Coqui is faked.

Run from the project folder:  .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""
import asyncio
import io
import sys
import unittest
import wave
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tts  # noqa: E402


class FakeSynth:
    output_sample_rate = 22050


class FakeModel:
    speakers = ["ED\n", "p273", "p330"]
    synthesizer = FakeSynth()

    def __init__(self):
        self.calls = []

    def tts(self, text, **kwargs):
        self.calls.append((text, kwargs))
        return [0.0, 0.5, -0.5, 1.5] * 100          # 1.5 must be clipped


def fake_voice(speaker="p273", speaker_wav=""):
    v = tts.CoquiVoice("fake/model", speaker, speaker_wav)
    v._model = FakeModel()
    return v


def run(coro):
    return asyncio.run(coro)


class ToWavTest(unittest.TestCase):
    def test_valid_16bit_mono_wav(self):
        data = tts.to_wav([0.0, 1.0, -1.0, 2.0], 22050)
        with wave.open(io.BytesIO(data)) as w:
            self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()),
                             (1, 2, 22050, 4))


class CoquiVoiceTest(unittest.TestCase):
    def test_uses_configured_speaker(self):
        v = fake_voice("p330")
        self.assertTrue(v.wav("Hello there, sir.").startswith(b"RIFF"))
        self.assertEqual(v._model.calls[0][1], {"speaker": "p330"})

    def test_cloning_passes_speaker_wav_and_language(self):
        v = fake_voice(speaker_wav=r"C:\voices\me.wav")
        v.wav("Hello.")
        self.assertEqual(v._model.calls[0][1], {"speaker_wav": r"C:\voices\me.wav", "language": "en"})

    def test_load_failure_is_remembered(self):
        v = tts.CoquiVoice("fake/model")
        v.error = "boom"
        self.assertFalse(v.warm_up())
        with self.assertRaises(RuntimeError):
            v.wav("Hello.")


class SynthesizeTest(unittest.TestCase):
    def test_english_uses_coqui_wav(self):
        with mock.patch.object(tts, "coqui", fake_voice()), \
             mock.patch.object(tts, "_edge_mp3", mock.AsyncMock(return_value=b"mp3")) as edge:
            audio, mime = run(tts.synthesize("Good evening, sir.", "en"))
        self.assertEqual(mime, "audio/wav")
        self.assertTrue(audio.startswith(b"RIFF"))
        edge.assert_not_called()

    def test_dutch_uses_edge(self):
        v = fake_voice()
        with mock.patch.object(tts, "coqui", v), \
             mock.patch.object(tts, "_edge_mp3", mock.AsyncMock(return_value=b"mp3")):
            self.assertEqual(run(tts.synthesize("Goedenavond meneer.", "nl")), (b"mp3", "audio/mpeg"))
        self.assertEqual(v._model.calls, [])

    def test_coqui_failure_falls_back_to_edge(self):
        v = fake_voice()
        v._model.tts = mock.Mock(side_effect=RuntimeError("synthesis failed"))
        with mock.patch.object(tts, "coqui", v), \
             mock.patch.object(tts, "_edge_mp3", mock.AsyncMock(return_value=b"mp3")):
            self.assertEqual(run(tts.synthesize("Hello sir.", "en")), (b"mp3", "audio/mpeg"))

    def test_no_coqui_uses_edge(self):
        with mock.patch.object(tts, "coqui", None), \
             mock.patch.object(tts, "_edge_mp3", mock.AsyncMock(return_value=b"mp3")):
            self.assertEqual(run(tts.synthesize("Hello sir.", "en")), (b"mp3", "audio/mpeg"))

    def test_nothing_works_returns_none(self):
        with mock.patch.object(tts, "coqui", None), \
             mock.patch.object(tts, "_edge_mp3", mock.AsyncMock(return_value=None)):
            self.assertIsNone(run(tts.synthesize("Hello sir.", "en")))

    def test_empty_text(self):
        self.assertIsNone(run(tts.synthesize("   ", "en")))


if __name__ == "__main__":
    unittest.main()

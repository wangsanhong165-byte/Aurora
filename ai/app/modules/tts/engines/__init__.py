"""TTS engines — import all classes so @TTSFactory.register fires."""
from app.modules.tts.engines.edge import EdgeTTS  # noqa: F401
from app.modules.tts.engines.gsvi import GSVITTS  # noqa: F401
from app.modules.tts.engines.gsvi_v2 import GSVIV2TTS  # noqa: F401
from app.modules.tts.engines.qwen import QwenTTS  # noqa: F401
from app.modules.tts.engines.pyttsx3 import Pyttsx3TTS  # noqa: F401
from app.modules.tts.engines.cloud import CloudTTS  # noqa: F401

"""
Testes unitários para o módulo core/transcriber.py.
"""

import os
import wave
import struct
import subprocess
import imageio_ffmpeg
import pytest

from core.transcriber import AudioTranscriber
from core.srt_parser import SubtitleItem


@pytest.fixture
def synthetic_audio_video(tmp_path):
    """Cria um arquivo de vídeo com faixa de áudio sintética usando FFmpeg."""
    ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
    out_video = str(tmp_path / "video_com_audio.mp4")

    # Gera um vídeo de 2 segundos com áudio senoidal usando lavfi do ffmpeg
    cmd = [
        ffmpeg_bin,
        "-y",
        "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-shortest",
        out_video
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return out_video


def test_audio_extraction(synthetic_audio_video, tmp_path):
    transcriber = AudioTranscriber(model_size="tiny")
    wav_out = str(tmp_path / "extraido.wav")
    
    transcriber.extract_audio(synthetic_audio_video, wav_out)
    assert os.path.exists(wav_out)
    assert os.path.getsize(wav_out) > 1000

    # Verifica se o arquivo gerado é WAV 16kHz mono
    with wave.open(wav_out, 'rb') as wf:
        assert wf.getnchannels() == 1
        assert wf.getframerate() == 16000


def test_save_srt(tmp_path):
    transcriber = AudioTranscriber(model_size="tiny")
    items = [
        SubtitleItem(index=1, start_seconds=1.2, end_seconds=3.8, text="Teste de transcrição automática."),
        SubtitleItem(index=2, start_seconds=4.0, end_seconds=6.5, text="Exportação em arquivo srt.")
    ]
    srt_out = str(tmp_path / "saida.srt")
    transcriber.save_srt(items, srt_out)

    assert os.path.exists(srt_out)
    with open(srt_out, "r", encoding="utf-8") as f:
        content = f.read()

    assert "00:00:01,200 --> 00:00:03,800" in content
    assert "Teste de transcrição automática." in content
    assert "00:00:04,000 --> 00:00:06,500" in content

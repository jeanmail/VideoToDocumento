"""
Testes unitários para o módulo core/video_processor.py usando vídeo sintético.
"""

import os
import cv2
import numpy as np
import pytest

from core.video_processor import (
    VideoProcessor,
    compute_dhash,
    calculate_similarity,
    ExtractedFrame
)
from core.srt_parser import SubtitleItem


@pytest.fixture
def sample_video(tmp_path):
    """Cria um vídeo sintético de 4 segundos a 10 FPS."""
    video_file = str(tmp_path / "synthetic_test.mp4")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    fps = 10.0
    width, height = 320, 240
    out = cv2.VideoWriter(video_file, fourcc, fps, (width, height))

    # Primeiros 2 segundos: imagem azul com texto A
    for i in range(20):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :] = (200, 50, 50)  # Azul
        cv2.putText(frame, "Tela 1", (50, 120), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        out.write(frame)

    # Próximos 2 segundos: imagem verde com texto B
    for i in range(20):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :] = (50, 200, 50)  # Verde
        cv2.putText(frame, "Tela 2", (50, 120), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        out.write(frame)

    out.release()
    return video_file


def test_dhash_and_similarity():
    # Padrão listrado vertical
    img1 = np.zeros((100, 100, 3), dtype=np.uint8)
    img1[:, ::2] = 255
    hash1 = compute_dhash(img1)

    # Imagem idêntica deve ter similaridade 1.0
    assert calculate_similarity(hash1, hash1) == 1.0

    # Padrão com contraste invertido
    img2 = np.zeros((100, 100, 3), dtype=np.uint8)
    img2[:, 1::2] = 255
    hash2 = compute_dhash(img2)
    assert calculate_similarity(hash1, hash2) < 0.2


def test_video_processor_extraction(sample_video, tmp_path):
    processor = VideoProcessor(sample_video)
    assert processor.duration_seconds >= 3.9

    output_dir = str(tmp_path / "frames")

    subtitles = [
        SubtitleItem(index=1, start_seconds=0.5, end_seconds=1.5, text="Primeira tela"),
        SubtitleItem(index=2, start_seconds=2.5, end_seconds=3.5, text="Segunda tela"),
    ]

    frames = processor.process_subtitles(
        subtitles=subtitles,
        output_dir=output_dir,
        min_interval_seconds=0.5,
        similarity_threshold=0.85
    )

    assert len(frames) == 2
    assert os.path.exists(frames[0].image_path)
    assert os.path.exists(frames[1].image_path)
    assert frames[0].subtitle_text == "Primeira tela"
    assert frames[1].subtitle_text == "Segunda tela"

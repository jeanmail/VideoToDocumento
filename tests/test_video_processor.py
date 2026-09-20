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


def test_detect_non_system_frame():
    from core.video_processor import detect_non_system_frame
    
    # 1. Tela vazia ou sem estrutura (deve ser detectada como sem interface)
    blank_img = np.zeros((480, 640, 3), dtype=np.uint8)
    is_non_sys, reason = detect_non_system_frame(blank_img)
    assert is_non_sys is True
    assert "sem interface" in reason.lower()

    # 2. Tela de sistema (com bordas ortogonais e tabelas)
    ui_img = np.full((480, 640, 3), 245, dtype=np.uint8) # Fundo claro de sistema
    # Desenha janela e tabela com linhas pretas horizontais e verticais
    for y in range(50, 400, 30):
        cv2.line(ui_img, (50, y), (590, y), (40, 40, 40), 2)
    for x in range(50, 600, 100):
        cv2.line(ui_img, (x, 50), (x, 400), (40, 40, 40), 2)
    cv2.putText(ui_img, "SISTEMA ERP - CADASTRO", (60, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    
    is_non_sys_ui, _ = detect_non_system_frame(ui_img)
    assert is_non_sys_ui is False

    # 3. Simulação de webcam (tons de pele predominantes)
    # BGR para tom de pele comum: ex B=130, G=150, R=210
    skin_img = np.full((480, 640, 3), (120, 140, 205), dtype=np.uint8)
    is_non_sys_skin, skin_reason = detect_non_system_frame(skin_img)
    assert is_non_sys_skin is True
    assert "câmera" in skin_reason.lower() or "pessoas" in skin_reason.lower()


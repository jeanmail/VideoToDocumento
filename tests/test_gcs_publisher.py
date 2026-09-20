"""
Testes unitários para o módulo core/gcs_publisher.py.
"""

import os
import cv2
import numpy as np

from core.gcs_publisher import GCSPublisher, SUPPORTED_PROJECTS
from core.video_processor import ExtractedFrame
from core.srt_parser import SubtitleItem


def test_supported_projects():
    projects = GCSPublisher.get_supported_projects()
    expected_slugs = [
        "prescricao-digital",
        "automation",
        "onetouch",
        "personal",
        "clinic",
        "monitoring",
        "agenda-online"
    ]
    for slug in expected_slugs:
        assert slug in projects


def test_generate_multimodal_markdown(tmp_path):
    img_path = str(tmp_path / "print_test.jpg")
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.imwrite(img_path, img)

    frames = [
        ExtractedFrame(
            id="f1",
            timestamp_seconds=5.0,
            timestamp_str="00:00:05",
            subtitle_text="Acesse o módulo de prescrição.",
            image_path=img_path,
            step_title="Acesso ao Módulo",
            ocr_text="Prescrição | Pacientes",
            selected=True
        )
    ]

    subs = [
        SubtitleItem(index=1, start_seconds=1.0, end_seconds=4.0, text="Introdução ao sistema."),
        SubtitleItem(index=2, start_seconds=5.0, end_seconds=8.0, text="Acesse o módulo de prescrição."),
    ]

    publisher = GCSPublisher(default_bucket="meu-bucket-teste")
    md = publisher.generate_multimodal_markdown(
        project_slug="prescricao-digital",
        title="Guia de Prescrição",
        approved_frames=frames,
        all_subtitles=subs,
        bucket_name="meu-bucket-teste"
    )

    # Verifica se a URL da imagem do GCS foi inserida no Markdown
    expected_img_url = f"https://storage.googleapis.com/meu-bucket-teste/prescricao-digital/prints/{os.path.basename(img_path)}"
    assert expected_img_url in md
    assert "![Acesso ao Módulo]" in md
    assert "Introdução ao sistema." in md
    assert "Acesse o módulo de prescrição." in md
    assert "Prescrição | Pacientes" in md


def test_prepare_local_package(tmp_path):
    img_path = str(tmp_path / "print_menu.jpg")
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.imwrite(img_path, img)

    frames = [
        ExtractedFrame(
            id="f1",
            timestamp_seconds=2.0,
            timestamp_str="00:00:02",
            subtitle_text="Passo 1",
            image_path=img_path,
            step_title="Menu Inicial",
            selected=True
        )
    ]

    subs = [
        SubtitleItem(index=1, start_seconds=1.0, end_seconds=3.0, text="Passo 1")
    ]

    output_dir = str(tmp_path / "pacotes")
    publisher = GCSPublisher(default_bucket="bucket-prod")
    files_map = publisher.prepare_local_package(
        project_slug="clinic",
        output_dir=output_dir,
        title="Manual Clinic",
        approved_frames=frames,
        all_subtitles=subs,
        bucket_name="bucket-prod"
    )

    assert "clinic/knowledge_base.md" in files_map
    assert f"clinic/prints/{os.path.basename(img_path)}" in files_map
    assert "clinic/transcricao.srt" in files_map

    # Verifica se os arquivos físicos foram criados
    assert os.path.exists(files_map["clinic/knowledge_base.md"])
    assert os.path.exists(files_map[f"clinic/prints/{os.path.basename(img_path)}"])
    assert os.path.exists(files_map["clinic/transcricao.srt"])

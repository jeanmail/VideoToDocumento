"""
Teste de integração de ponta a ponta do fluxo do VideoToDocument.
"""

import os
import cv2
import numpy as np

from core.srt_parser import parse_srt, group_subtitles
from core.video_processor import VideoProcessor
from core.doc_builder import DocumentBuilder

def test_full_pipeline(tmp_path):
    # 1. Cria vídeo sintético de 6 segundos
    video_path = str(tmp_path / "treinamento.mp4")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    fps = 10.0
    width, height = 400, 300
    out = cv2.VideoWriter(video_path, fourcc, fps, (width, height))

    # Segmento 1: tela vermelha (0-2s)
    for _ in range(20):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :] = (30, 30, 180)
        cv2.putText(frame, "Menu Principal", (40, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        out.write(frame)

    # Segmento 2: tela repetida/duplicada (2-4s)
    for _ in range(20):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :] = (30, 30, 180)
        cv2.putText(frame, "Menu Principal", (40, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        out.write(frame)

    # Segmento 3: tela nova (4-6s)
    for _ in range(20):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :] = (180, 50, 30)
        cv2.putText(frame, "Configuracoes Concluidas", (30, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        out.write(frame)

    out.release()

    # 2. Cria SRT correspondente
    srt_content = """1
00:00:00,500 --> 00:00:01,800
Abra o menu principal do sistema.

2
00:00:02,200 --> 00:00:03,500
Observe as opcoes disponiveis na mesma tela.

3
00:00:04,500 --> 00:00:05,800
Agora clique em concluir configuracao.
"""
    subtitles = parse_srt(srt_content)
    assert len(subtitles) == 3

    # 3. Processamento de Vídeo
    frames_dir = str(tmp_path / "extracted_frames")
    processor = VideoProcessor(video_path)
    extracted = processor.process_subtitles(
        subtitles=subtitles,
        output_dir=frames_dir,
        min_interval_seconds=1.0,
        similarity_threshold=0.85
    )

    assert len(extracted) >= 2
    # O segundo frame deve ter sido detectado como candidato a duplicata
    assert any(f.is_duplicate_candidate for f in extracted)

    # 4. Simulação de auditoria: aprovar apenas não duplicados
    approved = [f for f in extracted if not f.is_duplicate_candidate]
    assert len(approved) >= 1

    # 5. Geração de documentos finais
    output_docx = str(tmp_path / "guia_final.docx")
    output_pdf = str(tmp_path / "guia_final.pdf")

    builder = DocumentBuilder(title="Treinamento Integrado", subtitle="Teste E2E")
    builder.build_docx(approved, output_docx)
    builder.build_pdf(approved, output_pdf)

    assert os.path.exists(output_docx) and os.path.getsize(output_docx) > 0
    assert os.path.exists(output_pdf) and os.path.getsize(output_pdf) > 0

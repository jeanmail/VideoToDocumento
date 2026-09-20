"""
Testes unitários para o módulo core/doc_builder.py.
"""

import os
import numpy as np
import cv2
import docx

from core.doc_builder import DocumentBuilder
from core.video_processor import ExtractedFrame


def test_build_docx_and_pdf(tmp_path):
    # Cria uma imagem temporária válida
    img_path = str(tmp_path / "test_frame.jpg")
    img = np.zeros((200, 300, 3), dtype=np.uint8)
    cv2.putText(img, "Test Screen", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.imwrite(img_path, img)

    frames = [
        ExtractedFrame(
            id="f1",
            timestamp_seconds=1.5,
            timestamp_str="00:00:01",
            subtitle_text="Passo 1: Abra a janela de preferências.",
            image_path=img_path,
            step_title="Abertura de Preferências",
            ocr_text="Arquivo | Editar | Preferências",
            selected=True
        ),
        ExtractedFrame(
            id="f2",
            timestamp_seconds=5.0,
            timestamp_str="00:00:05",
            subtitle_text="Passo 2: Clique no botão salvar.",
            image_path=img_path,
            step_title="Salvar alterações",
            ocr_text="Salvar | Cancelar",
            selected=True
        )
    ]

    builder = DocumentBuilder(title="Guia de Teste", subtitle="Subtítulo de Teste")
    
    # Teste DOCX
    docx_output = str(tmp_path / "teste.docx")
    builder.build_docx(frames, docx_output)
    assert os.path.exists(docx_output)
    assert os.path.getsize(docx_output) > 1000

    doc = docx.Document(docx_output)
    full_text = "\n".join([p.text for p in doc.paragraphs])
    assert "Guia de Teste" in full_text
    assert "[TIMESTAMP: 00:00:01] - Abertura de Preferências" in full_text
    assert "Abra a janela de preferências" in full_text

    # Teste PDF
    pdf_output = str(tmp_path / "teste.pdf")
    builder.build_pdf(frames, pdf_output)
    assert os.path.exists(pdf_output)
    assert os.path.getsize(pdf_output) > 1000

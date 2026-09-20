"""
Testes unitários para o DocumentBuilder com transcrição completa intercalada com imagens aprovadas.
"""

import os
import cv2
import numpy as np
import docx

from core.doc_builder import DocumentBuilder
from core.video_processor import ExtractedFrame
from core.srt_parser import SubtitleItem


def test_interleaved_doc_builder(tmp_path):
    # Cria uma imagem de teste
    img_path = str(tmp_path / "print_aprovado.jpg")
    img = np.zeros((200, 300, 3), dtype=np.uint8)
    cv2.putText(img, "Tela Aprovada", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.imwrite(img_path, img)

    # 4 falas no treinamento:
    # Sub 1: Abertura (sem print)
    # Sub 2: Ação com print aprovado
    # Sub 3: Explicação intermediária (print foi descartado na auditoria)
    # Sub 4: Conclusão com print aprovado
    all_subs = [
        SubtitleItem(index=1, start_seconds=1.0, end_seconds=4.0, text="Sejam bem-vindos à abertura do treinamento."),
        SubtitleItem(index=2, start_seconds=6.0, end_seconds=9.0, text="Primeiro clique no menu de cadastros."),
        SubtitleItem(index=3, start_seconds=11.0, end_seconds=14.0, text="Aguarde o carregamento dos registros na base."),
        SubtitleItem(index=4, start_seconds=16.0, end_seconds=20.0, text="Por fim, confirme clicando no botão verde."),
    ]

    # Apenas os passos 2 e 4 possuem prints aprovados
    approved_frames = [
        ExtractedFrame(
            id="f1",
            timestamp_seconds=7.0,
            timestamp_str="00:00:07",
            subtitle_text="Primeiro clique no menu de cadastros.",
            image_path=img_path,
            step_title="Acesso aos Cadastros",
            selected=True
        ),
        ExtractedFrame(
            id="f2",
            timestamp_seconds=18.0,
            timestamp_str="00:00:18",
            subtitle_text="Por fim, confirme clicando no botão verde.",
            image_path=img_path,
            step_title="Confirmação Final",
            selected=True
        )
    ]

    builder = DocumentBuilder(title="Treinamento Integral", subtitle="Apostila Completa")
    docx_path = str(tmp_path / "documento_integral.docx")
    pdf_path = str(tmp_path / "documento_integral.pdf")

    builder.build_docx(approved_frames, docx_path, all_subtitles=all_subs)
    builder.build_pdf(approved_frames, pdf_path, all_subtitles=all_subs)

    assert os.path.exists(docx_path)
    assert os.path.exists(pdf_path)

    # Validar no DOCX que 100% da transcrição está presente
    doc = docx.Document(docx_path)
    full_text = "\n".join([p.text for p in doc.paragraphs])

    # Verifica se as falas SEM imagem estão no documento
    assert "Sejam bem-vindos à abertura do treinamento." in full_text
    assert "Aguarde o carregamento dos registros na base." in full_text

    # Verifica se as falas COM imagem estão no documento com os devidos cabeçalhos
    assert "Acesso aos Cadastros" in full_text
    assert "Confirmação Final" in full_text
    assert "Primeiro clique no menu de cadastros." in full_text
    assert "Por fim, confirme clicando no botão verde." in full_text

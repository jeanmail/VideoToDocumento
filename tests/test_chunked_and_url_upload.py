"""
Testes unitários e de integração para upload em partes (chunked) e ingestão por URL.
"""

import os
import io
import pytest
from fastapi.testclient import TestClient
import server

client = TestClient(server.app)


def test_chunked_upload_and_reassembly(tmp_path):
    """
    Testa se o fatiamento em partes reconstitui exatamente o binário original bit a bit.
    """
    original_data = b"VideoContentBitstreamTestData_1234567890" * 1000
    upload_id = "test_upload_session_001"
    chunk_size = 5000
    total_chunks = (len(original_data) + chunk_size - 1) // chunk_size

    # 1. Envia as partes
    for i in range(total_chunks):
        chunk_bytes = original_data[i * chunk_size : (i + 1) * chunk_size]
        response = client.post(
            "/api/upload/chunk",
            data={
                "upload_id": upload_id,
                "chunk_index": i,
                "total_chunks": total_chunks,
            },
            files={"chunk_file": ("test.mp4", io.BytesIO(chunk_bytes), "application/octet-stream")},
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

    # 2. Conclui e reconstitui
    comp_resp = client.post(
        "/api/upload/complete",
        data={
            "upload_id": upload_id,
            "filename": "treinamento_teste.mp4",
            "total_chunks": total_chunks,
        },
    )
    assert comp_resp.status_code == 200
    data = comp_resp.json()
    assert data["success"] is True
    saved_path = data["saved_video_path"]
    assert os.path.exists(saved_path)
    assert data["file_size"] == len(original_data)

    # 3. Validação bit a bit
    with open(saved_path, "rb") as f:
        reconstructed = f.read()
    assert reconstructed == original_data

    # Cleanup
    if os.path.exists(saved_path):
        os.remove(saved_path)


def test_extract_google_drive_file_id():
    """
    Testa a extração de File ID a partir de múltiplos formatos de links do Drive.
    """
    url1 = "https://drive.google.com/file/d/19lyO6Mw9KUWjlTPE2eVOpyqLujnbcuMP/view"
    assert server.extract_google_drive_file_id(url1) == "19lyO6Mw9KUWjlTPE2eVOpyqLujnbcuMP"

    url2 = "https://drive.google.com/file/d/19lyO6Mw9KUWjlTPE2eVOpyqLujnbcuMP/view?usp=sharing"
    assert server.extract_google_drive_file_id(url2) == "19lyO6Mw9KUWjlTPE2eVOpyqLujnbcuMP"

    url3 = "https://drive.google.com/uc?export=download&id=19lyO6Mw9KUWjlTPE2eVOpyqLujnbcuMP"
    assert server.extract_google_drive_file_id(url3) == "19lyO6Mw9KUWjlTPE2eVOpyqLujnbcuMP"

    url4 = "https://meusite.com/video.mp4"
    assert server.extract_google_drive_file_id(url4) is None

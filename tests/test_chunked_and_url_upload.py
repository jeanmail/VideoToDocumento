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


def test_job_state_persistence_and_recovery():
    """
    Testa se o estado de um job é salvo em disco e recuperado com sucesso caso
    uma requisição de polling ou export caia em outra instância/worker ou após limpar da memória.
    """
    test_job_id = "job_test_persistence_999"
    server.extraction_jobs[test_job_id] = {
        "status": "completed",
        "stage": "done",
        "progress": 1.0,
        "message": "Processamento concluído com sucesso!",
        "result": {"frames": [], "video_name": "teste"},
        "error": None,
    }
    server.save_job_state(test_job_id)

    # Verifica se o arquivo JSON foi criado no diretório JOBS_DIR
    job_file = os.path.join(server.JOBS_DIR, f"{test_job_id}.json")
    assert os.path.exists(job_file)

    # Remove o job da memória simulando outra instância de Cloud Run
    del server.extraction_jobs[test_job_id]
    assert test_job_id not in server.extraction_jobs

    # Faz requisição ao endpoint de progresso
    resp = client.get(f"/api/extract/progress/{test_job_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["progress"] == 1.0
    assert data["result"]["video_name"] == "teste"

    # Cleanup
    if os.path.exists(job_file):
        os.remove(job_file)
    meta_file = os.path.join(server.JOBS_DIR, f"{test_job_id}.meta")
    if os.path.exists(meta_file):
        os.remove(meta_file)


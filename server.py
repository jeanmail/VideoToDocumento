"""
FastAPI Server para VideoToDocumento.
Serve a API REST para extração, auditoria, downloads e publicação GCS,
além de servir os arquivos estáticos compilados do React na mesma porta.
"""

import os
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
import logging
import traceback
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# Definir BASE_DIR ANTES de qualquer coisa
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Configurar logging
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "videotodocumento.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

from core.srt_parser import parse_subtitles, group_subtitles, export_to_srt, SubtitleItem
from core.video_processor import VideoProcessor, ExtractedFrame, ensure_thumbnail
from core.doc_builder import DocumentBuilder
from core.transcriber import AudioTranscriber
from core.gcs_publisher import GCSPublisher, SUPPORTED_PROJECTS, slugify_training_name
STORAGE_DIR = os.path.join(BASE_DIR, "storage")
TEMP_UPLOADS = os.path.join(STORAGE_DIR, "temp_uploads")
EXTRACTED_FRAMES = os.path.join(STORAGE_DIR, "extracted_frames")
OUTPUTS_DIR = os.path.join(STORAGE_DIR, "outputs")
FRONTEND_DIST = os.path.join(BASE_DIR, "frontend", "dist")

for d in [TEMP_UPLOADS, EXTRACTED_FRAMES, OUTPUTS_DIR]:
    os.makedirs(d, exist_ok=True)

app = FastAPI(title="VideoToDocument API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Removido estado global - agora tudo é armazenado em extraction_jobs[job_id]

# Monta armazenamento estático para que o frontend carregue os frames e thumbnails
app.mount("/storage", StaticFiles(directory=STORAGE_DIR), name="storage")


class AdjustTimeRequest(BaseModel):
    delta_seconds: float


class PublishGCSRequest(BaseModel):
    title: str
    description: Optional[str] = ""
    product_slug: str
    bucket_name: Optional[str] = "kb-contact-center"
    selected_frame_ids: List[str]


def frame_to_dict(f: ExtractedFrame, step_num: int) -> dict:
    rel_image = os.path.relpath(f.image_path, BASE_DIR).replace("\\", "/")
    thumb_path = ensure_thumbnail(f.image_path, max_width=480)
    rel_thumb = os.path.relpath(thumb_path, BASE_DIR).replace("\\", "/")

    return {
        "id": f.id,
        "step_number": step_num,
        "timestamp_seconds": f.timestamp_seconds,
        "timestamp_str": f.timestamp_str,
        "image_url": f"/{rel_image}",
        "thumb_url": f"/{rel_thumb}",
        "step_title": f.step_title or f"Passo {step_num}",
        "subtitle_text": f.subtitle_text or "",
        "is_duplicate_candidate": bool(f.is_duplicate_candidate),
        "is_non_system_candidate": bool(getattr(f, "is_non_system_candidate", False)),
        "similarity_score": round(float(f.similarity_score or 0.0), 2),
        "selected": bool(f.selected),
    }


@app.get("/api/health")
def health_check():
    logger.debug("🏥 [HEALTH-CHECK] Health check realizado")
    return {"status": "ok", "version": "v1.2.0"}


@app.get("/api/logs")
def get_logs(lines: int = Query(50), level: str = Query("all")):
    """
    Endpoint para visualizar logs da aplicação.
    Parâmetros:
    - lines: número de linhas a retornar (default: 50)
    - level: filtro por nível (all, info, error, warning, debug)
    """
    logger.debug(f"📋 [LOGS-ENDPOINT] Requisição de logs | lines={lines} | level={level}")

    try:
        if not os.path.exists(LOG_FILE):
            logger.warn(f"⚠️ [LOGS-ENDPOINT] Arquivo de log não existe | path={LOG_FILE}")
            return {"error": "Log file not found", "lines": []}

        with open(LOG_FILE, "r", encoding="utf-8") as f:
            all_lines = f.readlines()

        # Filtrar por nível se solicitado
        filtered_lines = all_lines
        if level != "all":
            filtered_lines = [l for l in all_lines if level.upper() in l.upper()]

        # Retornar últimas N linhas
        result_lines = filtered_lines[-lines:] if len(filtered_lines) > lines else filtered_lines

        return {
            "success": True,
            "total_lines": len(all_lines),
            "filtered_lines": len(filtered_lines),
            "returned_lines": len(result_lines),
            "level": level,
            "log_file": LOG_FILE,
            "lines": result_lines
        }
    except Exception as e:
        logger.error(f"❌ [LOGS-ENDPOINT] Erro ao ler logs | error={str(e)}")
        return {"error": str(e), "lines": []}


# Gerenciamento de tarefas de processamento com feedback de progresso
extraction_jobs: Dict[str, Dict[str, Any]] = {}


def run_extraction_worker(
    job_id: str,
    saved_video: str,
    raw_name: str,
    subtitle_content: Optional[bytes],
    language: str,
    min_interval: float,
    similarity_threshold: float,
):
    try:
        logger.info(f"🔄 [WORKER-START] job_id={job_id} | video={saved_video} | lang={language}")

        extraction_jobs[job_id]["stage"] = "transcription"
        extraction_jobs[job_id]["message"] = "Iniciando transcrição de áudio..."
        extraction_jobs[job_id]["progress"] = 0.08

        video_name = raw_name.replace("_", " ").replace("-", " ").strip()
        logger.debug(f"📝 [WORKER] video_name={video_name} | job_id={job_id}")

        subs: List[SubtitleItem] = []
        if subtitle_content:
            logger.info(f"📄 [WORKER] Usando arquivo de legenda fornecido | job_id={job_id} | size={len(subtitle_content)} bytes")
            extraction_jobs[job_id]["message"] = "Processando arquivo de legenda fornecido..."
            extraction_jobs[job_id]["progress"] = 0.60
            subs = parse_subtitles(subtitle_content)
            logger.info(f"✅ [WORKER] Legendas parseadas | job_id={job_id} | count={len(subs)}")
        else:
            logger.info(f"🎤 [WORKER] Iniciando Whisper transcription | job_id={job_id} | lang={language}")
            def audio_progress(ratio: float, msg: str):
                mapped_prog = min(0.65, 0.10 + (ratio * 0.55))
                extraction_jobs[job_id]["progress"] = round(mapped_prog, 3)
                extraction_jobs[job_id]["message"] = msg
                logger.debug(f"📊 [WORKER-AUDIO-PROGRESS] job_id={job_id} | progress={round(mapped_prog*100, 1)}% | msg={msg}")

            transcriber = AudioTranscriber(model_size="base")
            subs = transcriber.transcribe(saved_video, language=language, progress_callback=audio_progress)
            logger.info(f"✅ [WORKER] Transcrição concluída | job_id={job_id} | subtitles={len(subs)}")

        # Fase 2: Extração de frames
        logger.info(f"🎬 [WORKER] Iniciando extração de frames | job_id={job_id}")
        extraction_jobs[job_id]["stage"] = "extraction"
        extraction_jobs[job_id]["message"] = "Sincronizando timeline e extraindo frames de sistema..."
        extraction_jobs[job_id]["progress"] = 0.68

        processor = VideoProcessor(saved_video)
        logger.debug(f"📹 [WORKER] VideoProcessor criado | job_id={job_id}")

        subs_grouped = group_subtitles(subs or [], max_gap_seconds=1.5, max_duration_seconds=15.0)
        logger.debug(f"📋 [WORKER] Legendas agrupadas | job_id={job_id} | grouped_count={len(subs_grouped)}")

        def frames_progress(ratio: float, msg: str):
            mapped_prog = min(0.98, 0.68 + (ratio * 0.30))
            extraction_jobs[job_id]["progress"] = round(mapped_prog, 3)
            extraction_jobs[job_id]["message"] = msg
            logger.debug(f"📊 [WORKER-FRAMES-PROGRESS] job_id={job_id} | progress={round(mapped_prog*100, 1)}% | msg={msg}")

        extracted = processor.process_subtitles(
            subtitles=subs_grouped,
            output_dir=EXTRACTED_FRAMES,
            min_interval_seconds=min_interval,
            similarity_threshold=similarity_threshold / 100.0,
            progress_callback=frames_progress,
        )
        logger.info(f"✅ [WORKER] Frames extraídos | job_id={job_id} | total={len(extracted)}")

        # Armazena tudo no job (não no state global)
        frames_resp = [frame_to_dict(f, idx + 1) for idx, f in enumerate(extracted)]
        approved_count = sum(1 for f in extracted if f.selected)
        duplicate_count = sum(1 for f in extracted if f.is_duplicate_candidate)
        non_system_count = sum(1 for f in extracted if getattr(f, "is_non_system_candidate", False))

        logger.debug(f"📊 [WORKER] Estatísticas | job_id={job_id} | approved={approved_count} | duplicates={duplicate_count} | non_system={non_system_count}")

        result_payload = {
            "success": True,
            "video_name": video_name,
            "frames": frames_resp,
            "subtitles": [
                {
                    "index": s.index,
                    "start_seconds": s.start_seconds,
                    "end_seconds": s.end_seconds,
                    "start_time_str": s.start_time_str,
                    "end_time_str": s.end_time_str,
                    "text": s.text,
                }
                for s in subs
            ],
            "total_frames": len(extracted),
            "approved_count": approved_count,
            "duplicate_count": duplicate_count,
            "non_system_count": non_system_count,
        }

        # Guardar metadados no job para uso posterior
        extraction_jobs[job_id]["_processor"] = processor
        extraction_jobs[job_id]["_frames"] = extracted
        extraction_jobs[job_id]["_subtitles"] = subs or []
        extraction_jobs[job_id]["_video_name"] = video_name
        logger.debug(f"💾 [WORKER] Dados armazenados no job | job_id={job_id}")

        extraction_jobs[job_id]["status"] = "completed"
        extraction_jobs[job_id]["stage"] = "done"
        extraction_jobs[job_id]["progress"] = 1.0
        extraction_jobs[job_id]["message"] = "Processamento concluído com sucesso!"
        extraction_jobs[job_id]["result"] = result_payload
        logger.info(f"🎉 [WORKER-COMPLETE] job_id={job_id} | status=completed | frames={len(extracted)}")

        # Schedule limpeza do vídeo temporário após 10 minutos
        def cleanup_temp_video(video_path: str, job_id_ref: str, delay_seconds: int = 600):
            try:
                time.sleep(delay_seconds)
                if os.path.exists(video_path):
                    os.remove(video_path)
                    logger.info(f"🗑️ [CLEANUP] Vídeo temporário deletado | job_id={job_id_ref} | path={video_path}")
                else:
                    logger.debug(f"⚠️ [CLEANUP] Vídeo já não existe | job_id={job_id_ref} | path={video_path}")
            except Exception as cleanup_err:
                logger.error(f"❌ [CLEANUP-ERROR] Erro ao limpar vídeo | job_id={job_id_ref} | error={str(cleanup_err)}")

        cleanup_thread = threading.Thread(
            target=cleanup_temp_video,
            args=(saved_video, job_id),
            daemon=True
        )
        cleanup_thread.start()
        logger.debug(f"⏰ [CLEANUP-SCHEDULED] Limpeza agendada em 10min | job_id={job_id} | video={saved_video}")

    except Exception as exc:
        logger.error(f"❌ [WORKER-ERROR] job_id={job_id} | error={str(exc)}")
        logger.error(f"📋 [WORKER-ERROR] Stack trace:\n{traceback.format_exc()}")
        extraction_jobs[job_id]["status"] = "error"
        extraction_jobs[job_id]["error"] = str(exc)
        extraction_jobs[job_id]["message"] = f"Erro no processamento: {str(exc)}"


@app.post("/api/extract")
async def extract_video(
    video: UploadFile = File(...),
    subtitle: Optional[UploadFile] = File(None),
    language: str = Form("pt"),
    min_interval: float = Form(2.5),
    similarity_threshold: float = Form(88.0),
    sync: bool = Query(False),
):
    try:
        logger.info(f"🚀 [EXTRACT-ENDPOINT] Requisição recebida | filename={video.filename} | lang={language} | sync={sync}")
        logger.debug(f"📋 [EXTRACT-ENDPOINT] Parâmetros | min_interval={min_interval} | similarity_threshold={similarity_threshold}")

        # Salva o vídeo enviado
        ext = os.path.splitext(video.filename)[1] or ".mp4"
        saved_video = os.path.join(TEMP_UPLOADS, f"input_video_{uuid.uuid4().hex[:8]}{ext}")
        logger.debug(f"💾 [EXTRACT-ENDPOINT] Salvando arquivo | path={saved_video}")

        with open(saved_video, "wb") as f:
            shutil.copyfileobj(video.file, f, length=16 * 1024 * 1024)

        logger.info(f"✅ [EXTRACT-ENDPOINT] Arquivo salvo com sucesso | size={os.path.getsize(saved_video)} bytes")

        raw_name = os.path.splitext(video.filename)[0]
        sub_bytes = await subtitle.read() if (subtitle and subtitle.filename) else None

        if sub_bytes:
            logger.info(f"📄 [EXTRACT-ENDPOINT] Arquivo de legenda detectado | size={len(sub_bytes)} bytes")
        else:
            logger.debug(f"📄 [EXTRACT-ENDPOINT] Nenhum arquivo de legenda fornecido")

        job_id = f"job_{uuid.uuid4().hex}"
        logger.info(f"🎯 [EXTRACT-ENDPOINT] Job criado | job_id={job_id}")

        extraction_jobs[job_id] = {
            "status": "processing",
            "stage": "upload",
            "progress": 0.05,
            "message": "Vídeo salvo. Iniciando análise...",
            "result": None,
            "error": None,
        }

        if sync:
            logger.info(f"⏱️ [EXTRACT-ENDPOINT] Modo SÍNCRONO ativado | job_id={job_id}")
            run_extraction_worker(
                job_id=job_id,
                saved_video=saved_video,
                raw_name=raw_name,
                subtitle_content=sub_bytes,
                language=language,
                min_interval=min_interval,
                similarity_threshold=similarity_threshold,
            )
            job = extraction_jobs[job_id]
            if job["status"] == "error":
                logger.error(f"❌ [EXTRACT-ENDPOINT] Erro em modo sync | job_id={job_id} | error={job['error']}")
                raise HTTPException(status_code=500, detail=job["error"])
            logger.info(f"✅ [EXTRACT-ENDPOINT] Modo sync concluído com sucesso | job_id={job_id}")
            return job["result"]

        # Inicia thread em segundo plano com monitoramento de progresso
        logger.info(f"🧵 [EXTRACT-ENDPOINT] Iniciando worker thread (modo assíncrono) | job_id={job_id}")
        t = threading.Thread(
            target=run_extraction_worker,
            kwargs={
                "job_id": job_id,
                "saved_video": saved_video,
                "raw_name": raw_name,
                "subtitle_content": sub_bytes,
                "language": language,
                "min_interval": min_interval,
                "similarity_threshold": similarity_threshold,
            },
            daemon=True,
        )
        t.start()
        logger.info(f"📤 [EXTRACT-ENDPOINT] Retornando job_id para polling | job_id={job_id}")

        return {"job_id": job_id, "status": "processing"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [EXTRACT-ENDPOINT] ERRO inesperado | error={str(e)}")
        logger.error(f"📋 [EXTRACT-ENDPOINT] Stack trace:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/extract/progress/{job_id}")
def get_extract_progress(job_id: str):
    logger.debug(f"🔍 [PROGRESS-ENDPOINT] Consultando progresso | job_id={job_id}")
    job = extraction_jobs.get(job_id)
    if not job:
        logger.warn(f"⚠️ [PROGRESS-ENDPOINT] Job não encontrado | job_id={job_id}")
        raise HTTPException(status_code=404, detail="Job não encontrado")

    logger.debug(f"📊 [PROGRESS-ENDPOINT] Job encontrado | job_id={job_id} | status={job.get('status')} | progress={job.get('progress', 0)}")
    return job


@app.post("/api/frames/{frame_id}/adjust-time")
def adjust_frame_time(frame_id: str, req: AdjustTimeRequest, job_id: str = Query(...)):
    logger.info(f"⏰ [ADJUST-TIME-ENDPOINT] Solicitação de ajuste | job_id={job_id} | frame_id={frame_id} | delta={req.delta_seconds}s")

    job = extraction_jobs.get(job_id)
    if not job or job.get("status") != "completed":
        logger.warn(f"⚠️ [ADJUST-TIME-ENDPOINT] Job inválido | job_id={job_id} | status={job.get('status') if job else 'N/A'}")
        raise HTTPException(status_code=404, detail="Job não encontrado ou ainda está processando")

    processor = job.get("_processor")
    frames = job.get("_frames", [])
    logger.debug(f"📊 [ADJUST-TIME-ENDPOINT] Dados obtidos | job_id={job_id} | frames_count={len(frames)} | has_processor={processor is not None}")

    if not processor or not frames:
        logger.error(f"❌ [ADJUST-TIME-ENDPOINT] Processador ou frames vazios | job_id={job_id}")
        raise HTTPException(status_code=400, detail="Nenhum vídeo processado")

    target_frame = next((f for f in frames if f.id == frame_id), None)
    if not target_frame:
        logger.warn(f"⚠️ [ADJUST-TIME-ENDPOINT] Frame não encontrado | job_id={job_id} | frame_id={frame_id}")
        raise HTTPException(status_code=404, detail="Frame não encontrado")

    old_time = target_frame.timestamp_seconds
    new_time = max(0.0, target_frame.timestamp_seconds + req.delta_seconds)
    logger.debug(f"⏱️ [ADJUST-TIME-ENDPOINT] Ajustando tempo | job_id={job_id} | frame_id={frame_id} | old_time={old_time}s | new_time={new_time}s")

    success = processor.refresh_frame_image(target_frame, new_time, EXTRACTED_FRAMES)
    if not success:
        logger.error(f"❌ [ADJUST-TIME-ENDPOINT] Falha ao extrair novo frame | job_id={job_id} | frame_id={frame_id} | time={new_time}s")
        raise HTTPException(status_code=500, detail="Falha ao extrair novo frame no timestamp")

    step_idx = frames.index(target_frame) + 1
    logger.info(f"✅ [ADJUST-TIME-ENDPOINT] Frame ajustado com sucesso | job_id={job_id} | frame_id={frame_id} | new_time={new_time}s")
    return {"success": True, "frame": frame_to_dict(target_frame, step_idx)}


@app.get("/api/export/docx")
def export_docx(title: str = Query("Guia de Treinamento"), frame_ids: str = Query(""), job_id: str = Query(...)):
    logger.info(f"📄 [EXPORT-DOCX-ENDPOINT] Solicitação de export | job_id={job_id} | title={title}")

    job = extraction_jobs.get(job_id)
    if not job or job.get("status") != "completed":
        logger.warn(f"⚠️ [EXPORT-DOCX-ENDPOINT] Job inválido | job_id={job_id} | status={job.get('status') if job else 'N/A'}")
        raise HTTPException(status_code=404, detail="Job não encontrado ou ainda está processando")

    frames = job.get("_frames", [])
    subtitles = job.get("_subtitles", [])
    logger.debug(f"📊 [EXPORT-DOCX-ENDPOINT] Dados | job_id={job_id} | total_frames={len(frames)} | subtitles={len(subtitles)}")

    ids = [i.strip() for i in frame_ids.split(",") if i.strip()]
    approved = [f for f in frames if f.id in ids] if ids else [f for f in frames if f.selected]
    logger.info(f"📝 [EXPORT-DOCX-ENDPOINT] Frames selecionados | job_id={job_id} | count={len(approved)}")

    clean_base = "".join(c for c in title if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_") or "guia"
    docx_path = os.path.join(OUTPUTS_DIR, f"{clean_base}.docx")
    logger.debug(f"💾 [EXPORT-DOCX-ENDPOINT] Construindo DOCX | job_id={job_id} | path={docx_path}")

    builder = DocumentBuilder(title=title)
    builder.build_docx(approved, docx_path, all_subtitles=subtitles)

    file_size = os.path.getsize(docx_path) if os.path.exists(docx_path) else 0
    logger.info(f"✅ [EXPORT-DOCX-ENDPOINT] DOCX criado com sucesso | job_id={job_id} | size={file_size} bytes | filename={clean_base}.docx")

    return FileResponse(docx_path, filename=f"{clean_base}.docx", media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@app.get("/api/export/pdf")
def export_pdf(title: str = Query("Guia de Treinamento"), frame_ids: str = Query(""), job_id: str = Query(...)):
    logger.info(f"📑 [EXPORT-PDF-ENDPOINT] Solicitação de export | job_id={job_id} | title={title}")

    job = extraction_jobs.get(job_id)
    if not job or job.get("status") != "completed":
        logger.warn(f"⚠️ [EXPORT-PDF-ENDPOINT] Job inválido | job_id={job_id} | status={job.get('status') if job else 'N/A'}")
        raise HTTPException(status_code=404, detail="Job não encontrado ou ainda está processando")

    frames = job.get("_frames", [])
    subtitles = job.get("_subtitles", [])
    logger.debug(f"📊 [EXPORT-PDF-ENDPOINT] Dados | job_id={job_id} | total_frames={len(frames)} | subtitles={len(subtitles)}")

    ids = [i.strip() for i in frame_ids.split(",") if i.strip()]
    approved = [f for f in frames if f.id in ids] if ids else [f for f in frames if f.selected]
    logger.info(f"📝 [EXPORT-PDF-ENDPOINT] Frames selecionados | job_id={job_id} | count={len(approved)}")

    clean_base = "".join(c for c in title if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_") or "guia"
    pdf_path = os.path.join(OUTPUTS_DIR, f"{clean_base}.pdf")
    logger.debug(f"💾 [EXPORT-PDF-ENDPOINT] Construindo PDF | job_id={job_id} | path={pdf_path}")

    builder = DocumentBuilder(title=title)
    builder.build_pdf(approved, pdf_path, all_subtitles=subtitles)

    file_size = os.path.getsize(pdf_path) if os.path.exists(pdf_path) else 0
    logger.info(f"✅ [EXPORT-PDF-ENDPOINT] PDF criado com sucesso | job_id={job_id} | size={file_size} bytes | filename={clean_base}.pdf")

    return FileResponse(pdf_path, filename=f"{clean_base}.pdf", media_type="application/pdf")


@app.get("/api/export/zip")
def export_zip(title: str = Query("Guia de Treinamento"), frame_ids: str = Query(""), job_id: str = Query(...)):
    logger.info(f"📦 [EXPORT-ZIP-ENDPOINT] Solicitação de export | job_id={job_id} | title={title}")

    job = extraction_jobs.get(job_id)
    if not job or job.get("status") != "completed":
        logger.warn(f"⚠️ [EXPORT-ZIP-ENDPOINT] Job inválido | job_id={job_id} | status={job.get('status') if job else 'N/A'}")
        raise HTTPException(status_code=404, detail="Job não encontrado ou ainda está processando")

    frames = job.get("_frames", [])
    subtitles = job.get("_subtitles", [])
    logger.debug(f"📊 [EXPORT-ZIP-ENDPOINT] Dados | job_id={job_id} | total_frames={len(frames)} | subtitles={len(subtitles)}")

    ids = [i.strip() for i in frame_ids.split(",") if i.strip()]
    approved = [f for f in frames if f.id in ids] if ids else [f for f in frames if f.selected]
    logger.info(f"📝 [EXPORT-ZIP-ENDPOINT] Frames selecionados | job_id={job_id} | count={len(approved)}")

    clean_base = "".join(c for c in title if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_") or "projeto"
    zip_path = os.path.join(OUTPUTS_DIR, f"{clean_base}.zip")
    logger.debug(f"💾 [EXPORT-ZIP-ENDPOINT] Construindo ZIP | job_id={job_id} | path={zip_path}")

    pdf_temp = os.path.join(OUTPUTS_DIR, f"{clean_base}_doc.pdf")
    logger.debug(f"📑 [EXPORT-ZIP-ENDPOINT] Gerando PDF temporário | job_id={job_id} | path={pdf_temp}")

    builder = DocumentBuilder(title=title)
    builder.build_pdf(approved, pdf_temp, all_subtitles=subtitles)

    logger.debug(f"📝 [EXPORT-ZIP-ENDPOINT] Gerando Markdown | job_id={job_id}")
    publisher = GCSPublisher()
    md_content = publisher.generate_multimodal_markdown(
        project_slug="treinamento",
        title=title,
        approved_frames=approved,
        all_subtitles=subtitles,
    )

    logger.debug(f"🗜️ [EXPORT-ZIP-ENDPOINT] Compactando arquivos | job_id={job_id} | frames={len(approved)}")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if os.path.exists(pdf_temp):
            logger.debug(f"📑 [EXPORT-ZIP-ENDPOINT] Adicionando PDF ao ZIP | job_id={job_id}")
            zf.write(pdf_temp, arcname=f"{clean_base}.pdf")

        logger.debug(f"📝 [EXPORT-ZIP-ENDPOINT] Adicionando Markdown ao ZIP | job_id={job_id}")
        zf.writestr("knowledge_base.md", md_content)

        logger.debug(f"🖼️ [EXPORT-ZIP-ENDPOINT] Adicionando {len(approved)} frames ao ZIP | job_id={job_id}")
        for idx, frame in enumerate(approved, 1):
            if os.path.exists(frame.image_path):
                img_name = f"passo_{idx}_{os.path.basename(frame.image_path)}"
                zf.write(frame.image_path, arcname=f"images/{img_name}")
            else:
                logger.warn(f"⚠️ [EXPORT-ZIP-ENDPOINT] Imagem não encontrada | job_id={job_id} | frame_idx={idx} | path={frame.image_path}")

    file_size = os.path.getsize(zip_path) if os.path.exists(zip_path) else 0
    logger.info(f"✅ [EXPORT-ZIP-ENDPOINT] ZIP criado com sucesso | job_id={job_id} | size={file_size} bytes | filename={clean_base}.zip")

    return FileResponse(zip_path, filename=f"{clean_base}.zip", media_type="application/zip")


@app.post("/api/publish/gcs")
def publish_gcs(req: PublishGCSRequest, job_id: str = Query(...)):
    logger.info(f"☁️ [PUBLISH-GCS-ENDPOINT] Solicitação de publicação | job_id={job_id} | title={req.title} | product={req.product_slug}")

    job = extraction_jobs.get(job_id)
    if not job or job.get("status") != "completed":
        logger.warn(f"⚠️ [PUBLISH-GCS-ENDPOINT] Job inválido | job_id={job_id} | status={job.get('status') if job else 'N/A'}")
        raise HTTPException(status_code=404, detail="Job não encontrado ou ainda está processando")

    frames = job.get("_frames", [])
    subtitles = job.get("_subtitles", [])
    logger.debug(f"📊 [PUBLISH-GCS-ENDPOINT] Dados | job_id={job_id} | total_frames={len(frames)} | subtitles={len(subtitles)}")

    approved = [f for f in frames if f.id in req.selected_frame_ids]
    if not approved:
        logger.warn(f"⚠️ [PUBLISH-GCS-ENDPOINT] Nenhum frame selecionado | job_id={job_id}")
        raise HTTPException(status_code=400, detail="Nenhum print selecionado para publicação")

    logger.info(f"📝 [PUBLISH-GCS-ENDPOINT] Frames selecionados | job_id={job_id} | count={len(approved)}")

    training_slug = slugify_training_name(req.title)
    publisher = GCSPublisher(default_bucket=req.bucket_name)
    logger.debug(f"🔧 [PUBLISH-GCS-ENDPOINT] Publisher criado | job_id={job_id} | bucket={req.bucket_name}")

    clean_base = "".join(c for c in req.title if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_") or "guia"
    docx_path = os.path.join(OUTPUTS_DIR, f"{clean_base}.docx")
    pdf_path = os.path.join(OUTPUTS_DIR, f"{clean_base}.pdf")
    logger.debug(f"💾 [PUBLISH-GCS-ENDPOINT] Gerando documentos | job_id={job_id} | docx={docx_path} | pdf={pdf_path}")

    builder = DocumentBuilder(title=req.title, subtitle=req.description or "")
    builder.build_docx(approved, docx_path, all_subtitles=subtitles)
    logger.debug(f"📄 [PUBLISH-GCS-ENDPOINT] DOCX criado | job_id={job_id}")

    builder.build_pdf(approved, pdf_path, all_subtitles=subtitles)
    logger.debug(f"📑 [PUBLISH-GCS-ENDPOINT] PDF criado | job_id={job_id}")

    logger.debug(f"📦 [PUBLISH-GCS-ENDPOINT] Preparando pacote local | job_id={job_id} | project={req.product_slug}")
    package_files = publisher.prepare_local_package(
        project_slug=req.product_slug,
        output_dir=OUTPUTS_DIR,
        title=req.title,
        approved_frames=approved,
        all_subtitles=subtitles,
        docx_path=docx_path,
        pdf_path=pdf_path,
        bucket_name=req.bucket_name,
        training_slug=training_slug,
    )
    logger.info(f"✅ [PUBLISH-GCS-ENDPOINT] Pacote local pronto | job_id={job_id} | files={len(package_files)}")

    logger.info(f"⬆️ [PUBLISH-GCS-ENDPOINT] Enviando para GCS | job_id={job_id} | bucket={req.bucket_name} | slug={training_slug}")
    result = publisher.publish_to_gcs(
        project_slug=req.product_slug,
        local_files_map=package_files,
        bucket_name=req.bucket_name,
        training_slug=training_slug,
    )

    if result.success:
        logger.info(f"🎉 [PUBLISH-GCS-ENDPOINT] Publicação bem-sucedida | job_id={job_id} | prefix={result.gcs_prefix}")
        return {
            "success": True,
            "gcs_prefix": result.gcs_prefix,
            "message": result.message,
        }
    else:
        logger.error(f"❌ [PUBLISH-GCS-ENDPOINT] Falha na publicação | job_id={job_id} | message={result.message}")
        return {
            "success": False,
            "gcs_prefix": result.gcs_prefix,
            "message": result.message,
        }


# Se a pasta compilada do frontend existir, serve o SPA
if os.path.exists(FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")

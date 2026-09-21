"""
FastAPI Server para VideoToDocumento.
Serve a API REST para extração, auditoria, downloads e publicação GCS,
além de servir os arquivos estáticos compilados do React na mesma porta.
"""

import os
import shutil
import tempfile
import threading
import uuid
import zipfile
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from core.srt_parser import parse_subtitles, group_subtitles, export_to_srt, SubtitleItem
from core.video_processor import VideoProcessor, ExtractedFrame, ensure_thumbnail
from core.doc_builder import DocumentBuilder
from core.transcriber import AudioTranscriber
from core.gcs_publisher import GCSPublisher, SUPPORTED_PROJECTS, slugify_training_name

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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

# Estado em memória da sessão ativa
class SessionState:
    video_path: Optional[str] = None
    video_name: str = ""
    frames: List[ExtractedFrame] = []
    subtitles: List[SubtitleItem] = []
    processor: Optional[VideoProcessor] = None

state = SessionState()

# Monta armazenamento estático para que o frontend carregue os frames e thumbnails
app.mount("/storage", StaticFiles(directory=STORAGE_DIR), name="storage")


class AdjustTimeRequest(BaseModel):
    delta_seconds: float


class PublishGCSRequest(BaseModel):
    title: str
    description: Optional[str] = ""
    product_slug: str
    bucket_name: Optional[str] = "kb-contact-center-vertex"
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
    return {"status": "ok", "version": "v1.2.0"}


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
        if extraction_jobs.get(job_id, {}).get("cancelled"):
            raise InterruptedError("Processamento suspenso pelo usuário")

        extraction_jobs[job_id]["stage"] = "transcription"
        extraction_jobs[job_id]["message"] = "Iniciando transcrição de áudio..."
        extraction_jobs[job_id]["progress"] = 0.08

        state.video_path = saved_video
        state.video_name = raw_name.replace("_", " ").replace("-", " ").strip()

        subs: List[SubtitleItem] = []
        if subtitle_content:
            extraction_jobs[job_id]["message"] = "Processando arquivo de legenda fornecido..."
            extraction_jobs[job_id]["progress"] = 0.60
            subs = parse_subtitles(subtitle_content)
        else:
            def audio_progress(ratio: float, msg: str):
                if extraction_jobs.get(job_id, {}).get("cancelled"):
                    raise InterruptedError("Processamento suspenso pelo usuário")
                # ratio vai de 0.0 a 1.0; mapeia para 0.10 a 0.65 do progresso total
                mapped_prog = min(0.65, 0.10 + (ratio * 0.55))
                extraction_jobs[job_id]["progress"] = round(mapped_prog, 3)
                extraction_jobs[job_id]["message"] = msg

            transcriber = AudioTranscriber(model_size="base")
            subs = transcriber.transcribe(saved_video, language=language, progress_callback=audio_progress)

        if extraction_jobs.get(job_id, {}).get("cancelled"):
            raise InterruptedError("Processamento suspenso pelo usuário")

        state.subtitles = subs or []

        # Fase 2: Extração de frames e análise de similaridade
        extraction_jobs[job_id]["stage"] = "extraction"
        extraction_jobs[job_id]["message"] = "Sincronizando timeline e extraindo frames de sistema..."
        extraction_jobs[job_id]["progress"] = 0.68

        processor = VideoProcessor(saved_video)
        state.processor = processor

        subs_grouped = group_subtitles(state.subtitles, max_gap_seconds=1.5, max_duration_seconds=15.0) if state.subtitles else []

        def frames_progress(ratio: float, msg: str):
            if extraction_jobs.get(job_id, {}).get("cancelled"):
                raise InterruptedError("Processamento suspenso pelo usuário")
            # ratio vai de 0.0 a 1.0; mapeia para 0.68 a 0.98 do progresso total
            mapped_prog = min(0.98, 0.68 + (ratio * 0.30))
            extraction_jobs[job_id]["progress"] = round(mapped_prog, 3)
            extraction_jobs[job_id]["message"] = msg

        extracted = processor.process_subtitles(
            subtitles=subs_grouped,
            output_dir=EXTRACTED_FRAMES,
            min_interval_seconds=min_interval,
            similarity_threshold=similarity_threshold / 100.0,
            progress_callback=frames_progress,
        )

        if extraction_jobs.get(job_id, {}).get("cancelled"):
            raise InterruptedError("Processamento suspenso pelo usuário")

        state.frames = extracted

        # Monta resposta serializada
        frames_resp = [frame_to_dict(f, idx + 1) for idx, f in enumerate(extracted)]
        approved_count = sum(1 for f in extracted if f.selected)
        duplicate_count = sum(1 for f in extracted if f.is_duplicate_candidate)
        non_system_count = sum(1 for f in extracted if getattr(f, "is_non_system_candidate", False))

        result_payload = {
            "success": True,
            "video_name": state.video_name,
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
                for s in state.subtitles
            ],
            "total_frames": len(extracted),
            "approved_count": approved_count,
            "duplicate_count": duplicate_count,
            "non_system_count": non_system_count,
        }

        extraction_jobs[job_id]["status"] = "completed"
        extraction_jobs[job_id]["stage"] = "done"
        extraction_jobs[job_id]["progress"] = 1.0
        extraction_jobs[job_id]["message"] = "Processamento concluído com sucesso!"
        extraction_jobs[job_id]["result"] = result_payload

    except InterruptedError:
        extraction_jobs[job_id]["status"] = "cancelled"
        extraction_jobs[job_id]["message"] = "Processamento suspenso pelo usuário."
        extraction_jobs[job_id]["progress"] = 0.0
    except Exception as exc:
        import traceback
        tb_str = traceback.format_exc()
        extraction_jobs[job_id]["status"] = "error"
        extraction_jobs[job_id]["error"] = str(exc) or type(exc).__name__
        extraction_jobs[job_id]["details"] = tb_str
        extraction_jobs[job_id]["message"] = f"Falha no processamento: {str(exc) or type(exc).__name__}"


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
        # Salva o vídeo enviado
        ext = os.path.splitext(video.filename)[1] or ".mp4"
        saved_video = os.path.join(TEMP_UPLOADS, f"input_video_{uuid.uuid4().hex[:8]}{ext}")
        with open(saved_video, "wb") as f:
            shutil.copyfileobj(video.file, f, length=16 * 1024 * 1024)

        raw_name = os.path.splitext(video.filename)[0]
        sub_bytes = await subtitle.read() if (subtitle and subtitle.filename) else None

        job_id = f"job_{uuid.uuid4().hex}"
        extraction_jobs[job_id] = {
            "status": "processing",
            "stage": "upload",
            "progress": 0.05,
            "message": "Vídeo salvo. Iniciando análise...",
            "result": None,
            "error": None,
            "details": None,
            "cancelled": False,
        }

        if sync:
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
                raise HTTPException(status_code=500, detail={"message": job["error"], "details": job.get("details")})
            return job["result"]

        # Inicia thread em segundo plano com monitoramento de progresso
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

        return {"job_id": job_id, "status": "processing"}

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        tb_str = traceback.format_exc()
        raise HTTPException(
            status_code=500,
            detail={
                "message": f"Falha ao iniciar processamento: {str(e)}",
                "details": tb_str,
                "error_type": type(e).__name__
            }
        )


@app.post("/api/extract/cancel/{job_id}")
def cancel_extract_job(job_id: str):
    job = extraction_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    job["cancelled"] = True
    job["status"] = "cancelled"
    job["message"] = "Processamento suspenso pelo usuário."
    return {"success": True, "message": "Job cancelado com sucesso"}


@app.get("/api/extract/progress/{job_id}")
def get_extract_progress(job_id: str):
    job = extraction_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return job


@app.post("/api/frames/{frame_id}/adjust-time")
def adjust_frame_time(frame_id: str, req: AdjustTimeRequest):
    if not state.processor or not state.frames:
        raise HTTPException(status_code=400, detail="Nenhum vídeo processado")

    target_frame = next((f for f in state.frames if f.id == frame_id), None)
    if not target_frame:
        raise HTTPException(status_code=404, detail="Frame não encontrado")

    new_time = max(0.0, target_frame.timestamp_seconds + req.delta_seconds)
    success = state.processor.refresh_frame_image(target_frame, new_time, EXTRACTED_FRAMES)
    if not success:
        raise HTTPException(status_code=500, detail="Falha ao extrair novo frame no timestamp")

    step_idx = state.frames.index(target_frame) + 1
    return {"success": True, "frame": frame_to_dict(target_frame, step_idx)}


@app.get("/api/export/docx")
def export_docx(title: str = Query("Guia de Treinamento"), frame_ids: str = Query("")):
    ids = [i.strip() for i in frame_ids.split(",") if i.strip()]
    approved = [f for f in state.frames if f.id in ids] if ids else [f for f in state.frames if f.selected]

    clean_base = "".join(c for c in title if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_") or "guia"
    docx_path = os.path.join(OUTPUTS_DIR, f"{clean_base}.docx")

    builder = DocumentBuilder(title=title)
    builder.build_docx(approved, docx_path, all_subtitles=state.subtitles)

    return FileResponse(docx_path, filename=f"{clean_base}.docx", media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@app.get("/api/export/pdf")
def export_pdf(title: str = Query("Guia de Treinamento"), frame_ids: str = Query("")):
    ids = [i.strip() for i in frame_ids.split(",") if i.strip()]
    approved = [f for f in state.frames if f.id in ids] if ids else [f for f in state.frames if f.selected]

    clean_base = "".join(c for c in title if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_") or "guia"
    pdf_path = os.path.join(OUTPUTS_DIR, f"{clean_base}.pdf")

    builder = DocumentBuilder(title=title)
    builder.build_pdf(approved, pdf_path, all_subtitles=state.subtitles)

    return FileResponse(pdf_path, filename=f"{clean_base}.pdf", media_type="application/pdf")


@app.get("/api/export/zip")
def export_zip(title: str = Query("Guia de Treinamento"), frame_ids: str = Query("")):
    ids = [i.strip() for i in frame_ids.split(",") if i.strip()]
    approved = [f for f in state.frames if f.id in ids] if ids else [f for f in state.frames if f.selected]

    clean_base = "".join(c for c in title if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_") or "projeto"
    zip_path = os.path.join(OUTPUTS_DIR, f"{clean_base}.zip")

    # Gera PDF para o pacote
    pdf_temp = os.path.join(OUTPUTS_DIR, f"{clean_base}_doc.pdf")
    builder = DocumentBuilder(title=title)
    builder.build_pdf(approved, pdf_temp, all_subtitles=state.subtitles)

    # Gera Markdown Multimodal
    publisher = GCSPublisher()
    md_content = publisher.generate_multimodal_markdown(
        project_slug="treinamento",
        title=title,
        approved_frames=approved,
        all_subtitles=state.subtitles,
    )

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if os.path.exists(pdf_temp):
            zf.write(pdf_temp, arcname=f"{clean_base}.pdf")
        zf.writestr("knowledge_base.md", md_content)

        # Adiciona imagens aprovadas na pasta images/
        for idx, frame in enumerate(approved, 1):
            if os.path.exists(frame.image_path):
                img_name = f"passo_{idx}_{os.path.basename(frame.image_path)}"
                zf.write(frame.image_path, arcname=f"images/{img_name}")

    return FileResponse(zip_path, filename=f"{clean_base}.zip", media_type="application/zip")


@app.post("/api/publish/gcs")
def publish_gcs(req: PublishGCSRequest):
    approved = [f for f in state.frames if f.id in req.selected_frame_ids]
    if not approved:
        raise HTTPException(status_code=400, detail="Nenhum print selecionado para publicação")

    training_slug = slugify_training_name(req.title)
    publisher = GCSPublisher(default_bucket=req.bucket_name)

    # Garante geração do DOCX e PDF para upload
    clean_base = "".join(c for c in req.title if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_") or "guia"
    docx_path = os.path.join(OUTPUTS_DIR, f"{clean_base}.docx")
    pdf_path = os.path.join(OUTPUTS_DIR, f"{clean_base}.pdf")
    builder = DocumentBuilder(title=req.title, subtitle=req.description or "")
    builder.build_docx(approved, docx_path, all_subtitles=state.subtitles)
    builder.build_pdf(approved, pdf_path, all_subtitles=state.subtitles)

    # Prepara pacote local estruturado
    package_files = publisher.prepare_local_package(
        project_slug=req.product_slug,
        output_dir=OUTPUTS_DIR,
        title=req.title,
        approved_frames=approved,
        all_subtitles=state.subtitles,
        docx_path=docx_path,
        pdf_path=pdf_path,
        bucket_name=req.bucket_name,
        training_slug=training_slug,
    )

    # Envia para o GCS
    result = publisher.publish_to_gcs(
        project_slug=req.product_slug,
        local_files_map=package_files,
        bucket_name=req.bucket_name,
        training_slug=training_slug,
    )

    if result.success:
        return {
            "success": True,
            "gcs_prefix": result.gcs_prefix,
            "message": result.message,
        }
    else:
        # Retorna falha informativa mantendo status do pacote local
        return {
            "success": False,
            "gcs_prefix": result.gcs_prefix,
            "message": result.message,
        }


# Se a pasta compilada do frontend existir, serve o SPA
if os.path.exists(FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")

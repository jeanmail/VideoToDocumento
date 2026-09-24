"""
FastAPI Server para VideoToDocumento.
Serve a API REST para extração, auditoria, downloads e publicação GCS,
além de servir os arquivos estáticos compilados do React na mesma porta.
"""

import json
import pickle
import os
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
import logging
import traceback
import urllib.request
import urllib.parse
import http.cookiejar
import re
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# Definir BASE_DIR ANTES de qualquer coisa
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

VERSION_FILE = os.path.join(BASE_DIR, "VERSION")
try:
    with open(VERSION_FILE, "r", encoding="utf-8") as _vf:
        APP_VERSION = _vf.read().strip() or "v1.3.0"
except Exception:
    APP_VERSION = "v1.3.0"

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
CHUNK_UPLOADS = os.path.join(STORAGE_DIR, "chunk_uploads")
EXTRACTED_FRAMES = os.path.join(STORAGE_DIR, "extracted_frames")
OUTPUTS_DIR = os.path.join(STORAGE_DIR, "outputs")
JOBS_DIR = os.path.join(STORAGE_DIR, "jobs")
FRONTEND_DIST = os.path.join(BASE_DIR, "frontend", "dist")

for d in [TEMP_UPLOADS, CHUNK_UPLOADS, EXTRACTED_FRAMES, OUTPUTS_DIR, JOBS_DIR]:
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


def extract_google_drive_file_id(url: str) -> Optional[str]:
    """Extrai o File ID de vários formatos de URL do Google Drive."""
    m = re.search(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)
    return None


def download_video_from_url(url: str, dest_path: str, progress_callback: Optional[Any] = None) -> str:
    """
    Baixa o vídeo a partir de uma URL (suporta links do Google Drive com bypass
    do aviso de vírus para arquivos grandes e URLs HTTP/HTTPS diretas).
    Retorna o nome do arquivo detectado.
    """
    drive_id = extract_google_drive_file_id(url)
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    target_url = url
    if drive_id:
        target_url = f"https://drive.google.com/uc?export=download&id={drive_id}"

    req = urllib.request.Request(target_url, headers={"User-Agent": user_agent})
    resp = opener.open(req, timeout=30)

    # Se for Google Drive e retornou HTML (página de aviso de vírus), resolve confirmação
    content_type = resp.headers.get("Content-Type", "")
    detected_name = ""
    
    if drive_id and "text/html" in content_type.lower():
        html_bytes = resp.read()
        html_text = html_bytes.decode("utf-8", errors="ignore")
        
        # Tenta extrair o nome original do arquivo presente no HTML do Drive
        name_match = re.search(r'class="uc-name-size"[^>]*><a[^>]*>([^<]+)</a>', html_text)
        if name_match:
            detected_name = name_match.group(1).strip()
            
        form_match = re.search(r'<form[^>]+id=["\']download-form["\'][^>]+action=["\']([^"\']+)["\']', html_text)
        if form_match:
            action_url = form_match.group(1)
            inputs = re.findall(r'<input[^>]+name=["\']([^"\']+)["\'][^>]+value=["\']([^"\']*)["\']', html_text)
            params = {k: v for k, v in inputs}
            final_url = f"{action_url}?{urllib.parse.urlencode(params)}"
            req2 = urllib.request.Request(final_url, headers={"User-Agent": user_agent})
            resp = opener.open(req2, timeout=60)
        else:
            # Fallback para token de confirmação
            token_match = re.search(r"confirm=([0-9A-Za-z_]+)", html_text)
            confirm_token = token_match.group(1) if token_match else "t"
            final_url = f"https://drive.google.com/uc?export=download&confirm={confirm_token}&id={drive_id}"
            req2 = urllib.request.Request(final_url, headers={"User-Agent": user_agent})
            resp = opener.open(req2, timeout=60)

    # Detecta nome via Content-Disposition se não foi detectado ainda
    disp = resp.headers.get("Content-Disposition", "")
    if not detected_name and disp:
        cd_match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';\r\n]+)', disp)
        if cd_match:
            detected_name = urllib.parse.unquote(cd_match.group(1).strip())

    if not detected_name:
        url_path = urllib.parse.urlparse(url).path
        base = os.path.basename(url_path)
        detected_name = base if base and "." in base else "video_download.mp4"

    # Download do arquivo em blocos
    total_size = int(resp.headers.get("Content-Length", 0))
    downloaded = 0
    chunk_size = 1024 * 1024  # 1MB por bloco

    with open(dest_path, "wb") as f_out:
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            f_out.write(chunk)
            downloaded += len(chunk)
            if total_size > 0 and progress_callback:
                progress_callback(downloaded / total_size, downloaded, total_size)

    return detected_name


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
    logger.debug(f"🏥 [HEALTH-CHECK] Health check realizado | version={APP_VERSION}")
    return {"status": "ok", "version": APP_VERSION}


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


# Gerenciamento de tarefas de processamento com feedback de progresso e persistência em disco
extraction_jobs: Dict[str, Dict[str, Any]] = {}


def save_job_state(job_id: str):
    """
    Persiste o estado do job em disco (JSON e metadados binários) para garantir
    tolerância a múltiplos workers/instâncias no Cloud Run, Render ou Docker.
    Utiliza escrita atômica (arquivo temporário + os.replace) para evitar que
    o endpoint de consulta leia o arquivo truncado (0 bytes) ou corrompido.
    """
    job = extraction_jobs.get(job_id)
    if not job:
        return
    try:
        json_path = os.path.join(JOBS_DIR, f"{job_id}.json")
        json_tmp_path = os.path.join(JOBS_DIR, f"{job_id}.json.tmp")
        meta_path = os.path.join(JOBS_DIR, f"{job_id}.meta")
        meta_tmp_path = os.path.join(JOBS_DIR, f"{job_id}.meta.tmp")

        # Serializa campos seguros em JSON de forma atômica
        safe_copy = {
            "status": job.get("status"),
            "stage": job.get("stage"),
            "progress": job.get("progress"),
            "message": job.get("message"),
            "result": job.get("result"),
            "error": job.get("error"),
        }
        with open(json_tmp_path, "w", encoding="utf-8") as f:
            json.dump(safe_copy, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(json_tmp_path, json_path)

        # Se houver objetos internos complexos (_frames, _subtitles, etc.), persiste em .meta atomicamente
        has_meta = any(k.startswith("_") for k in job.keys())
        if has_meta:
            meta_dict = {k: v for k, v in job.items() if k.startswith("_")}
            with open(meta_tmp_path, "wb") as f_meta:
                pickle.dump(meta_dict, f_meta)
                f_meta.flush()
                os.fsync(f_meta.fileno())
            os.replace(meta_tmp_path, meta_path)
    except Exception as e:
        logger.error(f"⚠️ [JOB-SAVE-ERROR] Não foi possível salvar estado do job={job_id}: {str(e)}")


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Retorna o job da memória ou do disco caso a requisição caia em outra instância / worker.
    Tolerante a leituras concorrentes com pequeno retry.
    """
    if job_id in extraction_jobs:
        return extraction_jobs[job_id]

    json_path = os.path.join(JOBS_DIR, f"{job_id}.json")
    meta_path = os.path.join(JOBS_DIR, f"{job_id}.meta")

    if os.path.exists(json_path):
        # Tenta ler com retry breve caso o arquivo esteja sendo finalizado por replace
        for attempt in range(2):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    restored = json.load(f)
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, "rb") as f_meta:
                            meta = pickle.load(f_meta)
                            restored.update(meta)
                    except Exception as meta_err:
                        logger.warn(f"⚠️ [JOB-META-WARN] Falha ao ler .meta do job={job_id}: {str(meta_err)}")
                extraction_jobs[job_id] = restored
                logger.info(f"🔄 [JOB-RESTORED] Job={job_id} restaurado do disco para a memória")
                return restored
            except Exception as e:
                if attempt == 0:
                    time.sleep(0.08)
                    continue
                logger.error(f"❌ [JOB-RESTORE-ERROR] Falha ao carregar {json_path}: {str(e)}")

    return None


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
        save_job_state(job_id)

        video_name = raw_name.replace("_", " ").replace("-", " ").strip()
        logger.debug(f"📝 [WORKER] video_name={video_name} | job_id={job_id}")

        subs: List[SubtitleItem] = []
        if subtitle_content:
            logger.info(f"📄 [WORKER] Usando arquivo de legenda fornecido | job_id={job_id} | size={len(subtitle_content)} bytes")
            extraction_jobs[job_id]["message"] = "Processando arquivo de legenda fornecido..."
            extraction_jobs[job_id]["progress"] = 0.60
            save_job_state(job_id)
            subs = parse_subtitles(subtitle_content)
            logger.info(f"✅ [WORKER] Legendas parseadas | job_id={job_id} | count={len(subs)}")
        else:
            logger.info(f"🎤 [WORKER] Iniciando Whisper transcription | job_id={job_id} | lang={language}")
            def audio_progress(ratio: float, msg: str):
                mapped_prog = min(0.65, 0.10 + (ratio * 0.55))
                extraction_jobs[job_id]["progress"] = round(mapped_prog, 3)
                extraction_jobs[job_id]["message"] = msg
                save_job_state(job_id)
                logger.debug(f"📊 [WORKER-AUDIO-PROGRESS] job_id={job_id} | progress={round(mapped_prog*100, 1)}% | msg={msg}")

            # Diagnóstico de memória em runtime
            model_to_use = "base"
            try:
                import psutil
                mem = psutil.virtual_memory()
                logger.info(f"🧠 [WORKER-RAM] RAM Total: {round(mem.total / (1024**3), 2)}GB | Disponível: {round(mem.available / (1024**3), 2)}GB ({mem.percent}% em uso)")
                if mem.available < 700 * 1024 * 1024:
                    logger.warn("⚠️ [WORKER-RAM] Pouca memória disponível (<700MB). Usando modelo 'tiny' para prevenir OOM.")
                    model_to_use = "tiny"
            except ImportError:
                pass

            transcriber = AudioTranscriber(model_size=model_to_use, compute_type="int8")
            subs = transcriber.transcribe(saved_video, language=language, progress_callback=audio_progress)
            logger.info(f"✅ [WORKER] Transcrição concluída | job_id={job_id} | model={model_to_use} | subtitles={len(subs)}")

        # Fase 2: Extração de frames
        logger.info(f"🎬 [WORKER] Iniciando extração de frames | job_id={job_id}")
        extraction_jobs[job_id]["stage"] = "extraction"
        extraction_jobs[job_id]["message"] = "Sincronizando timeline e extraindo frames de sistema..."
        extraction_jobs[job_id]["progress"] = 0.68
        save_job_state(job_id)

        processor = VideoProcessor(saved_video)
        logger.debug(f"📹 [WORKER] VideoProcessor criado | job_id={job_id}")

        subs_grouped = group_subtitles(subs or [], max_gap_seconds=1.5, max_duration_seconds=15.0)
        logger.debug(f"📋 [WORKER] Legendas agrupadas | job_id={job_id} | grouped_count={len(subs_grouped)}")

        def frames_progress(ratio: float, msg: str):
            mapped_prog = min(0.98, 0.68 + (ratio * 0.30))
            extraction_jobs[job_id]["progress"] = round(mapped_prog, 3)
            extraction_jobs[job_id]["message"] = msg
            save_job_state(job_id)
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
        save_job_state(job_id)
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
        save_job_state(job_id)


@app.post("/api/upload/chunk")
async def upload_chunk(
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    chunk_file: UploadFile = File(...),
):
    """
    Recebe um pedaço (chunk) do arquivo de vídeo fatiado pelo frontend.
    Grava o pedaço temporário em disco no servidor.
    """
    try:
        session_dir = os.path.join(CHUNK_UPLOADS, upload_id)
        os.makedirs(session_dir, exist_ok=True)
        chunk_path = os.path.join(session_dir, f"chunk_{chunk_index:05d}.part")

        with open(chunk_path, "wb") as f:
            shutil.copyfileobj(chunk_file.file, f, length=4 * 1024 * 1024)

        logger.debug(f"📦 [CHUNK-UPLOAD] upload_id={upload_id} | chunk {chunk_index + 1}/{total_chunks}")
        return {"success": True, "chunk_index": chunk_index}
    except Exception as e:
        logger.error(f"❌ [CHUNK-UPLOAD-ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao salvar parte do upload: {str(e)}")


@app.post("/api/upload/complete")
async def complete_chunked_upload(
    upload_id: str = Form(...),
    filename: str = Form(...),
    total_chunks: int = Form(...),
):
    """
    Reconstitui de forma contínua e idêntica bit-a-bit todas as partes enviadas
    num único arquivo de vídeo final antes de qualquer extração/transcrição.
    """
    try:
        session_dir = os.path.join(CHUNK_UPLOADS, upload_id)
        if not os.path.exists(session_dir):
            raise HTTPException(status_code=400, detail="Sessão de upload não encontrada.")

        ext = os.path.splitext(filename)[1] or ".mp4"
        saved_video = os.path.join(TEMP_UPLOADS, f"input_video_{uuid.uuid4().hex[:8]}{ext}")

        with open(saved_video, "wb") as f_out:
            for idx in range(total_chunks):
                chunk_path = os.path.join(session_dir, f"chunk_{idx:05d}.part")
                if not os.path.exists(chunk_path):
                    raise HTTPException(status_code=400, detail=f"Parte {idx} não encontrada para montagem.")
                with open(chunk_path, "rb") as f_in:
                    shutil.copyfileobj(f_in, f_out, length=8 * 1024 * 1024)

        # Limpa o diretório de partes
        shutil.rmtree(session_dir, ignore_errors=True)
        file_size = os.path.getsize(saved_video)
        logger.info(f"✅ [CHUNK-COMPLETE] Vídeo montado com sucesso | path={saved_video} | size={file_size} bytes")

        return {
            "success": True,
            "saved_video_path": saved_video,
            "filename": filename,
            "file_size": file_size,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [CHUNK-COMPLETE-ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao reconstituir o arquivo: {str(e)}")


@app.post("/api/extract")
async def extract_video(
    video: Optional[UploadFile] = File(None),
    video_url: Optional[str] = Form(None),
    chunked_video_path: Optional[str] = Form(None),
    chunked_filename: Optional[str] = Form(None),
    subtitle: Optional[UploadFile] = File(None),
    language: str = Form("pt"),
    min_interval: float = Form(2.5),
    similarity_threshold: float = Form(88.0),
    sync: bool = Query(False),
):
    try:
        saved_video = ""
        raw_name = "video_treinamento"

        # 1. Caso A: Vídeo reconstituído via Chunked Upload
        if chunked_video_path and os.path.exists(chunked_video_path):
            saved_video = chunked_video_path
            raw_name = os.path.splitext(chunked_filename or os.path.basename(chunked_video_path))[0]
            logger.info(f"🚀 [EXTRACT-ENDPOINT] Usando vídeo previamente montado em partes | name={raw_name} | path={saved_video}")

        # 2. Caso B: Vídeo enviado via Link (Google Drive ou URL web)
        elif video_url and video_url.strip():
            clean_url = video_url.strip()
            logger.info(f"🚀 [EXTRACT-ENDPOINT] Baixando vídeo a partir de URL | url={clean_url}")
            temp_dest = os.path.join(TEMP_UPLOADS, f"input_video_{uuid.uuid4().hex[:8]}.mp4")
            
            job_id_dl = f"job_{uuid.uuid4().hex}"
            extraction_jobs[job_id_dl] = {
                "status": "processing",
                "stage": "upload",
                "progress": 0.02,
                "message": "Baixando vídeo a partir do link fornecido...",
                "result": None,
                "error": None,
            }

            def url_progress(ratio, cur, tot):
                pct = min(0.06, 0.01 + (ratio * 0.05))
                extraction_jobs[job_id_dl]["progress"] = round(pct, 3)
                mb_cur = round(cur / (1024 * 1024), 1)
                mb_tot = round(tot / (1024 * 1024), 1) if tot > 0 else "?"
                extraction_jobs[job_id_dl]["message"] = f"Baixando vídeo: {mb_cur}MB / {mb_tot}MB..."

            try:
                detected_name = download_video_from_url(clean_url, temp_dest, progress_callback=url_progress)
                saved_video = temp_dest
                raw_name = os.path.splitext(detected_name)[0]
                logger.info(f"✅ [EXTRACT-ENDPOINT] Download concluído com sucesso | name={raw_name} | size={os.path.getsize(saved_video)} bytes")
            except Exception as dl_err:
                logger.error(f"❌ [EXTRACT-ENDPOINT] Erro ao baixar vídeo da URL: {str(dl_err)}")
                raise HTTPException(status_code=400, detail=f"Não foi possível baixar o vídeo da URL informada: {str(dl_err)}")

        # 3. Caso C: Upload de arquivo direto multipart tradicional
        elif video and video.filename:
            logger.info(f"🚀 [EXTRACT-ENDPOINT] Requisição com arquivo direto | filename={video.filename} | lang={language} | sync={sync}")
            ext = os.path.splitext(video.filename)[1] or ".mp4"
            saved_video = os.path.join(TEMP_UPLOADS, f"input_video_{uuid.uuid4().hex[:8]}{ext}")
            with open(saved_video, "wb") as f:
                shutil.copyfileobj(video.file, f, length=16 * 1024 * 1024)
            raw_name = os.path.splitext(video.filename)[0]
            logger.info(f"✅ [EXTRACT-ENDPOINT] Arquivo direto salvo | size={os.path.getsize(saved_video)} bytes")
        else:
            raise HTTPException(status_code=400, detail="Nenhum arquivo de vídeo, link ou upload em partes foi fornecido.")

        sub_bytes = await subtitle.read() if (subtitle and subtitle.filename) else None
        if sub_bytes:
            logger.info(f"📄 [EXTRACT-ENDPOINT] Arquivo de legenda detectado | size={len(sub_bytes)} bytes")
        else:
            logger.debug("📄 [EXTRACT-ENDPOINT] Nenhum arquivo de legenda fornecido")

        job_id = f"job_{uuid.uuid4().hex}"
        logger.info(f"🎯 [EXTRACT-ENDPOINT] Job criado | job_id={job_id}")

        extraction_jobs[job_id] = {
            "status": "processing",
            "stage": "upload",
            "progress": 0.05,
            "message": "Vídeo pronto. Iniciando análise...",
            "result": None,
            "error": None,
        }
        save_job_state(job_id)

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


@app.post("/api/extract/cancel/{job_id}")
def cancel_extraction(job_id: str):
    logger.info(f"🛑 [CANCEL-ENDPOINT] Solicitação de cancelamento | job_id={job_id}")
    job = get_job(job_id)
    if job:
        job["status"] = "cancelled"
        job["message"] = "Processamento suspenso pelo usuário."
        save_job_state(job_id)
        return {"success": True, "message": "Job cancelado com sucesso."}
    return {"success": False, "message": "Job não encontrado."}


@app.get("/api/extract/progress/{job_id}")
def get_extract_progress(job_id: str):
    logger.debug(f"🔍 [PROGRESS-ENDPOINT] Consultando progresso | job_id={job_id}")
    job = get_job(job_id)
    if not job:
        # Dá uma segunda chance breve (150ms) caso o worker esteja executando os.replace concorrentemente
        time.sleep(0.15)
        job = get_job(job_id)

    if not job:
        logger.warn(f"⚠️ [PROGRESS-ENDPOINT] Job não encontrado | job_id={job_id}")
        raise HTTPException(status_code=404, detail="Job não encontrado")

    logger.debug(f"📊 [PROGRESS-ENDPOINT] Job encontrado | job_id={job_id} | status={job.get('status')} | progress={job.get('progress', 0)}")
    return job


@app.post("/api/frames/{frame_id}/adjust-time")
def adjust_frame_time(frame_id: str, req: AdjustTimeRequest, job_id: str = Query(...)):
    logger.info(f"⏰ [ADJUST-TIME-ENDPOINT] Solicitação de ajuste | job_id={job_id} | frame_id={frame_id} | delta={req.delta_seconds}s")

    job = get_job(job_id)
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

    save_job_state(job_id)
    step_idx = frames.index(target_frame) + 1
    logger.info(f"✅ [ADJUST-TIME-ENDPOINT] Frame ajustado com sucesso | job_id={job_id} | frame_id={frame_id} | new_time={new_time}s")
    return {"success": True, "frame": frame_to_dict(target_frame, step_idx)}


@app.get("/api/export/docx")
def export_docx(title: str = Query("Guia de Treinamento"), frame_ids: str = Query(""), job_id: str = Query(...)):
    logger.info(f"📄 [EXPORT-DOCX-ENDPOINT] Solicitação de export | job_id={job_id} | title={title}")

    job = get_job(job_id)
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

    job = get_job(job_id)
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

    job = get_job(job_id)
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

    job = get_job(job_id)
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

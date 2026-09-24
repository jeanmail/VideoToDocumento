export interface SubtitleItem {
  index: number;
  start_seconds: number;
  end_seconds: number;
  start_time_str: string;
  end_time_str: string;
  text: string;
}

export interface FrameItem {
  id: string;
  step_number: number;
  timestamp_seconds: number;
  timestamp_str: string;
  image_url: string;
  thumb_url: string;
  step_title: string;
  subtitle_text: string;
  is_duplicate_candidate: boolean;
  is_non_system_candidate: boolean;
  similarity_score: number;
  selected: boolean;
}

export interface ExtractResponse {
  success: boolean;
  video_name: string;
  frames: FrameItem[];
  subtitles: SubtitleItem[];
  total_frames: number;
  approved_count: number;
  duplicate_count: number;
  non_system_count: number;
}

export interface PublishRequest {
  title: string;
  description?: string;
  product_slug: string;
  bucket_name?: string;
  selected_frame_ids: string[];
  job_id?: string;
}

export interface PublishResponse {
  success: boolean;
  gcs_prefix: string;
  message: string;
}

export class ExtractError extends Error {
  details?: string;
  constructor(message: string, details?: string) {
    super(message);
    this.name = 'ExtractError';
    this.details = details;
  }
}

export interface ExtractController {
  abort: () => void;
}

export interface ExtractParams {
  videoFile?: File | null;
  videoUrl?: string | null;
  subtitleFile?: File | null;
  language?: string;
  minInterval?: number;
  similarityThreshold?: number;
  onProgress?: (progress: number, message: string, stage: string) => void;
  controllerRef?: { current?: ExtractController };
}

const API_BASE = '/api';

export const api = {
  /**
   * Envia arquivo fatiado em partes (chunks de ~15MB) para evitar o erro de limite
   * de payload do Google Cloud Run (32MB) e outros servidores sem vendor lock-in.
   */
  async uploadFileChunked(
    file: File,
    chunkSize = 15 * 1024 * 1024,
    onProgress?: (ratio: number, msg: string) => void,
    checkCancelled?: () => boolean
  ): Promise<{ saved_video_path: string; filename: string }> {
    const uploadId = `upl_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
    const totalChunks = Math.ceil(file.size / chunkSize);

    for (let i = 0; i < totalChunks; i++) {
      if (checkCancelled && checkCancelled()) {
        throw new ExtractError('Processamento suspenso pelo usuário.');
      }

      const start = i * chunkSize;
      const end = Math.min(file.size, start + chunkSize);
      const chunkBlob = file.slice(start, end);

      const chunkForm = new FormData();
      chunkForm.append('upload_id', uploadId);
      chunkForm.append('chunk_index', i.toString());
      chunkForm.append('total_chunks', totalChunks.toString());
      chunkForm.append('chunk_file', chunkBlob, file.name);

      const pct = Math.round(((i + 1) / totalChunks) * 100);
      onProgress?.((i + 1) / totalChunks, `Enviando parte ${i + 1} de ${totalChunks} (${pct}%)...`);

      const resp = await fetch(`${API_BASE}/upload/chunk`, {
        method: 'POST',
        body: chunkForm,
      });

      if (!resp.ok) {
        const errJson = await resp.json().catch(() => ({ detail: 'Erro no upload de parte' }));
        throw new ExtractError(errJson.detail || `Erro ao enviar parte ${i + 1}`);
      }
    }

    if (checkCancelled && checkCancelled()) {
      throw new ExtractError('Processamento suspenso pelo usuário.');
    }

    onProgress?.(1, 'Montando vídeo no servidor...');
    const completeForm = new FormData();
    completeForm.append('upload_id', uploadId);
    completeForm.append('filename', file.name);
    completeForm.append('total_chunks', totalChunks.toString());

    const compResp = await fetch(`${API_BASE}/upload/complete`, {
      method: 'POST',
      body: completeForm,
    });

    if (!compResp.ok) {
      const errJson = await compResp.json().catch(() => ({ detail: 'Erro ao unir partes do vídeo' }));
      throw new ExtractError(errJson.detail || 'Falha ao reconstituir vídeo no servidor');
    }

    return compResp.json();
  },

  async extractVideo(
    videoOrParams: File | ExtractParams,
    subtitleFile?: File | null,
    language = 'pt',
    minInterval = 2.5,
    similarityThreshold = 88,
    onProgress?: (progress: number, message: string, stage: string) => void,
    controllerRef?: { current?: ExtractController }
  ): Promise<ExtractResponse> {
    // Permite chamada com objeto ExtractParams ou assinatura legada
    let file: File | null = null;
    let url: string | null = null;
    let sub: File | null = null;
    let lang = language;
    let minInt = minInterval;
    let simThresh = similarityThreshold;
    let progCb = onProgress;
    let ctrlRef = controllerRef;

    if (videoOrParams instanceof File) {
      file = videoOrParams;
      sub = subtitleFile || null;
    } else {
      file = videoOrParams.videoFile || null;
      url = videoOrParams.videoUrl || null;
      sub = videoOrParams.subtitleFile || null;
      lang = videoOrParams.language || 'pt';
      minInt = videoOrParams.minInterval ?? 2.5;
      simThresh = videoOrParams.similarityThreshold ?? 88;
      progCb = videoOrParams.onProgress;
      ctrlRef = videoOrParams.controllerRef;
    }

    let activeXhr: XMLHttpRequest | null = null;
    let activeInterval: any = null;
    let activeJobId: string | null = null;
    let isCancelled = false;

    const cleanup = () => {
      if (activeInterval) {
        clearInterval(activeInterval);
        activeInterval = null;
      }
    };

    if (ctrlRef) {
      ctrlRef.current = {
        abort: () => {
          isCancelled = true;
          cleanup();
          if (activeXhr) {
            try { activeXhr.abort(); } catch {}
          }
          if (activeJobId) {
            fetch(`${API_BASE}/extract/cancel/${activeJobId}`, { method: 'POST' }).catch(() => {});
          }
        }
      };
    }

    const formData = new FormData();
    if (sub) {
      formData.append('subtitle', sub);
    }
    formData.append('language', lang);
    formData.append('min_interval', minInt.toString());
    formData.append('similarity_threshold', simThresh.toString());

    // Se tiver URL de vídeo (ex: Google Drive ou link direto)
    if (url && url.trim()) {
      progCb?.(2, 'Conectando ao link do vídeo...', 'upload');
      formData.append('video_url', url.trim());
    }
    // Se for arquivo e maior que 20MB, usa upload fatiado (chunked) para contornar qualquer limite
    else if (file && file.size > 20 * 1024 * 1024) {
      progCb?.(1, 'Iniciando upload fatiado seguro...', 'upload');
      const assembled = await this.uploadFileChunked(
        file,
        15 * 1024 * 1024,
        (ratio, msg) => {
          progCb?.(Math.min(5, Math.max(1, Math.round(ratio * 5))), msg, 'upload');
        },
        () => isCancelled
      );
      formData.append('chunked_video_path', assembled.saved_video_path);
      formData.append('chunked_filename', assembled.filename);
    }
    // Arquivo menor que 20MB: upload multipart normal
    else if (file) {
      formData.append('video', file);
    } else {
      throw new ExtractError('Nenhum vídeo ou link foi informado.');
    }

    if (isCancelled) {
      throw new ExtractError('Processamento suspenso pelo usuário.');
    }

    // Dispara a requisição /api/extract
    const jobData: { job_id?: string; status?: string } & Partial<ExtractResponse> = await new Promise(
      (resolve, reject) => {
        const xhr = new XMLHttpRequest();
        activeXhr = xhr;
        xhr.open('POST', `${API_BASE}/extract`);

        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable && !isCancelled && file && file.size <= 20 * 1024 * 1024) {
            const uploadPct = Math.round((e.loaded / e.total) * 100);
            progCb?.(
              Math.min(5, Math.round(uploadPct * 0.05)),
              `Enviando vídeo para o servidor (${uploadPct}%)...`,
              'upload'
            );
          }
        };

        xhr.onload = () => {
          activeXhr = null;
          if (isCancelled) {
            return reject(new ExtractError('Processamento suspenso pelo usuário.'));
          }

          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              const data = JSON.parse(xhr.responseText);
              resolve(data);
            } catch {
              reject(new ExtractError('Resposta inválida do servidor ao iniciar processamento'));
            }
          } else {
            try {
              const err = JSON.parse(xhr.responseText);
              const msg = typeof err.detail === 'object' && err.detail?.message ? err.detail.message : (err.detail || 'Falha ao iniciar processamento');
              const det = typeof err.detail === 'object' && err.detail?.details ? err.detail.details : (typeof err.detail === 'string' ? err.detail : undefined);
              reject(new ExtractError(msg, det));
            } catch {
              reject(new ExtractError(`Erro no servidor (HTTP ${xhr.status})`));
            }
          }
        };

        xhr.onerror = () => {
          activeXhr = null;
          if (isCancelled) {
            reject(new ExtractError('Processamento suspenso pelo usuário.'));
          } else {
            reject(new ExtractError('Falha de conexão com o servidor'));
          }
        };

        xhr.onabort = () => {
          activeXhr = null;
          reject(new ExtractError('Processamento suspenso pelo usuário.'));
        };

        xhr.send(formData);
      }
    );

    if (isCancelled) {
      throw new ExtractError('Processamento suspenso pelo usuário.');
    }

    // Se o backend respondeu de forma síncrona diretamente
    if (!jobData.job_id && (jobData as ExtractResponse).frames) {
      progCb?.(100, 'Processamento concluído!', 'done');
      return jobData as ExtractResponse;
    }

    const jobId = jobData.job_id!;
    activeJobId = jobId;

    // 2. Polling contínuo do progresso da transcrição e extração
    return new Promise((resolve, reject) => {
      activeInterval = setInterval(async () => {
        if (isCancelled) {
          cleanup();
          return reject(new ExtractError('Processamento suspenso pelo usuário.'));
        }

        try {
          const res = await fetch(`${API_BASE}/extract/progress/${jobId}`);
          if (!res.ok) {
            cleanup();
            reject(new ExtractError(`Falha ao consultar progresso (HTTP ${res.status})`));
            return;
          }

          const job = await res.json();
          if (isCancelled) {
            cleanup();
            return reject(new ExtractError('Processamento suspenso pelo usuário.'));
          }

          const percent = Math.min(100, Math.max(5, Math.round((job.progress || 0) * 100)));
          progCb?.(percent, job.message || 'Processando...', job.stage || 'transcription');

          if (job.status === 'completed') {
            cleanup();
            progCb?.(100, 'Processamento concluído com sucesso!', 'done');
            resolve({ ...job.result, job_id: jobId });
          } else if (job.status === 'cancelled') {
            cleanup();
            reject(new ExtractError('Processamento suspenso pelo usuário.'));
          } else if (job.status === 'error') {
            cleanup();
            reject(new ExtractError(job.message || job.error || 'Erro durante o processamento do vídeo', job.details || job.error));
          }
        } catch (err: any) {
          cleanup();
          if (isCancelled) {
            reject(new ExtractError('Processamento suspenso pelo usuário.'));
          } else {
            reject(err instanceof ExtractError ? err : new ExtractError(err.message || 'Erro de comunicação', err.stack));
          }
        }
      }, 400);
    });
  },

  async cancelExtraction(jobId: string): Promise<void> {
    await fetch(`${API_BASE}/extract/cancel/${jobId}`, { method: 'POST' }).catch(() => {});
  },

  async adjustFrameTime(frameId: string, deltaSeconds: number): Promise<{ success: boolean; frame: FrameItem }> {
    const res = await fetch(`${API_BASE}/frames/${frameId}/adjust-time`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ delta_seconds: deltaSeconds }),
    });

    if (!res.ok) throw new Error('Falha ao ajustar tempo do frame');
    return res.json();
  },

  getDocxDownloadUrl(title: string, selectedFrameIds: string[], jobId: string): string {
    const params = new URLSearchParams({
      title,
      frame_ids: selectedFrameIds.join(','),
      job_id: jobId,
    });
    return `${API_BASE}/export/docx?${params.toString()}`;
  },

  getPdfDownloadUrl(title: string, selectedFrameIds: string[], jobId: string): string {
    const params = new URLSearchParams({
      title,
      frame_ids: selectedFrameIds.join(','),
      job_id: jobId,
    });
    return `${API_BASE}/export/pdf?${params.toString()}`;
  },

  getZipDownloadUrl(title: string, selectedFrameIds: string[], jobId: string): string {
    const params = new URLSearchParams({
      title,
      frame_ids: selectedFrameIds.join(','),
      job_id: jobId,
    });
    return `${API_BASE}/export/zip?${params.toString()}`;
  },

  async publishToGCS(req: PublishRequest): Promise<PublishResponse> {
    const res = await fetch(`${API_BASE}/publish/gcs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Erro na publicação GCS' }));
      throw new Error(err.detail || 'Falha na publicação para o GCS');
    }

    return res.json();
  }
};

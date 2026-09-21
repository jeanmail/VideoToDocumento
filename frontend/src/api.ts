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
}

export interface PublishResponse {
  success: boolean;
  gcs_prefix: string;
  message: string;
}

const API_BASE = '/api';

export const api = {
  async extractVideo(
    videoFile: File,
    subtitleFile?: File | null,
    language = 'pt',
    minInterval = 2.5,
    similarityThreshold = 88,
    onProgress?: (progress: number, message: string, stage: string) => void
  ): Promise<ExtractResponse> {
    const formData = new FormData();
    formData.append('video', videoFile);
    if (subtitleFile) {
      formData.append('subtitle', subtitleFile);
    }
    formData.append('language', language);
    formData.append('min_interval', minInterval.toString());
    formData.append('similarity_threshold', similarityThreshold.toString());

    // 1. Envio do vídeo com acompanhamento de upload via XMLHttpRequest
    const jobData: { job_id?: string; status?: string } & Partial<ExtractResponse> = await new Promise(
      (resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', `${API_BASE}/extract`);

        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            const uploadPct = Math.round((e.loaded / e.total) * 100);
            onProgress?.(
              Math.min(5, Math.round(uploadPct * 0.05)),
              `Enviando vídeo para o servidor (${uploadPct}%)...`,
              'upload'
            );
          }
        };

        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              const data = JSON.parse(xhr.responseText);
              resolve(data);
            } catch {
              reject(new Error('Resposta inválida do servidor ao iniciar processamento'));
            }
          } else {
            try {
              const err = JSON.parse(xhr.responseText);
              reject(new Error(err.detail || 'Falha ao iniciar processamento'));
            } catch {
              reject(new Error(`Erro no servidor (${xhr.status})`));
            }
          }
        };

        xhr.onerror = () => reject(new Error('Falha de conexão com o servidor'));
        xhr.send(formData);
      }
    );

    // Se o backend respondeu de forma síncrona diretamente
    if (!jobData.job_id && (jobData as ExtractResponse).frames) {
      onProgress?.(100, 'Processamento concluído!', 'done');
      return jobData as ExtractResponse;
    }

    const jobId = jobData.job_id!;

    // 2. Polling contínuo do progresso da transcrição e extração
    return new Promise((resolve, reject) => {
      const interval = setInterval(async () => {
        try {
          const res = await fetch(`${API_BASE}/extract/progress/${jobId}`);
          if (!res.ok) {
            clearInterval(interval);
            reject(new Error('Erro ao acompanhar progresso do processamento'));
            return;
          }

          const job = await res.json();
          const percent = Math.min(100, Math.max(5, Math.round((job.progress || 0) * 100)));
          onProgress?.(percent, job.message || 'Processando...', job.stage || 'transcription');

          if (job.status === 'completed') {
            clearInterval(interval);
            onProgress?.(100, 'Processamento concluído com sucesso!', 'done');
            resolve(job.result);
          } else if (job.status === 'error') {
            clearInterval(interval);
            reject(new Error(job.error || 'Erro durante a transcrição ou extração'));
          }
        } catch (err) {
          clearInterval(interval);
          reject(err);
        }
      }, 400);
    });
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

  getDocxDownloadUrl(title: string, selectedFrameIds: string[]): string {
    const params = new URLSearchParams({
      title,
      frame_ids: selectedFrameIds.join(','),
    });
    return `${API_BASE}/export/docx?${params.toString()}`;
  },

  getPdfDownloadUrl(title: string, selectedFrameIds: string[]): string {
    const params = new URLSearchParams({
      title,
      frame_ids: selectedFrameIds.join(','),
    });
    return `${API_BASE}/export/pdf?${params.toString()}`;
  },

  getZipDownloadUrl(title: string, selectedFrameIds: string[]): string {
    const params = new URLSearchParams({
      title,
      frame_ids: selectedFrameIds.join(','),
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

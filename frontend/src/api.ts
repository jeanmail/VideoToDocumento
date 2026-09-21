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
    similarityThreshold = 88
  ): Promise<ExtractResponse> {
    const formData = new FormData();
    formData.append('video', videoFile);
    if (subtitleFile) {
      formData.append('subtitle', subtitleFile);
    }
    formData.append('language', language);
    formData.append('min_interval', minInterval.toString());
    formData.append('similarity_threshold', similarityThreshold.toString());

    const res = await fetch(`${API_BASE}/extract`, {
      method: 'POST',
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Erro no processamento do vídeo' }));
      throw new Error(err.detail || 'Falha ao processar vídeo');
    }

    return res.json();
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

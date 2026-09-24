"""
Módulo de extração de áudio e transcrição automática via Faster-Whisper.
Gera legendas com timestamps no padrão .srt.
"""

import os
import subprocess
from typing import List, Optional, Callable
import imageio_ffmpeg

from core.srt_parser import SubtitleItem, export_to_srt


class AudioTranscriber:
    _cached_model = None
    _cached_model_key = None

    def __init__(self, model_size: str = "base", device: str = "cpu", compute_type: str = "int8"):
        """
        model_size: 'tiny', 'base', 'small', 'medium'.
        'base' é rápido, leve (~140MB) e excelente para português/inglês em CPU.
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type

    def _get_ffmpeg_path(self) -> str:
        """Obtém o binário estático do FFmpeg garantido pelo imageio-ffmpeg."""
        return imageio_ffmpeg.get_ffmpeg_exe()

    def extract_audio(self, video_path: str, output_wav_path: str) -> str:
        """
        Extrai o áudio do vídeo para WAV mono de 16kHz (padrão ideal do Whisper).
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_wav_path)), exist_ok=True)
        ffmpeg_bin = self._get_ffmpeg_path()

        cmd = [
            ffmpeg_bin,
            "-y",               # sobrescrever saída
            "-i", video_path,   # vídeo de entrada
            "-vn",              # sem vídeo
            "-acodec", "pcm_s16le",
            "-ar", "16000",     # 16kHz
            "-ac", "1",         # mono
            output_wav_path
        ]

        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            err_msg = result.stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"Erro ao extrair áudio com FFmpeg: {err_msg}")

        return output_wav_path

    def _load_model(self):
        cache_key = f"{self.model_size}_{self.device}_{self.compute_type}"
        if AudioTranscriber._cached_model is not None and AudioTranscriber._cached_model_key == cache_key:
            self._model = AudioTranscriber._cached_model
            return

        from faster_whisper import WhisperModel
        # int8 em CPU é extremamente rápido e consome 50% menos memória
        try:
            self._model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
        except Exception:
            # Fallback para float32 caso a CPU não suporte int8
            self._model = WhisperModel(self.model_size, device=self.device, compute_type="float32")

        AudioTranscriber._cached_model = self._model
        AudioTranscriber._cached_model_key = cache_key

    def transcribe(
        self,
        video_or_audio_path: str,
        language: Optional[str] = "pt",
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[SubtitleItem]:
        """
        Transcreve o arquivo de vídeo/áudio e retorna lista de SubtitleItem com timestamps.
        """
        if progress_callback:
            progress_callback(0.05, "Inicializando motor de transcrição...")

        self._load_model()

        # Se for vídeo, extrai o áudio WAV primeiro
        ext = os.path.splitext(video_or_audio_path)[1].lower()
        if ext not in [".wav", ".mp3"]:
            wav_temp = f"{video_or_audio_path}_temp_audio.wav"
            if progress_callback:
                progress_callback(0.15, "Extraindo faixa de áudio do vídeo...")
            audio_path = self.extract_audio(video_or_audio_path, wav_temp)
        else:
            audio_path = video_or_audio_path
            wav_temp = None

        try:
            if progress_callback:
                progress_callback(0.30, "Processando fala do áudio...")

            lang_arg = language if (language and language != "auto") else None
            segments, info = self._model.transcribe(
                audio_path,
                language=lang_arg,
                beam_size=5,
                word_timestamps=False,
                vad_filter=True  # Filtra silêncios automaticamente
            )

            results: List[SubtitleItem] = []
            duration = getattr(info, 'duration', 0.0)

            for idx, seg in enumerate(segments, start=1):
                clean_text = seg.text.strip()
                if clean_text:
                    results.append(SubtitleItem(
                        index=idx,
                        start_seconds=round(seg.start, 2),
                        end_seconds=round(seg.end, 2),
                        text=clean_text
                    ))

                if progress_callback and duration > 0:
                    prog = min(0.95, 0.30 + (0.65 * (seg.end / duration)))
                    progress_callback(prog, f"Transcrevendo: {int(seg.end)}s / {int(duration)}s...")

            if progress_callback:
                progress_callback(1.0, f"Transcrição concluída! {len(results)} segmentos gerados.")

            return results

        finally:
            # Limpa o arquivo WAV temporário se foi criado
            if wav_temp and os.path.exists(wav_temp):
                try:
                    os.remove(wav_temp)
                except Exception:
                    pass

    def save_srt(self, items: List[SubtitleItem], output_srt_path: str) -> str:
        """Salva a lista de itens de legenda diretamente em arquivo .srt."""
        os.makedirs(os.path.dirname(os.path.abspath(output_srt_path)), exist_ok=True)
        srt_content = export_to_srt(items)
        with open(output_srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)
        return output_srt_path

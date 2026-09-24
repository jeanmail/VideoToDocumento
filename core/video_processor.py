"""
Processador de vídeo: extração de frames, cálculo de similaridade e detecção de redundâncias.
"""

from dataclasses import dataclass
import os
import uuid
from typing import List, Optional, Tuple, Callable
import cv2
import numpy as np
from PIL import Image

from core.srt_parser import SubtitleItem


@dataclass
class ExtractedFrame:
    id: str
    timestamp_seconds: float
    timestamp_str: str
    subtitle_text: str
    image_path: str
    thumb_path: str = ""
    is_duplicate_candidate: bool = False
    similarity_score: float = 0.0
    selected: bool = True
    step_title: str = ""
    ocr_text: str = ""
    group_id: Optional[str] = None
    is_non_system_candidate: bool = False
    non_system_reason: str = ""


def detect_non_system_frame(image_np: np.ndarray) -> Tuple[bool, str]:
    """
    Analisa se o quadro capturado parece ser apenas câmeras/webcams/pessoas ou
    quadro sem interface de sistema, utilizando métricas de visão computacional:
    1. Detecção de linhas ortogonais estruturadas (típicas de janelas, menus, tabelas e inputs).
    2. Proporção de tons de pele humana (espaço de cores YCrCb).
    3. Densidade de bordas e contraste característico de telas de software.
    """
    if image_np is None or image_np.size == 0:
        return False, ""

    try:
        h, w = image_np.shape[:2]
        target_w = 480
        target_h = int(h * (target_w / float(w)))
        small = cv2.resize(image_np, (target_w, target_h), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

        edges = cv2.Canny(gray, 50, 150)
        total_edge_pixels = int(np.count_nonzero(edges))
        total_pixels = target_w * target_h

        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 1))
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 15))
        h_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, h_kernel)
        v_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, v_kernel)
        ortho_pixels = int(np.count_nonzero(h_lines) + np.count_nonzero(v_lines))

        edge_density = total_edge_pixels / float(total_pixels)
        ortho_ratio = ortho_pixels / float(max(1, total_edge_pixels))

        ycrcb = cv2.cvtColor(small, cv2.COLOR_BGR2YCrCb)
        skin_mask = cv2.inRange(ycrcb, np.array([0, 133, 77]), np.array([255, 173, 127]))
        skin_ratio = int(np.count_nonzero(skin_mask)) / float(total_pixels)

        # Regra 1: Alta proporção de pele E baixa estrutura de linhas ortogonais de software
        if skin_ratio > 0.07 and ortho_ratio < 0.40:
            return True, f"Câmera/Pessoas detectadas ({skin_ratio*100:.1f}% área de pele sem tela de sistema)"

        # Regra 2: Ausência de interface (muito pouca borda ou pouquíssima estrutura ortogonal)
        if edge_density < 0.012 and ortho_ratio < 0.28:
            return True, "Tela sem interface de software identificável"

        return False, ""
    except Exception:
        return False, ""


def ensure_thumbnail(image_path: str, max_width: int = 480) -> str:
    """
    Retorna o caminho de um thumbnail leve (JPEG ~25KB) para exibição rápida na UI.
    Gera automaticamente caso ainda não exista no disco.
    """
    if not image_path or not os.path.exists(image_path):
        return image_path

    base, ext = os.path.splitext(image_path)
    thumb_path = f"{base}_thumb.jpg"
    if os.path.exists(thumb_path):
        return thumb_path

    try:
        img = cv2.imread(image_path)
        if img is not None:
            h, w = img.shape[:2]
            if w > max_width:
                thumb_h = int(h * (max_width / float(w)))
                thumb_img = cv2.resize(img, (max_width, thumb_h), interpolation=cv2.INTER_AREA)
            else:
                thumb_img = img
            cv2.imwrite(thumb_path, thumb_img, [cv2.IMWRITE_JPEG_QUALITY, 70])
            return thumb_path
    except Exception:
        pass
    return image_path


def compute_dhash(image_np: np.ndarray, hash_size: int = 8) -> int:
    """
    Calcula o Difference Hash (dHash) de 64 bits para comparação visual de interfaces.
    """
    if len(image_np.shape) == 3:
        gray = cv2.cvtColor(image_np, cv2.COLOR_BGR2GRAY)
    else:
        gray = image_np

    # Redimensiona para (hash_size + 1, hash_size)
    resized = cv2.resize(gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    
    # Compara pixels adjacentes
    diff = resized[:, 1:] > resized[:, :-1]
    
    # Converte array booleano em inteiro de 64 bits
    hash_val = 0
    for bit in diff.flatten():
        hash_val = (hash_val << 1) | int(bit)
    return hash_val


def hamming_distance(hash1: int, hash2: int, bit_length: int = 64) -> int:
    """Calcula a distância de Hamming entre dois hashes."""
    x = hash1 ^ hash2
    distance = 0
    while x > 0:
        distance += x & 1
        x >>= 1
    return distance


def calculate_similarity(hash1: int, hash2: int, bit_length: int = 64) -> float:
    """Retorna a similaridade entre 0.0 e 1.0 baseada na distância de Hamming."""
    dist = hamming_distance(hash1, hash2, bit_length)
    return max(0.0, 1.0 - (dist / float(bit_length)))


class VideoProcessor:
    def __init__(self, video_path: str):
        self.video_path = video_path
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Vídeo não encontrado no caminho: {video_path}")

        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            raise ValueError(f"Não foi possível abrir o vídeo: {video_path}")

        self.fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.duration_seconds = self.total_frames / self.fps if self.fps > 0 else 0.0
        self.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

    def get_frame_at_timestamp(self, timestamp_seconds: float) -> Optional[np.ndarray]:
        """
        Extrai o quadro exato no segundo especificado.
        """
        if timestamp_seconds < 0:
            timestamp_seconds = 0.0
        if timestamp_seconds > self.duration_seconds:
            timestamp_seconds = max(0.0, self.duration_seconds - 0.1)

        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            return None

        # Posiciona por milissegundos
        cap.set(cv2.CAP_PROP_POS_MSEC, timestamp_seconds * 1000.0)
        success, frame = cap.read()
        cap.release()

        if success and frame is not None:
            return frame
        return None

    def save_frame_to_file(self, frame: np.ndarray, output_dir: str, file_prefix: str = "frame") -> str:
        """Salva a imagem do frame em alta qualidade e gera thumbnail leve para a interface."""
        os.makedirs(output_dir, exist_ok=True)
        unique_id = uuid.uuid4().hex[:8]
        filename = f"{file_prefix}_{unique_id}.jpg"
        filepath = os.path.join(output_dir, filename)
        cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, 92])

        # Gera thumbnail leve (max width 480px, ~20-30KB)
        try:
            h, w = frame.shape[:2]
            max_w = 480
            if w > max_w:
                thumb_h = int(h * (max_w / float(w)))
                thumb_frame = cv2.resize(frame, (max_w, thumb_h), interpolation=cv2.INTER_AREA)
            else:
                thumb_frame = frame
            thumb_path = os.path.join(output_dir, f"{file_prefix}_{unique_id}_thumb.jpg")
            cv2.imwrite(thumb_path, thumb_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        except Exception:
            pass

        return filepath

    def process_subtitles(
        self,
        subtitles: List[SubtitleItem],
        output_dir: str,
        min_interval_seconds: float = 2.0,
        similarity_threshold: float = 0.88,
        capture_offset_ratio: float = 0.2,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[ExtractedFrame]:
        """
        Percorre os itens de legenda, extrai os frames no momento ideal e
        marca potenciais capturas redundantes por análise de similaridade visual.
        Reutiliza uma única conexão VideoCapture aberta para evitar reaberturas pesadas de I/O em disco.
        """
        os.makedirs(output_dir, exist_ok=True)
        results: List[ExtractedFrame] = []
        last_extracted_time = -9999.0
        last_hash: Optional[int] = None
        total_subs = len(subtitles)

        cap = cv2.VideoCapture(self.video_path)
        try:
            for idx, sub in enumerate(subtitles):
                if progress_callback and total_subs > 0:
                    progress_callback((idx + 1) / float(total_subs), f"Extraindo e analisando telas ({idx + 1}/{total_subs})...")

                # Calcula o momento ideal de captura
                target_time = sub.start_seconds + (sub.duration_seconds * capture_offset_ratio)
                
                # Se for menor que o intervalo mínimo desde a última extração, ignoramos
                if (target_time - last_extracted_time) < min_interval_seconds:
                    continue

                if not cap.isOpened():
                    frame_img = self.get_frame_at_timestamp(target_time)
                else:
                    target_ms = max(0.0, min(self.duration_seconds - 0.05, target_time)) * 1000.0
                    cap.set(cv2.CAP_PROP_POS_MSEC, target_ms)
                    success, frame_img = cap.read()
                    if not success or frame_img is None:
                        frame_img = self.get_frame_at_timestamp(target_time)

                if frame_img is None:
                    continue

                # Calcula hash visual
                current_hash = compute_dhash(frame_img)
                is_duplicate = False
                sim_score = 0.0

                if last_hash is not None:
                    sim_score = calculate_similarity(last_hash, current_hash)
                    if sim_score >= similarity_threshold:
                        is_duplicate = True

                # Detecta câmeras, webcams ou quadros sem interface de software
                is_non_system, non_sys_reason = detect_non_system_frame(frame_img)

                # Salva o arquivo de imagem
                image_path = self.save_frame_to_file(frame_img, output_dir, file_prefix=f"step_{idx+1}")

                # Desmarca automaticamente os duplicados e telas sem sistema/webcams
                should_select = (not is_duplicate) and (not is_non_system)

                frame_id = f"frame_{idx+1}_{uuid.uuid4().hex[:6]}"
                results.append(ExtractedFrame(
                    id=frame_id,
                    timestamp_seconds=target_time,
                    timestamp_str=sub.start_time_str,
                    subtitle_text=sub.text,
                    image_path=image_path,
                    is_duplicate_candidate=is_duplicate,
                    similarity_score=round(sim_score, 3),
                    is_non_system_candidate=is_non_system,
                    non_system_reason=non_sys_reason,
                    selected=should_select,
                    step_title=f"Passo {len(results) + 1}",
                    ocr_text=""
                ))

                last_extracted_time = target_time
                last_hash = current_hash

        finally:
            if cap is not None:
                cap.release()

        return results

    def refresh_frame_image(self, extracted_frame: ExtractedFrame, new_timestamp: float, output_dir: str) -> bool:
        """
        Recarrega o frame para um novo timestamp (ex: avanço/recuo de 1s na auditoria)
        e atualiza o arquivo no disco.
        """
        new_frame = self.get_frame_at_timestamp(new_timestamp)
        if new_frame is None:
            return False

        # Salva sobrescrevendo ou gerando novo
        image_path = self.save_frame_to_file(new_frame, output_dir, file_prefix=f"adjusted_{extracted_frame.id}")
        
        # Remove a imagem antiga e seu thumbnail se existirem
        if os.path.exists(extracted_frame.image_path):
            try:
                os.remove(extracted_frame.image_path)
                old_thumb = ensure_thumbnail(extracted_frame.image_path)
                if old_thumb != extracted_frame.image_path and os.path.exists(old_thumb):
                    os.remove(old_thumb)
            except Exception:
                pass

        extracted_frame.image_path = image_path
        extracted_frame.thumb_path = ensure_thumbnail(image_path)
        extracted_frame.timestamp_seconds = new_timestamp
        
        # Atualiza a detecção de interface/câmera
        is_non_system, non_sys_reason = detect_non_system_frame(new_frame)
        extracted_frame.is_non_system_candidate = is_non_system
        extracted_frame.non_system_reason = non_sys_reason
        
        # Atualiza a string do timestamp
        tot = int(new_timestamp)
        h, m, s = tot // 3600, (tot % 3600) // 60, tot % 60
        extracted_frame.timestamp_str = f"{h:02d}:{m:02d}:{s:02d}"
        return True

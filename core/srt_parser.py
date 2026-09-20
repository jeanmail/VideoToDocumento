"""
Módulo de parsing, sincronização e exportação de arquivos de legenda:
Suporta .srt (SubRip), .vtt (WebVTT) e .sbv (YouTube SubViewer).
"""

from dataclasses import dataclass
import re
from typing import List, Union
import io


@dataclass
class SubtitleItem:
    index: int
    start_seconds: float
    end_seconds: float
    text: str

    @property
    def start_time_str(self) -> str:
        """Retorna o timestamp formatado no padrão HH:MM:SS."""
        total_seconds = int(self.start_seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    @property
    def end_time_str(self) -> str:
        """Retorna o timestamp final formatado no padrão HH:MM:SS."""
        total_seconds = int(self.end_seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.end_seconds - self.start_seconds)


def time_to_seconds(time_str: str) -> float:
    """
    Converte timestamp 'HH:MM:SS,mmm', 'HH:MM:SS.mmm' ou 'MM:SS.mmm' para segundos float.
    """
    time_str = time_str.strip().replace(',', '.')
    parts = time_str.split(':')
    if len(parts) == 3:
        hours = float(parts[0])
        minutes = float(parts[1])
        seconds = float(parts[2])
        return hours * 3600.0 + minutes * 60.0 + seconds
    elif len(parts) == 2:
        minutes = float(parts[0])
        seconds = float(parts[1])
        return minutes * 60.0 + seconds
    return float(parts[0])


def seconds_to_srt_time(seconds: float) -> str:
    """Converte segundos float para o formato padrão SRT: 'HH:MM:SS,mmm'."""
    total_ms = max(0, int(round(seconds * 1000)))
    ms = total_ms % 1000
    tot_sec = total_ms // 1000
    s = tot_sec % 60
    tot_min = tot_sec // 60
    m = tot_min % 60
    h = tot_min // 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _clean_subtitle_text(raw_text: str) -> str:
    """Remove formatações HTML (ex: <i>, <b>, <c.color>), tags VTT e normaliza espaços."""
    # Remove tags HTML e tags de estilo VTT como <c.color>
    text = re.sub(r'<[^>]+>', '', raw_text)
    # Remove marcações de voz VTT como <v Speaker>
    text = re.sub(r'<v\s+[^>]+>', '', text)
    # Normaliza quebras de linha em uma única linha contínua
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " ".join(lines)


def parse_subtitles(source: Union[str, bytes, io.StringIO, io.BytesIO]) -> List[SubtitleItem]:
    """
    Lê legendas em múltiplos formatos com timestamp:
    - .srt (SubRip clássico: 00:00:01,000 --> 00:00:04,000)
    - .vtt (WebVTT exportado pelo YouTube Studio: 00:00:01.000 --> 00:00:04.000)
    - .sbv (YouTube SubViewer: 0:00:01.000,0:00:04.000)
    """
    content = ""
    if isinstance(source, bytes):
        content = source.decode("utf-8-sig", errors="replace")
    elif isinstance(source, io.BytesIO):
        content = source.getvalue().decode("utf-8-sig", errors="replace")
    elif isinstance(source, io.StringIO):
        content = source.getvalue()
    elif isinstance(source, str):
        if "\n" in source or "-->" in source or ("," in source and ":" in source):
            content = source
        else:
            with open(source, "r", encoding="utf-8-sig", errors="replace") as f:
                content = f.read()

    # Normalizar quebras de linha
    content = content.replace("\r\n", "\n").replace("\r", "\n")

    items: List[SubtitleItem] = []

    # 1. Tentar detectar formato YouTube SubViewer (.sbv):
    # Formato:
    # 0:00:01.000,0:00:04.000
    # Texto da fala
    sbv_pattern = re.compile(
        r'(?:^|\n)(\d{1,2}:\d{2}:\d{2}[\.,]\d{1,3})\s*,\s*(\d{1,2}:\d{2}:\d{2}[\.,]\d{1,3})\n'
        r'([\s\S]*?)(?=\n\s*\n\d{1,2}:\d{2}:\d{2}[\.,]\d{1,3}|\n\s*\n?$|\Z)',
        re.MULTILINE
    )
    sbv_matches = list(sbv_pattern.finditer(content))
    if sbv_matches and "-->" not in content[:300]:
        for idx, match in enumerate(sbv_matches, start=1):
            start_str = match.group(1)
            end_str = match.group(2)
            raw_text = match.group(3).strip()
            clean_text = _clean_subtitle_text(raw_text)
            if clean_text:
                items.append(SubtitleItem(
                    index=idx,
                    start_seconds=time_to_seconds(start_str),
                    end_seconds=time_to_seconds(end_str),
                    text=clean_text
                ))
        items.sort(key=lambda x: x.start_seconds)
        return items

    # 2. Formatos com setas '-->' (SRT e WebVTT):
    # Suporta timestamps completos HH:MM:SS.mmm ou curtos MM:SS.mmm
    # Também ignora cabeçalho WEBVTT e metadados de alinhamento na linha do timestamp
    arrow_pattern = re.compile(
        r'(?:^|\n)(?:(\d+)\n)?'  # Índice opcional (SRT tem, VTT pode não ter)
        r'((?:\d{1,2}:)?\d{2}:\d{2}[,\.]\d{1,3})\s*-->\s*((?:\d{1,2}:)?\d{2}:\d{2}[,\.]\d{1,3})[^\n]*\n'
        r'([\s\S]*?)(?=\n\s*\n(?:(?:\d+\n)?(?:\d{1,2}:)?\d{2}:\d{2}[,\.]\d{1,3}\s*-->|\s*$)|\Z)',
        re.MULTILINE
    )

    matches = list(arrow_pattern.finditer(content))
    for idx, match in enumerate(matches, start=1):
        custom_idx = match.group(1)
        start_str = match.group(2)
        end_str = match.group(3)
        raw_text = match.group(4).strip()

        # Ignorar blocos de comentários NOTE do WebVTT
        if raw_text.startswith("NOTE"):
            continue

        clean_text = _clean_subtitle_text(raw_text)
        if not clean_text:
            continue

        start_sec = time_to_seconds(start_str)
        end_sec = time_to_seconds(end_str)
        item_index = int(custom_idx) if (custom_idx and custom_idx.isdigit()) else idx

        items.append(SubtitleItem(
            index=item_index,
            start_seconds=start_sec,
            end_seconds=end_sec,
            text=clean_text
        ))

    items.sort(key=lambda x: x.start_seconds)
    # Reindexar sequencialmente
    for i, it in enumerate(items, start=1):
        it.index = i

    return items


# Alias para compatibilidade total com código existente
parse_srt = parse_subtitles


def export_to_srt(items: List[SubtitleItem]) -> str:
    """
    Exporta uma lista de SubtitleItem para string formatada no padrão SRT oficial.
    Permite baixar/exportar legendas geradas automaticamente ou convertidas de VTT/SBV.
    """
    blocks = []
    for idx, item in enumerate(items, start=1):
        start_t = seconds_to_srt_time(item.start_seconds)
        end_t = seconds_to_srt_time(item.end_seconds)
        blocks.append(f"{idx}\n{start_t} --> {end_t}\n{item.text.strip()}\n")
    return "\n".join(blocks)


def group_subtitles(items: List[SubtitleItem], max_gap_seconds: float = 1.5, max_duration_seconds: float = 15.0) -> List[SubtitleItem]:
    """
    Agrupa itens de legenda próximos no tempo para evitar excesso de fragmentos
    quando o locutor faz pequenas pausas, mantendo a coesão do passo a passo.
    """
    if not items:
        return []

    grouped: List[SubtitleItem] = []
    current_item = SubtitleItem(
        index=items[0].index,
        start_seconds=items[0].start_seconds,
        end_seconds=items[0].end_seconds,
        text=items[0].text
    )

    for next_item in items[1:]:
        gap = next_item.start_seconds - current_item.end_seconds
        total_duration = next_item.end_seconds - current_item.start_seconds

        if 0 <= gap <= max_gap_seconds and total_duration <= max_duration_seconds:
            # Agrupar texto
            combined_text = f"{current_item.text} {next_item.text}".strip()
            current_item.end_seconds = next_item.end_seconds
            current_item.text = combined_text
        else:
            grouped.append(current_item)
            current_item = SubtitleItem(
                index=len(grouped) + 1,
                start_seconds=next_item.start_seconds,
                end_seconds=next_item.end_seconds,
                text=next_item.text
            )

    grouped.append(current_item)
    for i, it in enumerate(grouped, start=1):
        it.index = i
    return grouped

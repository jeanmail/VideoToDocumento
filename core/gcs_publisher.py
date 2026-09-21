"""
Módulo de exportação e publicação para Google Cloud Storage (GCS)
organizado por projetos de produtos para ingestão no Vertex AI Agent Builder.
"""

import os
import shutil
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass

from core.video_processor import ExtractedFrame
from core.srt_parser import SubtitleItem, export_to_srt

# Mapeamento dos 7 produtos corporativos
SUPPORTED_PROJECTS: Dict[str, str] = {
    "prescricao-digital": "Prescrição Digital",
    "automation": "Automation",
    "onetouch": "OneTouch",
    "personal": "Personal",
    "clinic": "Clinic",
    "monitoring": "Monitoring",
    "agenda-online": "Agenda Online",
}


@dataclass
class PublishResult:
    success: bool
    project_slug: str
    project_name: str
    bucket_name: str
    gcs_prefix: str
    uploaded_files: List[str]
    markdown_content: str
    message: str


def slugify_training_name(name: str) -> str:
    """
    Converte um nome de treinamento legível para um slug URL-safe.

    Exemplo:
        "Receita Digital v2 - Outubro 2025" -> "receita-digital-v2-outubro-2025"

    Se o nome for vazio, gera automaticamente com timestamp: "20251001-143000".
    """
    import re
    import unicodedata
    from datetime import datetime

    if not name or not name.strip():
        return datetime.now().strftime("%Y%m%d-%H%M%S")

    # Normaliza unicode (remove acentos)
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = nfkd.encode("ascii", errors="ignore").decode("ascii")

    # Lowercase, substitui espaços/underscores/pontos/traços por hífen único
    slug = ascii_str.lower()
    slug = re.sub(r"[\s_./\\]+", "-", slug)
    # Remove caracteres não alfanuméricos exceto hífen
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    # Colapsa múltiplos hifens
    slug = re.sub(r"-{2,}", "-", slug)
    # Remove hifens nas bordas
    slug = slug.strip("-")

    return slug or datetime.now().strftime("%Y%m%d-%H%M%S")


class GCSPublisher:
    def __init__(self, default_bucket: str = "kb-contact-center-vertex"):
        self.default_bucket = default_bucket

    @staticmethod
    def get_supported_projects() -> Dict[str, str]:
        """Retorna os produtos disponíveis."""
        return SUPPORTED_PROJECTS

    def generate_multimodal_markdown(
        self,
        project_slug: str,
        title: str,
        approved_frames: List[ExtractedFrame],
        all_subtitles: Optional[List[SubtitleItem]] = None,
        bucket_name: Optional[str] = None,
        training_slug: Optional[str] = None,
    ) -> str:
        """
        Gera o documento Markdown estruturado para o Vertex AI Agent Builder.
        Embute as URLs diretas do GCS para cada print, permitindo que a IA
        retorne texto acompanhado de imagens de tela no chat do cliente.

        Estrutura de URL: https://storage.googleapis.com/<bucket>/<project>/<training>/prints/<arquivo>
        """
        bucket = bucket_name or self.default_bucket
        project_name = SUPPORTED_PROJECTS.get(project_slug, project_slug)

        # Monta URL base respeitando training_slug quando presente
        if training_slug:
            gcs_base_url = (
                f"https://storage.googleapis.com/{bucket}/{project_slug}/{training_slug}/prints"
            )
        else:
            gcs_base_url = f"https://storage.googleapis.com/{bucket}/{project_slug}/prints"

        training_info = f" / {training_slug}" if training_slug else ""
        md_lines = [
            f"# Base de Conhecimento: {project_name}",
            f"## Documento: {title}{training_info}",
            "",
            "> Este documento é uma fonte de instrução passo a passo para o agente de IA de atendimento.",
            "> Ao responder ao usuário, forneça a instrução textual acompanhada da imagem da tela correspondente.",
            "",
            "---",
            ""
        ]

        # Linha do tempo intercalada
        if all_subtitles:
            pending_frames = sorted(approved_frames, key=lambda x: x.timestamp_seconds)
            sorted_subs = sorted(all_subtitles, key=lambda x: x.start_seconds)
            step_num = 0

            for sub in sorted_subs:
                # Se houver frame anterior a esta fala
                while pending_frames and pending_frames[0].timestamp_seconds < sub.start_seconds:
                    frame = pending_frames.pop(0)
                    step_num += 1
                    step_title = frame.step_title if frame.step_title else f"Passo {step_num}"
                    img_filename = os.path.basename(frame.image_path)
                    img_url = f"{gcs_base_url}/{img_filename}"

                    md_lines.append(f"### [TIMESTAMP: {frame.timestamp_str}] - {step_title}")
                    md_lines.append(f"![{step_title}]({img_url})")
                    md_lines.append("")
                    if frame.subtitle_text:
                        md_lines.append(f"**Instrução:** {frame.subtitle_text}")
                    if frame.ocr_text:
                        md_lines.append(f"**Elementos na tela (OCR):** {frame.ocr_text}")
                    md_lines.append("")

                # Verifica se há frame no intervalo desta fala
                matched_frame = None
                if pending_frames and pending_frames[0].timestamp_seconds <= (sub.end_seconds + 0.5):
                    matched_frame = pending_frames.pop(0)

                if matched_frame:
                    step_num += 1
                    step_title = matched_frame.step_title if matched_frame.step_title else f"Passo {step_num}"
                    img_filename = os.path.basename(matched_frame.image_path)
                    img_url = f"{gcs_base_url}/{img_filename}"

                    md_lines.append(f"### [TIMESTAMP: {matched_frame.timestamp_str}] - {step_title}")
                    md_lines.append(f"![{step_title}]({img_url})")
                    md_lines.append("")
                    text_to_use = matched_frame.subtitle_text or sub.text
                    md_lines.append(f"**Instrução:** {text_to_use}")
                    if matched_frame.ocr_text:
                        md_lines.append(f"**Elementos na tela (OCR):** {matched_frame.ocr_text}")
                    md_lines.append("")
                else:
                    # Narração sem print associado
                    md_lines.append(f"**[{sub.start_time_str}]** {sub.text}")
                    md_lines.append("")

            # Prints restantes
            while pending_frames:
                frame = pending_frames.pop(0)
                step_num += 1
                step_title = frame.step_title if frame.step_title else f"Passo {step_num}"
                img_filename = os.path.basename(frame.image_path)
                img_url = f"{gcs_base_url}/{img_filename}"

                md_lines.append(f"### [TIMESTAMP: {frame.timestamp_str}] - {step_title}")
                md_lines.append(f"![{step_title}]({img_url})")
                md_lines.append("")
                if frame.subtitle_text:
                    md_lines.append(f"**Instrução:** {frame.subtitle_text}")
                if frame.ocr_text:
                    md_lines.append(f"**Elementos na tela (OCR):** {frame.ocr_text}")
                md_lines.append("")

        else:
            for idx, frame in enumerate(approved_frames, start=1):
                step_title = frame.step_title if frame.step_title else f"Passo {idx}"
                img_filename = os.path.basename(frame.image_path)
                img_url = f"{gcs_base_url}/{img_filename}"

                md_lines.append(f"### [TIMESTAMP: {frame.timestamp_str}] - {step_title}")
                md_lines.append(f"![{step_title}]({img_url})")
                md_lines.append("")
                if frame.subtitle_text:
                    md_lines.append(f"**Instrução:** {frame.subtitle_text}")
                if frame.ocr_text:
                    md_lines.append(f"**Elementos na tela (OCR):** {frame.ocr_text}")
                md_lines.append("")

        return "\n".join(md_lines)

    def prepare_local_package(
        self,
        project_slug: str,
        output_dir: str,
        title: str,
        approved_frames: List[ExtractedFrame],
        all_subtitles: Optional[List[SubtitleItem]] = None,
        docx_path: Optional[str] = None,
        pdf_path: Optional[str] = None,
        bucket_name: Optional[str] = None,
        training_slug: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Prepara a pasta local contendo todos os artefatos estruturados para publicação.

        Estrutura de diretório local (e chaves no GCS):
            <project_slug>/<training_slug>/prints/<arquivo>.jpg   (com training_slug)
            <project_slug>/prints/<arquivo>.jpg                   (sem training_slug, legado)

        Retorna dicionário {blob_name_no_gcs: caminho_arquivo_local}.
        """
        bucket = bucket_name or self.default_bucket

        # Define o prefixo base dependendo se há training_slug
        if training_slug:
            gcs_prefix = f"{project_slug}/{training_slug}"
        else:
            gcs_prefix = project_slug

        package_dir = os.path.join(output_dir, *gcs_prefix.split("/"))
        prints_dir = os.path.join(package_dir, "prints")
        os.makedirs(prints_dir, exist_ok=True)

        files_map: Dict[str, str] = {}

        # 1. Copiar imagens aprovadas
        for frame in approved_frames:
            if os.path.exists(frame.image_path):
                fname = os.path.basename(frame.image_path)
                dest = os.path.join(prints_dir, fname)
                shutil.copy2(frame.image_path, dest)
                files_map[f"{gcs_prefix}/prints/{fname}"] = dest

        # 2. Gerar e salvar o Markdown Multimodal
        md_content = self.generate_multimodal_markdown(
            project_slug=project_slug,
            title=title,
            approved_frames=approved_frames,
            all_subtitles=all_subtitles,
            bucket_name=bucket,
            training_slug=training_slug,
        )
        md_path = os.path.join(package_dir, "knowledge_base.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        files_map[f"{gcs_prefix}/knowledge_base.md"] = md_path

        # 3. Documento Word (se houver)
        if docx_path and os.path.exists(docx_path):
            dest_docx = os.path.join(package_dir, "guia_treinamento.docx")
            shutil.copy2(docx_path, dest_docx)
            files_map[f"{gcs_prefix}/guia_treinamento.docx"] = dest_docx

        # 4. Documento PDF (se houver)
        if pdf_path and os.path.exists(pdf_path):
            dest_pdf = os.path.join(package_dir, "guia_treinamento.pdf")
            shutil.copy2(pdf_path, dest_pdf)
            files_map[f"{gcs_prefix}/guia_treinamento.pdf"] = dest_pdf

        # 5. Legenda completa SRT (se houver)
        if all_subtitles:
            srt_content = export_to_srt(all_subtitles)
            srt_path = os.path.join(package_dir, "transcricao.srt")
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(srt_content)
            files_map[f"{gcs_prefix}/transcricao.srt"] = srt_path

        return files_map

    def publish_to_gcs(
        self,
        project_slug: str,
        local_files_map: Dict[str, str],
        bucket_name: Optional[str] = None,
        credentials_path: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        training_slug: Optional[str] = None,
    ) -> PublishResult:
        """
        Envia os arquivos preparados para o Bucket no GCS.
        """
        bucket = bucket_name or self.default_bucket
        project_name = SUPPORTED_PROJECTS.get(project_slug, project_slug)

        if training_slug:
            gcs_uri_prefix = f"gs://{bucket}/{project_slug}/{training_slug}/"
        else:
            gcs_uri_prefix = f"gs://{bucket}/{project_slug}/"

        # Chave do knowledge_base no files_map
        if training_slug:
            kb_key = f"{project_slug}/{training_slug}/knowledge_base.md"
        else:
            kb_key = f"{project_slug}/knowledge_base.md"

        try:
            from google.cloud import storage
            from google.oauth2 import service_account

            if credentials_path and os.path.exists(credentials_path):
                creds = service_account.Credentials.from_service_account_file(credentials_path)
                client = storage.Client(credentials=creds, project=creds.project_id)
            else:
                client = storage.Client()

            gcs_bucket = client.bucket(bucket)
            total = len(local_files_map)
            uploaded_list = []

            for idx, (gcs_blob_name, local_file_path) in enumerate(local_files_map.items(), start=1):
                if progress_callback:
                    progress_callback(
                        idx / float(total),
                        f"Enviando para GCS ({idx}/{total}): {os.path.basename(local_file_path)}"
                    )

                blob = gcs_bucket.blob(gcs_blob_name)
                # Content type adequado
                content_type = "text/markdown; charset=utf-8" if gcs_blob_name.endswith(".md") else None
                blob.upload_from_filename(local_file_path, content_type=content_type)
                uploaded_list.append(f"gs://{bucket}/{gcs_blob_name}")

            # Lê o markdown gerado para retorno
            md_local = local_files_map.get(kb_key, "")
            md_text = ""
            if md_local and os.path.exists(md_local):
                with open(md_local, "r", encoding="utf-8") as f:
                    md_text = f.read()

            return PublishResult(
                success=True,
                project_slug=project_slug,
                project_name=project_name,
                bucket_name=bucket,
                gcs_prefix=gcs_uri_prefix,
                uploaded_files=uploaded_list,
                markdown_content=md_text,
                message=f"Pacote multimodal publicado com sucesso em {gcs_uri_prefix} ({len(uploaded_list)} arquivos)."
            )

        except Exception as e:
            # Retorna falha informativa
            md_local = local_files_map.get(kb_key, "")
            md_text = ""
            if md_local and os.path.exists(md_local):
                with open(md_local, "r", encoding="utf-8") as f:
                    md_text = f.read()

            return PublishResult(
                success=False,
                project_slug=project_slug,
                project_name=project_name,
                bucket_name=bucket,
                gcs_prefix=gcs_uri_prefix,
                uploaded_files=[],
                markdown_content=md_text,
                message=f"Falha na comunicação com o GCS: {e}"
            )

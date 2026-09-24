"""
VideoToDocument - Aplicação Streamlit
Interface completa em 3 etapas para extração, auditoria e geração de documentos de treinamento a partir de vídeos e legendas SRT.
"""

import os
import shutil
import tempfile
import streamlit as st
from PIL import Image

from core.srt_parser import parse_subtitles, parse_srt, group_subtitles, export_to_srt
from core.video_processor import VideoProcessor, ExtractedFrame, ensure_thumbnail
from core.ocr_engine import OCREngine
from core.doc_builder import DocumentBuilder
from core.transcriber import AudioTranscriber
from core.gcs_publisher import GCSPublisher, SUPPORTED_PROJECTS, slugify_training_name

# Configurações de layout da página
st.set_page_config(
    page_title="VideoToDocument | Gerador de Guias de Treinamento",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Diretórios de trabalho
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORAGE_DIR = os.path.join(BASE_DIR, "storage")
TEMP_UPLOADS = os.path.join(STORAGE_DIR, "temp_uploads")
EXTRACTED_FRAMES = os.path.join(STORAGE_DIR, "extracted_frames")
OUTPUTS_DIR = os.path.join(STORAGE_DIR, "outputs")

for d in [TEMP_UPLOADS, EXTRACTED_FRAMES, OUTPUTS_DIR]:
    os.makedirs(d, exist_ok=True)

# Inicialização de variáveis no session_state
if "current_step" not in st.session_state:
    st.session_state.current_step = 1
if "frames" not in st.session_state:
    st.session_state.frames = []
if "video_path" not in st.session_state:
    st.session_state.video_path = None
if "video_processor" not in st.session_state:
    st.session_state.video_processor = None
if "docx_path" not in st.session_state:
    st.session_state.docx_path = None
if "pdf_path" not in st.session_state:
    st.session_state.pdf_path = None
if "audit_page" not in st.session_state:
    st.session_state.audit_page = 1
if "audit_filter" not in st.session_state:
    st.session_state.audit_filter = "all"
if "audit_per_page" not in st.session_state:
    st.session_state.audit_per_page = 12
if "audit_cols" not in st.session_state:
    st.session_state.audit_cols = 3
if "all_subtitles" not in st.session_state:
    st.session_state.all_subtitles = []
if "auto_srt_text" not in st.session_state:
    st.session_state.auto_srt_text = None
if "default_training_title" not in st.session_state:
    st.session_state.default_training_title = "Guia de Treinamento - Passo a Passo"


# Estilos visuais adicionais
st.markdown("""
<style>
    .metric-box {
        background-color: #f0f2f6;
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 12px;
    }
    .duplicate-warning, .badge-dup {
        color: #92400e;
        font-weight: 600;
        background-color: #fef3c7;
        border-radius: 4px;
        padding: 2px 7px;
        display: inline-block;
        font-size: 0.80em;
    }
    .approved-tag, .badge-ok {
        color: #166534;
        font-weight: 600;
        background-color: #dcfce7;
        border-radius: 4px;
        padding: 2px 7px;
        display: inline-block;
        font-size: 0.80em;
    }
    .badge-webcam {
        color: #991b1b;
        font-weight: 600;
        background-color: #fee2e2;
        border-radius: 4px;
        padding: 2px 7px;
        display: inline-block;
        font-size: 0.80em;
    }
</style>
""", unsafe_allow_html=True)


# Barra Lateral com status e navegação
with st.sidebar:
    st.image("https://raw.githubusercontent.com/feathericons/feather/master/icons/video.svg", width=40)
    st.title("VideoToDocument")
    st.caption("Vídeo + Legenda SRT ➔ Documento Passo a Passo para NotebookLM")
    st.divider()

    st.write("### Fluxo de Trabalho")
    steps_labels = [
        "1. Upload & Configuração",
        "2. Auditoria e Validação de Prints",
        "3. Compilação do Documento"
    ]
    for i, label in enumerate(steps_labels, start=1):
        if st.session_state.current_step == i:
            st.markdown(f"**▶ `{label}`**")
        elif st.session_state.current_step > i:
            st.markdown(f"✅ ~{label}~")
        else:
            st.markdown(f"⚪ {label}")

    st.divider()
    if st.button("🔄 Reiniciar Sessão / Novo Vídeo", use_container_width=True):
        st.session_state.current_step = 1
        st.session_state.frames = []
        st.session_state.video_path = None
        st.session_state.video_processor = None
        st.session_state.docx_path = None
        st.session_state.pdf_path = None
        st.session_state.all_subtitles = []
        st.session_state.auto_srt_text = None
        # Limpar temporários
        for folder in [TEMP_UPLOADS, EXTRACTED_FRAMES]:
            for f in os.listdir(folder):
                fp = os.path.join(folder, f)
                try:
                    if os.path.isfile(fp):
                        os.remove(fp)
                except Exception:
                    pass
        st.rerun()

    # Informações de Versão e Build no rodapé da barra lateral
    st.markdown("---")
    version_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")
    try:
        with open(version_file, "r", encoding="utf-8") as _vf:
            APP_VERSION = _vf.read().strip() or "v1.3.0"
    except Exception:
        APP_VERSION = "v1.3.0"
    st.markdown(
        f"<div style='text-align: center; color: #888888; font-size: 0.82em; padding: 6px 0;'>"
        f"<strong>Versão:</strong> <code>{APP_VERSION}</code><br>"
        f"<span style='font-size: 0.9em;'>Build: <em>main (sem OCR)</em></span>"
        f"</div>",
        unsafe_allow_html=True
    )


# ==========================================
# ETAPA 1: Upload e Pré-Processamento
# ==========================================
if st.session_state.current_step == 1:
    st.header("Etapa 1: Upload do Vídeo e Transcrição")
    st.write(
        "Carregue o vídeo do treinamento. A transcrição e a extração dos prints serão realizadas "
        "automaticamente ao avançar, filtrando telas repetidas e reuniões/webcams."
    )

    uploaded_video = st.file_uploader(
        "1. Selecione o arquivo de Vídeo",
        type=["mp4", "mkv", "mov", "avi", "webm"],
        help="Vídeo do treinamento de software ou instrução (suporta arquivos de qualquer tamanho, até 10GB)."
    )

    if uploaded_video:
        raw_name = os.path.splitext(uploaded_video.name)[0]
        clean_title = raw_name.replace("_", " ").replace("-", " ").strip()
        if st.session_state.get("_last_uploaded_name") != uploaded_video.name:
            st.session_state.default_training_title = clean_title
            st.session_state._last_uploaded_name = uploaded_video.name
        st.success(f"✓ Vídeo carregado: **{uploaded_video.name}**")

    st.markdown("### 2. Legenda / Transcrição da Fala")
    transcription_mode = st.radio(
        "Como deseja fornecer a transcrição?",
        options=["auto", "upload"],
        format_func=lambda x: "🎙️ Gerar transcrição automaticamente do vídeo (Whisper)" if x == "auto" else "📁 Enviar arquivo existente (.srt, .vtt, .sbv do YouTube)",
        horizontal=True
    )

    if transcription_mode == "upload":
        uploaded_sub = st.file_uploader(
            "Selecione o arquivo de Legenda (.srt, .vtt, .sbv)",
            type=["srt", "vtt", "sbv"],
            help="Formatos aceitos com timestamp: SubRip (.srt), WebVTT (.vtt) e YouTube SubViewer (.sbv)."
        )
        if uploaded_sub:
            sub_bytes = uploaded_sub.read()
            parsed = parse_subtitles(sub_bytes)
            if parsed:
                st.session_state.all_subtitles = parsed
                st.success(f"✓ Legenda carregada com sucesso: {len(parsed)} trechos de fala identificados.")

                ext = os.path.splitext(uploaded_sub.name)[1].lower()
                if ext in [".vtt", ".sbv"]:
                    srt_data = export_to_srt(parsed)
                    st.download_button(
                        "⬇ Baixar convertida em formato padrão (.srt)",
                        data=srt_data,
                        file_name=f"{os.path.splitext(uploaded_sub.name)[0]}.srt",
                        mime="text/plain"
                    )
            else:
                st.error("Nenhum bloco de fala válido com marcação de tempo foi encontrado no arquivo enviado.")
    else:
        st.info("⚡ **Fluxo Direto:** A transcrição via Whisper será gerada automaticamente assim que você clicar no botão abaixo para avançar para a extração dos prints.")
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            whisper_lang = st.selectbox(
                "Idioma da fala no vídeo:",
                options=["pt", "en", "auto"],
                format_func=lambda x: {"pt": "Português", "en": "Inglês", "auto": "Detectar automaticamente"}[x]
            )
        with col_m2:
            whisper_model = st.selectbox(
                "Modelo Whisper:",
                options=["base", "tiny", "small"],
                format_func=lambda x: {
                    "base": "Base (Recomendado - Rápido e Preciso)",
                    "tiny": "Tiny (Ultrarrápido)",
                    "small": "Small (Maior precisão)"
                }[x]
            )

        if st.session_state.get("all_subtitles") and st.session_state.get("auto_srt_text"):
            st.download_button(
                label="⬇ Baixar Transcrição Gerada (.srt)",
                data=st.session_state.auto_srt_text,
                file_name="transcricao_gerada.srt",
                mime="text/plain"
            )

    st.markdown("### Configurações de Extração e Sensibilidade")
    with st.expander("Ajustes Avançados de Captura e IA", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            min_interval = st.slider(
                "Intervalo mínimo entre capturas (segundos)",
                min_value=1.0, max_value=10.0, value=2.5, step=0.5,
                help="Evita capturas excessivas em falas muito frequentes."
            )
        with c2:
            sim_threshold = st.slider(
                "Sensibilidade para detecção de telas repetidas (%)",
                min_value=70, max_value=98, value=88, step=1,
                help="Percentual de semelhança visual para sugerir descarte de duplicatas."
            )
        with c3:
            enable_grouping = st.checkbox(
                "Agrupar falas curtas contínuas para os prints",
                value=True,
                help="Une blocos de legenda muito próximos para gerar títulos e capturas coesas."
            )

    can_proceed = (uploaded_video is not None)

    if can_proceed:
        if st.button("🚀 Avançar para Extração e Auditoria dos Prints", type="primary", use_container_width=True):
            if transcription_mode == "upload" and not st.session_state.get("all_subtitles"):
                st.error("Por favor, envie o arquivo de legenda (.srt, .vtt, .sbv) ou selecione a opção de transcrição automática com Whisper.")
                st.stop()

            # 1. Salva o vídeo com buffer eficiente
            with st.spinner("Gravando arquivo de vídeo temporário..."):
                video_ext = os.path.splitext(uploaded_video.name)[1]
                saved_video_path = os.path.join(TEMP_UPLOADS, f"input_video{video_ext}")
                uploaded_video.seek(0)
                with open(saved_video_path, "wb") as f:
                    shutil.copyfileobj(uploaded_video, f, length=16 * 1024 * 1024)
                st.session_state.video_path = saved_video_path

            # 2. Transcrição automática se modo 'auto'
            if transcription_mode == "auto":
                trans_bar = st.progress(0, text="Iniciando motor Whisper para extração da fala...")
                transcriber = AudioTranscriber(model_size=whisper_model)

                def update_trans_progress(p, txt):
                    trans_bar.progress(p, text=txt)

                with st.spinner("Extraindo áudio do vídeo e transcrevendo com Whisper..."):
                    try:
                        gen_subs = transcriber.transcribe(
                            saved_video_path,
                            language=whisper_lang,
                            progress_callback=update_trans_progress
                        )
                        if gen_subs:
                            st.session_state.all_subtitles = gen_subs
                            st.session_state.auto_srt_text = export_to_srt(gen_subs)
                        else:
                            st.error("Não foram detectados trechos de fala audíveis no vídeo para sincronizar com os prints.")
                            st.stop()
                    except Exception as e:
                        st.error(f"Erro durante a transcrição Whisper: {e}")
                        st.stop()
                    finally:
                        trans_bar.empty()

            # 3. Extração e Análise dos Frames
            with st.spinner("Inicializando processamento e análise dos frames..."):
                processor = VideoProcessor(saved_video_path)
                st.session_state.video_processor = processor

                subtitles_for_frames = list(st.session_state.all_subtitles)
                if enable_grouping:
                    subtitles_for_frames = group_subtitles(subtitles_for_frames, max_gap_seconds=1.5, max_duration_seconds=15.0)

            prog_bar = st.progress(0, text="Extraindo e analisando telas de sistema...")

            # Processamento e extração com detecção automática de câmeras/webcams e duplicadas
            extracted_frames = processor.process_subtitles(
                subtitles=subtitles_for_frames,
                output_dir=EXTRACTED_FRAMES,
                min_interval_seconds=min_interval,
                similarity_threshold=sim_threshold / 100.0
            )

            prog_bar.empty()
            st.session_state.frames = extracted_frames
            st.session_state.audit_page = 1
            st.session_state.current_step = 2
            st.rerun()
    else:
        st.info("👈 Por favor, selecione um arquivo de vídeo acima para prosseguir.")


# ==========================================
# ETAPA 2: Painel de Auditoria e Validação
# ==========================================
elif st.session_state.current_step == 2:
    st.header("Etapa 2: Painel de Auditoria e Validação dos Prints")
    st.info(
        "💡 **Curadoria Visual em Grid:** Prints repetidos e telas contendo apenas pessoas/câmeras sem interface "
        "de software foram desmarcados automaticamente. Revise e valide os passos antes da compilação final."
    )

    frames = st.session_state.frames
    total_frames = len(frames)
    duplicates_count = sum(1 for f in frames if f.is_duplicate_candidate)
    non_system_count = sum(1 for f in frames if getattr(f, "is_non_system_candidate", False))
    approved_count = sum(1 for f in frames if f.selected)
    rejected_count = total_frames - approved_count

    # Callbacks rápidos de sincronização direta
    def on_toggle_chk(frame_id):
        k = f"chk_sel_{frame_id}"
        if k in st.session_state:
            for f in st.session_state.frames:
                if f.id == frame_id:
                    f.selected = st.session_state[k]
                    break

    def on_change_title(frame_id):
        k = f"title_{frame_id}"
        if k in st.session_state:
            for f in st.session_state.frames:
                if f.id == frame_id:
                    f.step_title = st.session_state[k]
                    break

    def on_change_text(frame_id):
        k = f"text_{frame_id}"
        if k in st.session_state:
            for f in st.session_state.frames:
                if f.id == frame_id:
                    f.subtitle_text = st.session_state[k]
                    break

    # Barra superior de métricas
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total de Prints", total_frames)
    m2.metric("Aprovados (Sistema)", approved_count)
    m3.metric("Descartados", rejected_count)
    m4.metric("Telas Repetidas", duplicates_count)
    m5.metric("Câmeras / Pessoas", non_system_count)

    st.markdown("---")

    # Controles de Filtro e Ações em Massa
    f_col1, f_col2 = st.columns([1.6, 2.4])

    with f_col1:
        filter_choices = {
            "all": f"Todos ({total_frames})",
            "approved": f"Aprovados ({approved_count})",
            "rejected": f"Descartados ({rejected_count})",
            "duplicates": f"Repetidas ({duplicates_count})",
            "non_system": f"Câmeras/Pessoas ({non_system_count})"
        }
        selected_filter_key = st.radio(
            "Filtrar exibição:",
            options=list(filter_choices.keys()),
            format_func=lambda x: filter_choices[x],
            horizontal=True,
            index=0
        )

    with f_col2:
        st.write("**Ações Rápidas em Lote:**")
        b1, b2, b3, b4 = st.columns(4)
        with b1:
            if st.button("Desmarcar Câmeras", use_container_width=True, help="Desmarca todas as telas identificadas com pessoas/reunião"):
                for f in frames:
                    if getattr(f, "is_non_system_candidate", False):
                        f.selected = False
                        st.session_state[f"chk_sel_{f.id}"] = False
                st.rerun()
        with b2:
            if st.button("Limpar Repetidas", use_container_width=True, help="Desmarca todas as telas com alta similaridade"):
                for f in frames:
                    if f.is_duplicate_candidate:
                        f.selected = False
                        st.session_state[f"chk_sel_{f.id}"] = False
                st.rerun()
        with b3:
            if st.button("Aprovar Todos", use_container_width=True):
                for f in frames:
                    f.selected = True
                    st.session_state[f"chk_sel_{f.id}"] = True
                st.rerun()
        with b4:
            if st.button("Desmarcar Todos", use_container_width=True):
                for f in frames:
                    f.selected = False
                    st.session_state[f"chk_sel_{f.id}"] = False
                st.rerun()

    # Controles de Visualização: Colunas e Paginação
    c_lay1, c_lay2 = st.columns([2, 1])
    with c_lay1:
        num_cols = st.radio(
            "Visualização em Grid:",
            options=[3, 4],
            format_func=lambda x: f"Grid de {x} colunas",
            horizontal=True,
            index=0
        )
    with c_lay2:
        per_page_choice = st.selectbox(
            "Prints por página:",
            options=[12, 24, 36, 48, "Todos"],
            index=0
        )

    # Filtragem dos frames
    if selected_filter_key == "approved":
        filtered_frames = [f for f in frames if f.selected]
    elif selected_filter_key == "rejected":
        filtered_frames = [f for f in frames if not f.selected]
    elif selected_filter_key == "duplicates":
        filtered_frames = [f for f in frames if f.is_duplicate_candidate]
    elif selected_filter_key == "non_system":
        filtered_frames = [f for f in frames if getattr(f, "is_non_system_candidate", False)]
    else:
        filtered_frames = frames

    total_filtered = len(filtered_frames)

    # Configuração da Paginação
    if per_page_choice == "Todos":
        per_page = max(1, total_filtered)
    else:
        per_page = int(per_page_choice)

    total_pages = max(1, (total_filtered + per_page - 1) // per_page)
    if st.session_state.audit_page > total_pages:
        st.session_state.audit_page = 1
    current_page = st.session_state.audit_page

    start_idx = (current_page - 1) * per_page
    end_idx = min(start_idx + per_page, total_filtered)
    page_items = filtered_frames[start_idx:end_idx]

    # Barra de Paginação Superior
    p_col1, p_col2, p_col3 = st.columns([1, 2, 1])
    with p_col1:
        if st.button("◀ Anterior", disabled=(current_page <= 1), use_container_width=True, key="btn_prev_top"):
            st.session_state.audit_page = current_page - 1
            st.rerun()
    with p_col2:
        st.markdown(
            f"<div style='text-align:center; padding-top:6px; font-weight:600; color:#333;'>"
            f"Página {current_page} de {total_pages} (Exibindo {start_idx + 1}-{end_idx} de {total_filtered})"
            f"</div>",
            unsafe_allow_html=True
        )
    with p_col3:
        if st.button("Próxima ▶", disabled=(current_page >= total_pages), use_container_width=True, key="btn_next_top"):
            st.session_state.audit_page = current_page + 1
            st.rerun()

    st.divider()

    # Renderização da grade rápida e fluida em Grid (3 ou 4 colunas)
    processor: VideoProcessor = st.session_state.video_processor

    if not page_items:
        st.info("Nenhum print corresponde ao filtro selecionado.")
    else:
        for row_idx in range(0, len(page_items), num_cols):
            row_items = page_items[row_idx:row_idx + num_cols]
            cols = st.columns(num_cols)
            for col_idx, frame in enumerate(row_items):
                global_idx = frames.index(frame) + 1
                with cols[col_idx]:
                    with st.container(border=True):
                        # Topo do card: Checkbox + Timestamp
                        c_t1, c_t2 = st.columns([1.5, 1.2])
                        with c_t1:
                            st.checkbox(
                                f"**Passo #{global_idx}**",
                                value=frame.selected,
                                key=f"chk_sel_{frame.id}",
                                on_change=on_toggle_chk,
                                args=(frame.id,),
                                help="Marcar para incluir este passo no documento"
                            )
                        with c_t2:
                            st.caption(f"⏱ `{frame.timestamp_str}`")

                        # Badges de status
                        if getattr(frame, "is_non_system_candidate", False):
                            st.markdown(
                                f'<span class="badge-webcam" title="{getattr(frame, "non_system_reason", "Câmera ou tela sem software detectada")}">👤 Câmera/Pessoas</span>',
                                unsafe_allow_html=True
                            )
                        elif frame.is_duplicate_candidate:
                            st.markdown(
                                f'<span class="badge-dup" title="Similaridade de {int(frame.similarity_score * 100)}%">⚠️ Similar ({int(frame.similarity_score * 100)}%)</span>',
                                unsafe_allow_html=True
                            )
                        elif frame.selected:
                            st.markdown('<span class="badge-ok">✓ Tela Aprovada</span>', unsafe_allow_html=True)

                        # Miniatura leve e compacta
                        thumb_path = ensure_thumbnail(frame.image_path, max_width=480)
                        img_to_show = thumb_path if os.path.exists(thumb_path) else frame.image_path
                        if os.path.exists(img_to_show):
                            st.image(img_to_show, use_container_width=True)
                        else:
                            st.warning("Imagem não encontrada.")

                        # Título do Passo compacto
                        st.text_input(
                            "Título do Passo:",
                            value=frame.step_title or f"Passo {global_idx}",
                            key=f"title_{frame.id}",
                            label_visibility="collapsed",
                            on_change=on_change_title,
                            args=(frame.id,),
                            placeholder=f"Passo {global_idx}"
                        )

                        # Popover compacto para ajuste de tempo e edição da fala
                        with st.popover("⚙️ Ajustar tempo / fala", use_container_width=True):
                            st.markdown("**Ajuste fino de tempo no vídeo:**")
                            c_m1, c_m05, c_p05, c_p1 = st.columns(4)
                            with c_m1:
                                if st.button("⏪ -1s", key=f"adj_m1_{frame.id}"):
                                    new_t = max(0.0, frame.timestamp_seconds - 1.0)
                                    if processor.refresh_frame_image(frame, new_t, EXTRACTED_FRAMES):
                                        st.rerun()
                            with c_m05:
                                if st.button("◀ -0.5s", key=f"adj_m05_{frame.id}"):
                                    new_t = max(0.0, frame.timestamp_seconds - 0.5)
                                    if processor.refresh_frame_image(frame, new_t, EXTRACTED_FRAMES):
                                        st.rerun()
                            with c_p05:
                                if st.button("+0.5s ▶", key=f"adj_p05_{frame.id}"):
                                    new_t = frame.timestamp_seconds + 0.5
                                    if processor.refresh_frame_image(frame, new_t, EXTRACTED_FRAMES):
                                        st.rerun()
                            with c_p1:
                                if st.button("+1s ⏩", key=f"adj_p1_{frame.id}"):
                                    new_t = frame.timestamp_seconds + 1.0
                                    if processor.refresh_frame_image(frame, new_t, EXTRACTED_FRAMES):
                                        st.rerun()

                            st.text_area(
                                "Transcrição da Fala:",
                                value=frame.subtitle_text,
                                height=70,
                                key=f"text_{frame.id}",
                                on_change=on_change_text,
                                args=(frame.id,)
                            )

                            if getattr(frame, "non_system_reason", ""):
                                st.caption(f"ℹ️ {frame.non_system_reason}")
                            if frame.ocr_text:
                                st.caption(f"🔍 OCR: {frame.ocr_text}")

    # Paginação Inferior
    if total_pages > 1:
        st.markdown("")
        b_col1, b_col2, b_col3 = st.columns([1, 2, 1])
        with b_col1:
            if st.button("◀ Página Anterior", disabled=(current_page <= 1), use_container_width=True, key="btn_prev_bottom"):
                st.session_state.audit_page = current_page - 1
                st.rerun()
        with b_col2:
            st.markdown(
                f"<div style='text-align:center; padding-top:6px; color:#555;'>Página {current_page} de {total_pages}</div>",
                unsafe_allow_html=True
            )
        with b_col3:
            if st.button("Próxima Página ▶", disabled=(current_page >= total_pages), use_container_width=True, key="btn_next_bottom"):
                st.session_state.audit_page = current_page + 1
                st.rerun()

    st.divider()

    # Botões de Navegação entre Etapas
    nav_c1, nav_c2 = st.columns([1, 1])
    with nav_c1:
        if st.button("⬅ Voltar para Upload", use_container_width=True):
            st.session_state.current_step = 1
            st.rerun()
    with nav_c2:
        if st.button("Avançar para Compilação Final ➔", type="primary", use_container_width=True):
            valid_approved = sum(1 for f in frames if f.selected)
            if valid_approved == 0:
                st.warning("Selecione pelo menos um print aprovado para avançar.")
            else:
                st.session_state.current_step = 3
                st.rerun()


# ==========================================
# ETAPA 3: Compilação do Documento Final
# ==========================================
elif st.session_state.current_step == 3:
    st.header("Etapa 3: Geração do Documento Final")
    st.write("Revise os detalhes da exportação e gere os documentos estruturados prontos para leitura humana e ingestão pelo **NotebookLM**.")

    approved_frames = [f for f in st.session_state.frames if f.selected]
    all_subs = st.session_state.get("all_subtitles", [])

    st.success(f"🎉 **{len(approved_frames)} passos aprovados** para inclusão visual no documento.")
    
    if all_subs:
        st.info(
            f"📖 **Documento Integral Consolidado:** 100% da transcrição ({len(all_subs)} blocos de fala) "
            f"será mantida no documento, intercalando os prints aprovados exatamente nos momentos correspondentes."
        )

    doc_col1, doc_col2 = st.columns(2)
    with doc_col1:
        default_title = st.session_state.get("default_training_title", "Guia de Treinamento - Passo a Passo")
        doc_title = st.text_input("Título do Documento:", value=default_title)
    with doc_col2:
        doc_subtitle = st.text_input("Subtítulo / Contexto:", value="Documentação integral gerada automaticamente pelo VideoToDocument")

    clean_file_base = "".join(c for c in doc_title if c.isalnum() or c in (' ', '_', '-')).strip()
    clean_file_base = clean_file_base.replace(' ', '_') or "guia_treinamento"

    st.divider()

    comp_c1, comp_c2 = st.columns(2)

    with comp_c1:
        st.markdown("### 📄 Arquivo Word (.docx)")
        st.write("Ideal para edição posterior e compatível com ingestão direta no NotebookLM com imagens e cabeçalhos claros.")
        if st.button("Gerar DOCX", type="primary", use_container_width=True):
            with st.spinner("Construindo documento integral .docx..."):
                builder = DocumentBuilder(title=doc_title, subtitle=doc_subtitle)
                docx_output = os.path.join(OUTPUTS_DIR, f"{clean_file_base}.docx")
                builder.build_docx(approved_frames, docx_output, all_subtitles=all_subs)
                st.session_state.docx_path = docx_output
                st.toast("DOCX integral gerado com sucesso!")

        if st.session_state.docx_path and os.path.exists(st.session_state.docx_path):
            with open(st.session_state.docx_path, "rb") as f:
                st.download_button(
                    label="⬇ Baixar Documento Word (.docx)",
                    data=f.read(),
                    file_name=f"{clean_file_base}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True
                )

    with comp_c2:
        st.markdown("### 📕 Arquivo PDF (.pdf)")
        st.write("Visualização portátil formatada com estilos limpos e alinhamento das imagens e textos.")
        if st.button("Gerar PDF", type="primary", use_container_width=True):
            with st.spinner("Construindo documento integral PDF..."):
                builder = DocumentBuilder(title=doc_title, subtitle=doc_subtitle)
                pdf_output = os.path.join(OUTPUTS_DIR, f"{clean_file_base}.pdf")
                builder.build_pdf(approved_frames, pdf_output, all_subtitles=all_subs)
                st.session_state.pdf_path = pdf_output
                st.toast("PDF integral gerado com sucesso!")

        if st.session_state.pdf_path and os.path.exists(st.session_state.pdf_path):
            with open(st.session_state.pdf_path, "rb") as f:
                st.download_button(
                    label="⬇ Baixar Documento PDF (.pdf)",
                    data=f.read(),
                    file_name=f"{clean_file_base}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )

    if all_subs:
        st.markdown("---")
        st.write("### 🎬 Transcrição em Formato SRT")
        srt_full_data = export_to_srt(all_subs)
        st.download_button(
            label="⬇ Baixar Transcrição Completa (.srt)",
            data=srt_full_data,
            file_name=f"{clean_file_base}.srt",
            mime="text/plain",
            use_container_width=True
        )

    # ==========================================
    # PUBLICAÇÃO NO GCS POR PROJETO DE PRODUTO
    # ==========================================
    st.markdown("---")
    st.markdown("### 🚀 Publicação na Base de Conhecimento do Produto (GCS / Vertex AI)")
    st.write(
        "Publique a base de conhecimento estruturada diretamente no bucket do Google Cloud Storage "
        "correspondente ao produto selecionado, pronta para alimentar o agente de IA do Contact Center."
    )

    proj_col1, proj_col2 = st.columns(2)
    with proj_col1:
        selected_project_slug = st.selectbox(
            "Selecione o Projeto / Produto de Destino:",
            options=list(SUPPORTED_PROJECTS.keys()),
            format_func=lambda x: f"📦 {SUPPORTED_PROJECTS[x]}"
        )
    with proj_col2:
        gcs_bucket_name = st.text_input(
            "Nome do Bucket no GCS:",
            value=st.session_state.get("gcs_bucket_name", "kb-contact-center"),
            help="Bucket do Google Cloud Storage que armazena os arquivos da base de conhecimento."
        )
        st.session_state.gcs_bucket_name = gcs_bucket_name

    # Campo de nome do treinamento (subpasta por envio)
    training_name_input = st.text_input(
        "Nome do Treinamento / Versão:",
        value=st.session_state.get("training_name", st.session_state.get("default_training_title", "")),
        placeholder="Ex: Onboarding Receita Digital - Set 2025",
        help=(
            "Identifica este envio dentro do produto. "
            "Cada nome vira uma subpasta isolada no GCS, permitindo acumular vários treinamentos. "
            "Deixe em branco para gerar nome automático com data e hora."
        )
    )
    st.session_state.training_name = training_name_input

    training_slug = slugify_training_name(training_name_input)
    st.caption(
        f"📁 Subpasta GCS: `gs://{gcs_bucket_name}/{selected_project_slug}/{training_slug}/`"
    )

    with st.expander("🔑 Credenciais do Google Cloud (Opcional se já autenticado via gcloud / ADC)", expanded=False):
        gcs_cred_file = st.text_input(
            "Caminho do arquivo JSON da Service Account:",
            value=st.session_state.get("gcs_cred_path", ""),
            help="Exemplo: C:\\keys\\minha-service-account.json"
        )
        st.session_state.gcs_cred_path = gcs_cred_file

    pub_c1, pub_c2 = st.columns(2)
    publisher = GCSPublisher(default_bucket=gcs_bucket_name)

    with pub_c1:
        if st.button("☁️ Publicar no GCS do Produto", type="primary", use_container_width=True):
            with st.spinner(
                f"Compilando pacote e enviando para "
                f"gs://{gcs_bucket_name}/{selected_project_slug}/{training_slug}/..."
            ):
                # Garante que docx e pdf estão gerados
                builder = DocumentBuilder(title=doc_title, subtitle=doc_subtitle)
                docx_output = os.path.join(OUTPUTS_DIR, f"{clean_file_base}.docx")
                pdf_output = os.path.join(OUTPUTS_DIR, f"{clean_file_base}.pdf")
                builder.build_docx(approved_frames, docx_output, all_subtitles=all_subs)
                builder.build_pdf(approved_frames, pdf_output, all_subtitles=all_subs)

                # 1. Prepara pasta local organizada por training_slug
                package_files = publisher.prepare_local_package(
                    project_slug=selected_project_slug,
                    output_dir=OUTPUTS_DIR,
                    title=doc_title,
                    approved_frames=approved_frames,
                    all_subtitles=all_subs,
                    docx_path=docx_output,
                    pdf_path=pdf_output,
                    bucket_name=gcs_bucket_name,
                    training_slug=training_slug,
                )

                # 2. Publica no GCS
                result = publisher.publish_to_gcs(
                    project_slug=selected_project_slug,
                    local_files_map=package_files,
                    bucket_name=gcs_bucket_name,
                    credentials_path=gcs_cred_file if gcs_cred_file else None,
                    training_slug=training_slug,
                )

                if result.success:
                    st.success(f"🎉 {result.message}")
                    st.info(f"📂 **Caminho para o Vertex AI Datastore:** `{result.gcs_prefix}`")
                else:
                    st.warning(f"⚠️ {result.message}")
                    st.info(
                        f"💡 O pacote completo foi organizado localmente em: "
                        f"`storage/outputs/{selected_project_slug}/{training_slug}/` "
                        f"com todos os prints e `knowledge_base.md`."
                    )

    with pub_c2:
        preview_md = publisher.generate_multimodal_markdown(
            project_slug=selected_project_slug,
            title=doc_title,
            approved_frames=approved_frames,
            all_subtitles=all_subs,
            bucket_name=gcs_bucket_name,
            training_slug=training_slug,
        )
        st.download_button(
            label="⬇ Baixar knowledge_base.md (Multimodal)",
            data=preview_md,
            file_name=f"knowledge_base_{selected_project_slug}_{training_slug}.md",
            mime="text/markdown",
            use_container_width=True
        )

    with st.expander("👁️ Ver Prévia do knowledge_base.md (com URLs de imagens para o Vertex AI)", expanded=False):
        st.code(preview_md, language="markdown")

    st.divider()
    if st.button("⬅ Voltar ao Painel de Auditoria"):
        st.session_state.current_step = 2
        st.rerun()

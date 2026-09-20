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
from core.gcs_publisher import GCSPublisher, SUPPORTED_PROJECTS

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
    st.session_state.audit_filter = "Todos"
if "audit_per_page" not in st.session_state:
    st.session_state.audit_per_page = 8
if "all_subtitles" not in st.session_state:
    st.session_state.all_subtitles = []
if "auto_srt_text" not in st.session_state:
    st.session_state.auto_srt_text = None


# Estilos visuais adicionais
st.markdown("""
<style>
    .metric-box {
        background-color: #f0f2f6;
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 12px;
    }
    .duplicate-warning {
        color: #b91c1c;
        font-weight: 600;
        background-color: #fee2e2;
        border-radius: 6px;
        padding: 4px 8px;
        display: inline-block;
        font-size: 0.85em;
    }
    .approved-tag {
        color: #15803d;
        font-weight: 600;
        background-color: #dcfce7;
        border-radius: 6px;
        padding: 4px 8px;
        display: inline-block;
        font-size: 0.85em;
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


# ==========================================
# ETAPA 1: Upload e Pré-Processamento
# ==========================================
if st.session_state.current_step == 1:
    st.header("Etapa 1: Upload do Vídeo e Transcrição")
    st.write(
        "Carregue o vídeo do treinamento e envie a legenda ou gere a transcrição automaticamente "
        "com reconhecimento de fala (Whisper) antes de iniciar a extração e auditoria dos prints."
    )

    uploaded_video = st.file_uploader(
        "1. Selecione o arquivo de Vídeo",
        type=["mp4", "mkv", "mov", "avi", "webm"],
        help="Vídeo do treinamento de software ou instrução."
    )

    st.markdown("### 2. Legenda / Transcrição da Fala")
    transcription_mode = st.radio(
        "Como deseja fornecer a transcrição?",
        options=["upload", "auto"],
        format_func=lambda x: "📁 Enviar arquivo existente (.srt, .vtt, .sbv do YouTube)" if x == "upload" else "🎙️ Gerar transcrição automaticamente do vídeo (Whisper)",
        horizontal=True
    )

    current_subtitles = []

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
                current_subtitles = parsed
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
        st.write("Gere uma legenda formatada `.srt` com timestamps precisos diretamente da faixa de áudio do vídeo.")
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

        if uploaded_video is None:
            st.warning("⚠️ Carregue o arquivo de vídeo acima antes de iniciar a transcrição automática.")
        else:
            if st.button("🎙️ Gerar Transcrição do Vídeo Agora", type="secondary"):
                video_ext = os.path.splitext(uploaded_video.name)[1]
                saved_video_path = os.path.join(TEMP_UPLOADS, f"input_video{video_ext}")
                with open(saved_video_path, "wb") as f:
                    f.write(uploaded_video.getbuffer() if hasattr(uploaded_video, 'getbuffer') else uploaded_video.read())
                st.session_state.video_path = saved_video_path

                trans_bar = st.progress(0, text="Iniciando motor Whisper...")
                transcriber = AudioTranscriber(model_size=whisper_model)

                def update_trans_progress(p, txt):
                    trans_bar.progress(p, text=txt)

                with st.spinner("Extraindo áudio e transcrevendo fala..."):
                    try:
                        gen_subs = transcriber.transcribe(
                            saved_video_path,
                            language=whisper_lang,
                            progress_callback=update_trans_progress
                        )
                        if gen_subs:
                            st.session_state.all_subtitles = gen_subs
                            st.session_state.auto_srt_text = export_to_srt(gen_subs)
                            st.success(f"✓ Transcrição concluída com sucesso! {len(gen_subs)} blocos de fala gerados.")
                        else:
                            st.error("Não foram detectados blocos de fala audíveis no vídeo.")
                    except Exception as e:
                        st.error(f"Erro durante a transcrição: {e}")

        if st.session_state.get("all_subtitles") and st.session_state.get("auto_srt_text"):
            current_subtitles = st.session_state.all_subtitles
            st.download_button(
                label="⬇ Baixar Transcrição Gerada (.srt)",
                data=st.session_state.auto_srt_text,
                file_name="transcricao_gerada.srt",
                mime="text/plain",
                type="primary"
            )

    st.markdown("### Configurações de Extração e Sensibilidade")
    with st.expander("Ajustes Avançados de Captura", expanded=False):
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

        enable_ocr = st.checkbox("Executar OCR nas telas extraídas (detecção de botões e texto)", value=False)

    ready_to_extract = (uploaded_video is not None) and (len(st.session_state.get("all_subtitles", [])) > 0)

    if ready_to_extract:
        if st.button("🚀 Iniciar Extração e Análise dos Prints", type="primary", use_container_width=True):
            with st.spinner("Salvando arquivos e inicializando processamento..."):
                video_ext = os.path.splitext(uploaded_video.name)[1]
                saved_video_path = os.path.join(TEMP_UPLOADS, f"input_video{video_ext}")
                with open(saved_video_path, "wb") as f:
                    f.write(uploaded_video.getbuffer() if hasattr(uploaded_video, 'getbuffer') else uploaded_video.read())

                st.session_state.video_path = saved_video_path
                processor = VideoProcessor(saved_video_path)
                st.session_state.video_processor = processor

                subtitles_for_frames = list(st.session_state.all_subtitles)
                if enable_grouping:
                    subtitles_for_frames = group_subtitles(subtitles_for_frames, max_gap_seconds=1.5, max_duration_seconds=15.0)

            prog_bar = st.progress(0, text="Processando frames do vídeo...")
            ocr_engine = OCREngine(enabled=enable_ocr)

            # Processamento e extração
            extracted_frames = processor.process_subtitles(
                subtitles=subtitles_for_frames,
                output_dir=EXTRACTED_FRAMES,
                min_interval_seconds=min_interval,
                similarity_threshold=sim_threshold / 100.0
            )

            # OCR opcional
            if enable_ocr:
                for idx, frame in enumerate(extracted_frames):
                    prog_bar.progress(
                        (idx + 1) / len(extracted_frames),
                        text=f"Analisando OCR no frame {idx+1}/{len(extracted_frames)}..."
                    )
                    frame.ocr_text = ocr_engine.extract_text(frame.image_path)

            prog_bar.progress(1.0, text="Extração concluída!")
            st.session_state.frames = extracted_frames
            st.session_state.current_step = 2
            st.rerun()


# ==========================================
# ETAPA 2: Painel de Auditoria e Validação
# ==========================================
elif st.session_state.current_step == 2:
    st.header("Etapa 2: Painel de Auditoria e Validação dos Prints")
    st.info(
        "💡 **Processo Fluido de Curadoria:** Revise e valide os passos antes da compilação. "
        "Prints são carregados como miniaturas otimizadas para máxima velocidade na seleção."
    )

    frames = st.session_state.frames
    total_frames = len(frames)
    duplicates_count = sum(1 for f in frames if f.is_duplicate_candidate)
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
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total de Prints", total_frames)
    m2.metric("Aprovados", approved_count)
    m3.metric("Descartados", rejected_count)
    m4.metric("Duplicatas Sugeridas", duplicates_count)

    st.markdown("---")

    # Controles de Filtro e Ações em Massa
    f_col1, f_col2 = st.columns([1.5, 2.5])

    with f_col1:
        filter_choices = {
            "all": f"Todos ({total_frames})",
            "approved": f"Aprovados ({approved_count})",
            "rejected": f"Descartados ({rejected_count})",
            "duplicates": f"Duplicados ({duplicates_count})"
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
            if st.button("Limpar Duplicados", use_container_width=True, help="Desmarca todos identificados com alta similaridade"):
                for f in frames:
                    if f.is_duplicate_candidate:
                        f.selected = False
                        st.session_state[f"chk_sel_{f.id}"] = False
                st.rerun()
        with b2:
            if st.button("Aprovar Todos", use_container_width=True):
                for f in frames:
                    f.selected = True
                    st.session_state[f"chk_sel_{f.id}"] = True
                st.rerun()
        with b3:
            if st.button("Desmarcar Todos", use_container_width=True):
                for f in frames:
                    f.selected = False
                    st.session_state[f"chk_sel_{f.id}"] = False
                st.rerun()
        with b4:
            per_page_choice = st.selectbox(
                "Prints/pág:",
                options=[6, 8, 12, 24, "Todos"],
                index=1,
                label_visibility="collapsed"
            )

    # Filtragem dos frames
    if selected_filter_key == "approved":
        filtered_frames = [f for f in frames if f.selected]
    elif selected_filter_key == "rejected":
        filtered_frames = [f for f in frames if not f.selected]
    elif selected_filter_key == "duplicates":
        filtered_frames = [f for f in frames if f.is_duplicate_candidate]
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
            f"Página {current_page} de {total_pages} (Prints {start_idx + 1}-{end_idx} de {total_filtered})"
            f"</div>",
            unsafe_allow_html=True
        )
    with p_col3:
        if st.button("Próxima ▶", disabled=(current_page >= total_pages), use_container_width=True, key="btn_next_top"):
            st.session_state.audit_page = current_page + 1
            st.rerun()

    st.divider()

    # Renderização da grade rápida e fluida de frames
    processor: VideoProcessor = st.session_state.video_processor

    if not page_items:
        st.info("Nenhum print corresponde ao filtro selecionado.")
    else:
        for idx, frame in enumerate(page_items):
            global_idx = frames.index(frame) + 1
            with st.container(border=True):
                col_img, col_info = st.columns([1.1, 1.9])

                with col_img:
                    # Carrega thumbnail leve (~20KB) ao invés da imagem 1080p completa
                    thumb_path = ensure_thumbnail(frame.image_path)
                    if os.path.exists(thumb_path):
                        st.image(thumb_path, use_container_width=True)
                    elif os.path.exists(frame.image_path):
                        st.image(frame.image_path, use_container_width=True)
                    else:
                        st.warning("Imagem não encontrada.")

                    st.caption(f"⏱ Tempo: `{frame.timestamp_str}` ({frame.timestamp_seconds:.1f}s)")

                    # Popover compacto para ajuste fino de tempo (evita desenhar 4 botões fixos no card)
                    with st.popover("⏱ Ajustar Segundo"):
                        st.caption("Ajuste se o quadro original pegou um desfoque:")
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

                with col_info:
                    # Cabeçalho do print: Checkbox direto e status
                    h_c1, h_c2 = st.columns([2, 1])
                    with h_c1:
                        st.checkbox(
                            f"**Incluir no Documento**",
                            value=frame.selected,
                            key=f"chk_sel_{frame.id}",
                            on_change=on_toggle_chk,
                            args=(frame.id,)
                        )
                    with h_c2:
                        if frame.is_duplicate_candidate:
                            st.markdown(
                                f'<span class="duplicate-warning">⚠️ Similar ({int(frame.similarity_score * 100)}%)</span>',
                                unsafe_allow_html=True
                            )
                        elif frame.selected:
                            st.markdown('<span class="approved-tag">✓ Aprovado</span>', unsafe_allow_html=True)

                    # Edição de título do passo
                    st.text_input(
                        "Título do Passo:",
                        value=frame.step_title or f"Passo {global_idx}",
                        key=f"title_{frame.id}",
                        on_change=on_change_title,
                        args=(frame.id,)
                    )

                    # Edição do texto da legenda/transcrição
                    st.text_area(
                        "Transcrição / Fala do Trecho:",
                        value=frame.subtitle_text,
                        height=75,
                        key=f"text_{frame.id}",
                        on_change=on_change_text,
                        args=(frame.id,)
                    )

                    if frame.ocr_text:
                        st.caption(f"🔍 **OCR:** {frame.ocr_text}")

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
        doc_title = st.text_input("Título do Documento:", value="Guia de Treinamento - Passo a Passo")
    with doc_col2:
        doc_subtitle = st.text_input("Subtítulo / Contexto:", value="Documentação integral gerada automaticamente pelo VideoToDocument")

    st.divider()

    comp_c1, comp_c2 = st.columns(2)

    with comp_c1:
        st.markdown("### 📄 Arquivo Word (.docx)")
        st.write("Ideal para edição posterior e compatível com ingestão direta no NotebookLM com imagens e cabeçalhos claros.")
        if st.button("Gerar DOCX", type="primary", use_container_width=True):
            with st.spinner("Construindo documento integral .docx..."):
                builder = DocumentBuilder(title=doc_title, subtitle=doc_subtitle)
                docx_output = os.path.join(OUTPUTS_DIR, "guia_treinamento.docx")
                builder.build_docx(approved_frames, docx_output, all_subtitles=all_subs)
                st.session_state.docx_path = docx_output
                st.toast("DOCX integral gerado com sucesso!")

        if st.session_state.docx_path and os.path.exists(st.session_state.docx_path):
            with open(st.session_state.docx_path, "rb") as f:
                st.download_button(
                    label="⬇ Baixar Documento Word (.docx)",
                    data=f.read(),
                    file_name="guia_treinamento.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True
                )

    with comp_c2:
        st.markdown("### 📕 Arquivo PDF (.pdf)")
        st.write("Visualização portátil formatada com estilos limpos e alinhamento das imagens e textos.")
        if st.button("Gerar PDF", type="primary", use_container_width=True):
            with st.spinner("Construindo documento integral PDF..."):
                builder = DocumentBuilder(title=doc_title, subtitle=doc_subtitle)
                pdf_output = os.path.join(OUTPUTS_DIR, "guia_treinamento.pdf")
                builder.build_pdf(approved_frames, pdf_output, all_subtitles=all_subs)
                st.session_state.pdf_path = pdf_output
                st.toast("PDF integral gerado com sucesso!")

        if st.session_state.pdf_path and os.path.exists(st.session_state.pdf_path):
            with open(st.session_state.pdf_path, "rb") as f:
                st.download_button(
                    label="⬇ Baixar Documento PDF (.pdf)",
                    data=f.read(),
                    file_name="guia_treinamento.pdf",
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
            file_name="treinamento_completo.srt",
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
            value=st.session_state.get("gcs_bucket_name", "kb-contact-center-vertex"),
            help="Bucket do Google Cloud Storage que armazena os arquivos da base de conhecimento."
        )
        st.session_state.gcs_bucket_name = gcs_bucket_name

    # Campo de nome do treinamento (subpasta por envio)
    training_name_input = st.text_input(
        "Nome do Treinamento / Versão:",
        value=st.session_state.get("training_name", ""),
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
                docx_output = os.path.join(OUTPUTS_DIR, "guia_treinamento.docx")
                pdf_output = os.path.join(OUTPUTS_DIR, "guia_treinamento.pdf")
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

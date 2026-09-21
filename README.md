# VideoToDocument 🎬➔📄

Aplicação para processamento de vídeos instrutivos/treinamentos e arquivos de legenda (`.srt`), gerando documentos estruturados (**DOCX** e **PDF**) com transcrição sincronizada e capturas de tela validadas manualmente em um painel interativo de auditoria.

Formatado especialmente para leitura humana e ingestão de alta precisão pelo **NotebookLM**.

---

## 🌟 Funcionalidades Principais

- **Upload Simples:** Suporte a vídeos (`.mp4`, `.mkv`, `.mov`, etc.) e legendas (`.srt`).
- **Extração Inteligente:** Sincronização direta dos momentos de fala para extrair o frame correspondente da interface.
- **Detecção de Redundâncias (dHash):** Compara automaticamente a similaridade visual entre telas subsequentes e marca sugestões de exclusão para telas repetidas.
- **Painel de Auditoria e Curadoria (Etapa 2):**
  - Grade interativa com timeline dos prints.
  - Seleção/descarte individual ou em lote.
  - Ajuste fino de tempo (`-1s`, `-0.5s`, `+0.5s`, `+1s`) para capturar o frame perfeito sem desfoque de transição.
  - Edição de títulos dos passos e textos da transcrição.
- **Exportação Multiformato:**
  - **DOCX (Word):** formatado com cabeçalhos semânticos `[TIMESTAMP: HH:MM:SS]` para o NotebookLM.
  - **PDF:** documento pronto para impressão e distribuição.
- **OCR Modular Opcional:** Identificação de textos e botões na tela.

---

## 🚀 Como Executar

### 1. Criar o Ambiente Virtual e Instalar Dependências

Certifique-se de que o Python 3.10+ está instalado:

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

### 2. Iniciar a Aplicação

```powershell
.\.venv\Scripts\streamlit run app.py
```

A interface abrirá automaticamente no seu navegador padrão em `http://localhost:8501`.

---

## 📁 Estrutura do Projeto

```
VideoToDocumento/
├── app.py                      # Aplicação Principal (Interface Streamlit)
├── requirements.txt            # Dependências do projeto
├── core/
│   ├── srt_parser.py           # Leitura e agrupamento de legendas .srt
│   ├── video_processor.py      # Extração de frames e análise de similaridade (dHash)
│   ├── ocr_engine.py           # Extração OCR modular
│   └── doc_builder.py          # Construtor de DOCX e PDF
├── storage/
│   ├── temp_uploads/           # Vídeos e legendas temporárias
│   ├── extracted_frames/       # Prints em processo de auditoria
│   └── outputs/                # Documentos finais gerados
└── tests/
    ├── test_srt_parser.py      # Testes do parser de SRT
    ├── test_video_processor.py # Testes da extração de frames
    └── test_doc_builder.py     # Testes da geração de DOCX e PDF
```

---

## 🧪 Executando os Testes Automatizados

Para rodar todos os testes de unidade e integração:

```powershell
.\.venv\Scripts\pytest
```

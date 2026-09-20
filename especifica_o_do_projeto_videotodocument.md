# Especificação Técnica e Arquitetura de Software

**Projeto:** VideoToDocument

**Objetivo:** Processar vídeos de treinamento e arquivos de legenda (`.srt`) para gerar um documento estruturado (DOCX/PDF) contendo transcrição sincronizada com capturas de tela (prints) validadas pelo usuário.

## 1. Visão Geral da Solução

O **VideoToDocument** é uma aplicação focada em transformar vídeos instrutivos de software em guias visuais passo a passo. O grande diferencial do sistema é o **fluxo de validação em duas etapas**, garantindo que apenas as telas realmente relevantes sejam mantidas no documento final, evitando poluição visual e redundâncias antes da ingestão pelo NotebookLM.

```
[ Upload: Vídeo + SRT ] 
          │
          ▼
   [ Etapa 1: Extração & OCR ]
          │
          ▼
  [ Etapa 2: Auditoria Manual ] ──> (Excluir/Agrupar/Editar Prints)
          │
          ▼
 [ Etapa 3: Compilação Final ] ──> (Documento DOCX/PDF pronto para NotebookLM)

```

## 2. Fluxo de Trabalho (Workflow Detalhado)

### Etapa 1: Upload e Pré-Processamento

1. **Interface de Entrada:**

   * Campo de Upload do Vídeo (`.mp4`, `.mkv`, `.mov`).

   * Campo de Upload do Arquivo de Legenda/Transcrição (`.srt`).

   * Configuração opcional de sensibilidade (ex: intervalo mínimo entre capturas em segundos, sensibilidade de mudança de tela).

2. **Processamento Inicial (Sincronização & OCR):**

   * O sistema lê o `.srt` e extrai os blocos de texto com seus respectivos *timestamps* de início e fim.

   * O motor do sistema percorre o vídeo nos momentos exatos indicados pela legenda (ou em mudanças de cena significativas).

   * **Extração Visual:** Captura do frame em resolução original.

   * **Leitura OCR (Opcional/Enriquecimento):** Opcionalmente, um motor OCR (ex: EasyOCR ou Tesseract) analisa a imagem extraída para identificar elementos da interface (botões, títulos de janelas, formulários).

### Etapa 2: Painel de Auditoria e Validação dos Prints (Requisito Chave)

Nesta fase, o documento **ainda não é gerado**. O usuário é direcionado para uma galeria interativa para curadoria.

#### Recursos do Painel de Auditoria:

* **Visualização em Grade/Linha do Tempo:** Lista de todos os prints capturados organizados por ordem cronológica com seu respectivo tempo (`HH:MM:SS`) e o trecho da legenda correspondente.

* **Exclusão de Redundâncias:** Botão para descartar frames repetidos ou irrelevantes.

* **Agrupamento de Passos:** Opção de selecionar múltiplos prints e agrupá-los em uma única seção ou "passo a passo" continuo.

* **Seleção do Frame Ideal:** Se o print capturado automaticamente pegou uma transição desfocada, o usuário pode avançar/recuar alguns quadros diretamente no painel.

* **Filtro Inteligente por OCR (Sugestão):** O sistema marca automaticamente telas com alto índice de similaridade visual para que o usuário possa deletá-las em lote.

### Etapa 3: Geração do Documento Final

Após a confirmação do usuário na auditoria:

1. O sistema compila apenas os **prints aprovados**.

2. Alinha cada print aprovado ao texto da transcrição `.srt` correspondente àquela janela de tempo.

3. Formata o conteúdo no estilo ideal para ingestão no **NotebookLM**:

   * Cabeçalhos claros com marcações de tempo (`[TIMESTAMP: 00:02:15]`).

   * Transcrição formatada.

   * Descrição textual dos elementos visuais (obtida via OCR ou descrição da tela).

   * Imagem renderizada no tamanho ideal.

4. Exporta nos formatos `.docx` e `.pdf`.

## 3. Sugestão de Arquitetura Tecnológica

Para implementar essa interface e fluxo de forma ágil e moderna (ideal para desenvolvimento com Antigravity):

### Stack Recomendada:

* **Frontend / Interface do Usuário:** **Streamlit** ou **Gradio** (Permitem criar a tela de upload, galeria de imagens interativa para auditoria e botões de ação em pouquíssimas linhas de código Python).

* **Processamento de Vídeo:** `OpenCV` (cv2) ou `FFmpeg-python`.

* **Parser de Legendas:** `pysrt` (para ler e manipular arquivos `.srt` facilmente).

* **Motor de OCR:** `EasyOCR` ou `PaddleOCR` (alta precisão para texto de interfaces gráficas/software).

* **Geração de Documentos:** `python-docx` (Word) e `reportlab` ou `weasyprint` (PDF).

## 4. Estrutura Recomendada do Projeto

```
videotodocument/
├── app.py                      # Aplicação Principal (Interface Streamlit/Gradio)
├── requirements.txt            # Dependências do projeto
├── core/
│   ├── video_processor.py      # Extração de frames e detecção de cena
│   ├── srt_parser.py           # Leitura e sincronização de legendas .srt
│   ├── ocr_engine.py           # Análise de texto visual nos prints
│   └── doc_builder.py          # Montagem do arquivo .docx/.pdf final
├── storage/
│   ├── temp_uploads/           # Vídeos e .srt temporários
│   ├── extracted_frames/       # Prints aguardando auditoria
│   └── outputs/                # Documentos finais gerados
└── README.md                   # Documentação de execução

```

## 5. Próximos Passos Recomendados

1. **Aprovação da Especificação:** Validar os pontos da interface de auditoria.

2. **Setup do Ambiente:** Criar a estrutura de diretórios e instalar as bibliotecas de processamento.

3. **Desenvolvimento do MVP:**

   * Módulo 1: Parser SRT + Extrator de Frames em tempos específicos.

   * Módulo 2: Tela simples de seleção/exclusão dos prints extraídos.

   * Módulo 3: Exportador para Word (`.docx`).
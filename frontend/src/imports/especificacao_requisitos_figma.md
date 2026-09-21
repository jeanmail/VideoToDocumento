# 📐 Especificação de Requisitos & Design Brief (User Stories)
## Projeto: VideoToDocumento (Fábrica de Guias e Bases de Conhecimento Multimodal)
**Objetivo para o Figma:** Guiar o design de UI/UX para uma aplicação web moderna, fluida e intuitiva que transforma gravações de treinamentos em documentos estruturados (DOCX, PDF, SRT) e bases de conhecimento para IAs de atendimento (Vertex AI / GCS).

---

## 🧭 Visão Geral & Personas

- **Persona Principal:** Analista de Treinamento / Suporte / Especialista de Produto (não técnico).
- **Missão:** Criar documentação rica e estruturada de sistemas corporativos em poucos cliques, sem perder tempo pausando vídeos manualmente para tirar prints e transcrever falas.
- **Tom & Estilo de UI Desejado:** Clean, moderno, profissional (SaaS B2B), paleta equilibrada com foco na produtividade, visualização rica de mídias e navegação por etapas (Stepper / Wizard).

---

## 🗺️ Fluxo de Trabalho (3 Etapas Principais)

1. **Etapa 1: Ingestão e Configuração (Upload & Transcrição)**
2. **Etapa 2: Estúdio de Curadoria e Auditoria Visual (Grid de Validação)**
3. **Etapa 3: Exportação e Publicação Multimodal (Downloads & Nuvem)**

---

## 📝 Épicos e Histórias de Usuário (User Stories)

### 📌 ÉPICO 1: Entrada de Vídeo e Transcrição da Fala

#### US01 - Upload de Vídeo e Escolha de Transcrição
> **Como** especialista de produto,  
> **Quero** carregar um vídeo de treinamento e escolher se envio uma legenda pronta ou se o sistema deve transcrever o áudio automaticamente,  
> **Para que** eu possa trabalhar tanto com vídeos já legendados (YouTube Studio) quanto com gravações brutas.

**Critérios de Aceitação (UI/UX):**
- **Área de Drag & Drop de Vídeo:** Suporte a arquivos pesados (`.mp4`, `.mkv`, `.mov`, `.webm`) com feedback visual claro de upload (barra de progresso e nome/tamanho do arquivo).
- **Seletor de Modo de Transcrição (Tabs ou Radio Cards):**
  - **Opção A:** *Enviar arquivo de legenda existente* (Dropzone secundário com suporte a `.srt`, `.vtt` e `.sbv`).
  - **Opção B:** *Gerar transcrição automaticamente via IA (Whisper)* (Seleção rápida de idioma: Português, Inglês, Auto; e nível de precisão/modelo: Rápido vs Preciso).
- **Botão de Download da Legenda Gerada:** Disponibilizar botão de download imediato da legenda `.srt` gerada pela IA caso o usuário deseje utilizá-la fora do app.

#### US02 - Ajustes de Sensibilidade e Inteligência de Captura
> **Como** usuário,  
> **Quero** ter acesso a parâmetros avançados de corte de frames de forma colapsável/expansível,  
> **Para que** a tela principal não fique poluída, mas eu possa ajustar a frequência de capturas caso o vídeo seja muito rápido ou muito longo.

**Critérios de Aceitação (UI/UX):**
- **Accordion / Expander:** Título *"Ajustes Avançados de Captura e IA"*, colapsado por padrão.
- **Controles (Sliders & Toggles):**
  - Slider de *Intervalo Mínimo entre Capturas* (1.0s a 10.0s, default 2.5s).
  - Slider de *Sensibilidade de Telas Repetidas* (70% a 98%, default 88%).
  - Toggle de *Agrupamento Inteligente de Falas Curtas* (default ativo).
- **Call-to-Action Principal (CTA):** Botão destacado e convidativo no rodapé: *"Avançar para Extração e Auditoria dos Prints ➔"*.

---

### 📌 ÉPICO 2: Estúdio de Auditoria e Curadoria Visual dos Prints

#### US03 - Visão Geral com Indicadores e Filtros Rápidos
> **Como** revisor de conteúdo,  
> **Quero** ver um resumo visual do processamento (total de telas, aprovadas, duplicadas e câmeras detectadas) e filtrar rapidamente a lista,  
> **Para que** eu possa focar apenas nas telas que exigem minha atenção.

**Critérios de Aceitação (UI/UX):**
- **Barra de Métricas (Scorecards/Pills):**
  - Total de Prints Extraídos.
  - Telas Aprovadas (verde).
  - Telas Duplicadas/Similares (amarelo/alerta).
  - Câmeras/Webcams detectadas sem tela de sistema (azul/cinza).
- **Segmented Control / Filtro Rápido:** Alternar visualização entre: `Todos`, `Apenas Aprovados`, `Telas Repetidas` e `Câmeras/Pessoas`.
- **Toolbar de Ações em Lote:** Botões rápidos: *"Desmarcar Câmeras"*, *"Limpar Repetidas"*, *"Aprovar Todos"*, *"Desmarcar Todos"*.

#### US04 - Cards de Validação de Prints (Grid Interativo)
> **Como** usuário,  
> **Quero** visualizar os prints em grade responsiva (3 ou 4 colunas) com miniaturas leves e controles diretos no card,  
> **Para que** eu possa validar, renomear passos e sincronizar o tempo com fluidez máxima sem travamento da interface.

**Critérios de Aceitação (UI/UX):**
- **Card de Print (Design Component):**
  - **Header do Card:** Checkbox com destaque para o número do passo (`Passo #X`) e badge com timestamp (`⏱ 01:25`).
  - **Badge de Contexto IA:** Etiquetas coloridas automáticas (`✓ Tela Aprovada`, `⚠️ Similar 89%`, `👤 Câmera/Webcam`).
  - **Visualização da Imagem:** Miniatura com aspecto 16:9, cantos arredondados, permitindo clique para expandir/zoom em modal.
  - **Campo de Título Editável:** Input de texto rápido para renomear o título do passo (ex: *"Acessar menu de prescrições"*).
  - **Menu Popover/Expander de Ajuste Fino:**
    - Botões rápidos de compensação de tempo: `⏪ -1s`, `◀ -0.5s`, `+0.5s ▶`, `+1s ⏩` (recarrega o frame do vídeo em tempo real se o apresentador mudou de tela antes ou depois).
    - Campo de edição da fala/instrução transcrita associada àquele momento.
- **Paginação:** Barra inferior e superior com navegação de páginas (`Anterior`, `Próxima`, indicador de página atual e seletor de quantos prints por página: 8, 12 ou 16).

---

### 📌 ÉPICO 3: Compilação de Documentos e Publicação Multimodal

#### US05 - Geração de Documentos de Treinamento (Word e PDF)
> **Como** criador de documentação,  
> **Quero** baixar o material consolidado em formatos corporativos (DOCX e PDF) mantendo a transcrição cronológica completa intercalada com os prints aprovados,  
> **Para que** os colaboradores tenham uma apostila rica e detalhada do treinamento.

**Critérios de Aceitação (UI/UX):**
- **Campos de Metadados:** Input para *Título do Documento* e *Subtítulo / Versão*.
- **Cards de Ação de Download:**
  - Card 1: **Documento Word (.docx)** com botão de gerar e baixar.
  - Card 2: **Documento PDF (.pdf)** com visualização formatada e botão de baixar.
  - Card 3: **Arquivo de Legenda Completa (.srt)** com botão de download direto.

#### US06 - Publicação na Nuvem para Agente de IA do Contact Center (GCS & Vertex AI)
> **Como** gestor de inteligência artificial / atendimento,  
> **Quero** destinar o material para a base de conhecimento de um produto específico na nuvem com identificação do treinamento,  
> **Para que** o agente virtual do Vertex AI consiga responder clientes no chat com texto e fotos das telas.

**Critérios de Aceitação (UI/UX):**
- **Seletor de Produto Corporativo (Dropdown com ícones):**
  - Opções: *Prescrição Digital*, *Automation*, *OneTouch*, *Personal*, *Clinic*, *Monitoring*, *Agenda Online*.
- **Identificação do Treinamento:**
  - Input de texto: *"Nome do Treinamento / Versão"* (ex: `Onboarding de Médicos - Set 2026`).
  - Preview visual da rota na nuvem: `gs://<bucket>/<produto>/<slug-do-treinamento>/`.
- **Botões de Ação na Nuvem:**
  - Botão Primário: *"☁️ Publicar na Base de Conhecimento do Produto"*.
  - Botão Secundário: *"⬇ Baixar knowledge_base.md (Multimodal)"* (para inspeção manual das URLs embutidas).
- **Visualizador de Código/Preview:** Expander para visualizar o Markdown estruturado que será lido pela IA.

---

### 📌 ÉPICO 4: Navegação Global e Rodapé do Sistema

#### US07 - Barra Lateral de Status e Identificação de Versão
> **Como** usuário e desenvolvedor,  
> **Quero** acompanhar visualmente em qual etapa do fluxo de trabalho estou e identificar claramente a versão da build em produção,  
> **Para que** eu tenha certeza das atualizações e consiga reiniciar a sessão quando desejar.

**Critérios de Aceitação (UI/UX):**
- **Sidebar (Menu Lateral Fixo):**
  - Logotipo e Nome do Produto: `VideoToDocument`.
  - Stepper Vertical:
    - `1. Upload & Configuração`
    - `2. Auditoria e Validação de Prints`
    - `3. Compilação do Documento`
    - *(Estados: Atual em destaque, Anteriores com check verde, Próximas em cinza)*.
  - Botão utilitário: *"🔄 Reiniciar Sessão / Novo Vídeo"*.
  - **Rodapé Fixo no Canto Inferior Esquerdo:**
    - Tag/Badge com a versão da aplicação (ex: `Versão: v1.2.0`).
    - Informação sutil da build/ambiente (`Build: main`).

---

## 🎨 Diretrizes de Componentes para o Figma

| Componente | Função | Dica de Estilo |
| :--- | :--- | :--- |
| **Stepper / Wizard** | Guiar o progresso (Etapas 1, 2 e 3) | Barra superior limpa ou vertical na sidebar com ícones de estado |
| **Dropzone de Mídia** | Receber vídeo e legenda | Área com bordas pontilhadas, ícone SVG central, suporte a arrastar arquivo |
| **Scorecard Bar** | Resumo de métricas na auditoria | Pills/Badges modernos com contadores coloridos e filtros integrados |
| **Card de Print (Gallery)** | Revisar prints e ajustar tempo | Container branco com sombra suave (drop-shadow leve), layout bem compacto |
| **Popover de Ajuste Fino** | Compensar segundos do vídeo | Micro-botões compactos (`-1s`, `-0.5s`, `+0.5s`, `+1s`) alinhados horizontalmente |
| **Cloud Publish Box** | Publicar no GCS / Vertex AI | Caixa com destaque visual de nuvem, seletor de produtos e preview de subpasta |

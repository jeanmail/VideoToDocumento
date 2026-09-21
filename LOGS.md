# 📋 Guia de Logs - VideoToDocumento

## 📍 Localização dos Logs

Os logs são salvos em:
```
./logs/videotodocumento.log
```

## 🔍 Visualizando Logs

### Via Makefile (Recomendado)

```bash
# Últimos 100 linhas
make logs

# Acompanhar em tempo real (tail -f)
make logs-tail

# Apenas erros
make logs-errors

# Apenas logs de extração
make logs-extract

# Apenas logs de export
make logs-export

# Apenas logs do worker
make logs-worker
```

### Via Linha de Comando (Docker)

```bash
# Últimas linhas
docker-compose logs videotodocumento

# Em tempo real
docker-compose logs -f videotodocumento

# Apenas erros
docker-compose logs videotodocumento | grep ERROR
```

### Via API HTTP

```bash
# Últimas 50 linhas (default)
curl http://localhost:9999/api/logs

# Últimas 100 linhas
curl "http://localhost:9999/api/logs?lines=100"

# Apenas erros
curl "http://localhost:9999/api/logs?level=error"

# Apenas logs INFO
curl "http://localhost:9999/api/logs?level=info"

# Apenas logs WARNING
curl "http://localhost:9999/api/logs?level=warning"
```

## 📊 Formato dos Logs

Cada linha de log contém:
```
TIMESTAMP - MODULE - LEVEL - [FUNCTION:LINE] - MESSAGE
```

Exemplo:
```
2026-09-21 10:30:45,123 - __main__ - INFO - [extract_video:245] - 🚀 [EXTRACT-ENDPOINT] Requisição recebida | filename=demo.mp4 | lang=pt | sync=False
```

## 🎯 Emojis e Significados

- 🚀 `[*-START]` - Início de operação
- ✅ `[*-OK]` / `[*-COMPLETE]` - Sucesso/Conclusão
- ❌ `[*-ERROR]` - Erro crítico
- ⚠️ `[*-WARN]` - Aviso
- 📊 `[*-PROGRESS]` - Progresso de operação
- 🔄 `[WORKER-*]` - Logs da thread de processamento
- 🎤 `[WHISPER/TRANSCR]` - Transcrição de áudio
- 🎬 `[EXTRACT]` - Extração de frames
- 📦 `[EXPORT/ZIP]` - Export de arquivos
- 💾 `[*-SAVE]` - Salvamento de dados
- 🏥 `[HEALTH]` - Health check
- 📋 `[LOGS]` - Operações de logs

## 🔍 Rastreando uma Requisição Completa

### 1. Upload de Vídeo
```
🚀 [EXTRACT-ENDPOINT] Requisição recebida
✅ [EXTRACT-ENDPOINT] Arquivo salvo com sucesso
📤 [EXTRACT-ENDPOINT] Retornando job_id para polling
```

### 2. Processing em Background (Worker)
```
🔄 [WORKER-START] Job iniciado
🎤 [WORKER] Iniciando Whisper transcription
📊 [WORKER-AUDIO-PROGRESS] progress=25%
📊 [WORKER-AUDIO-PROGRESS] progress=50%
✅ [WORKER] Transcrição concluída
🎬 [WORKER] Iniciando extração de frames
📊 [WORKER-FRAMES-PROGRESS] progress=60%
✅ [WORKER] Frames extraídos
🎉 [WORKER-COMPLETE] status=completed
```

### 3. Polling de Progresso
```
🔍 [PROGRESS-ENDPOINT] Consultando progresso
📊 [PROGRESS-ENDPOINT] Job encontrado | status=processing | progress=50
```

### 4. Export de Arquivos
```
📄 [EXPORT-DOCX-ENDPOINT] Solicitação de export
📝 [EXPORT-DOCX-ENDPOINT] Frames selecionados
💾 [EXPORT-DOCX-ENDPOINT] Construindo DOCX
✅ [EXPORT-DOCX-ENDPOINT] DOCX criado com sucesso | size=2048576 bytes
```

### 5. Publicação no GCS
```
☁️ [PUBLISH-GCS-ENDPOINT] Solicitação de publicação
📝 [PUBLISH-GCS-ENDPOINT] Frames selecionados
💾 [PUBLISH-GCS-ENDPOINT] Gerando documentos
⬆️ [PUBLISH-GCS-ENDPOINT] Enviando para GCS
🎉 [PUBLISH-GCS-ENDPOINT] Publicação bem-sucedida
```

## 🐛 Debugando Problemas

### Problema: "Job não encontrado"
```bash
# Procure por:
make logs-errors

# Procure pela linha:
⚠️ [*-ENDPOINT] Job inválido | job_id=... | status=...
```

### Problema: "Erro ao extrair áudio"
```bash
# Procure por:
make logs-extract | grep ERROR

# Procure por:
❌ [WORKER-ERROR] job_id=... | error=...
```

### Problema: "Memória insuficiente"
```bash
# Procure por:
make logs | grep -i "memory\|oom"

# Solução: Aumentar limite de memória em docker-compose.yml
mem_limit: 8g  # Aumentar de 6g para 8g ou mais
```

### Problema: "PDF/DOCX não gerado"
```bash
# Procure por:
make logs-export | grep ERROR

# Procure por:
❌ [EXPORT-*-ENDPOINT] Falha ao extrair novo frame
```

## 🔧 Limpando Logs Antigos

```bash
# Remover logs com mais de 7 dias
make clean

# Ou manualmente
find logs -name "*.log" -mtime +7 -delete
```

## 📈 Monitoramento Contínuo

Para monitorar a aplicação em produção:

```bash
# Terminal 1: Acompanhar logs em tempo real
make logs-tail

# Terminal 2: Monitorar health check
watch -n 5 'curl -s http://localhost:9999/api/health | jq .'

# Terminal 3: Monitorar erros apenas
watch -n 10 'docker-compose logs videotodocumento | grep -i ERROR | tail -20'
```

## 📝 Log Levels

- **DEBUG** - Informações de debug detalhadas (progress, variáveis, etc)
- **INFO** - Informações gerais do fluxo
- **WARNING** - Avisos que algo pode estar errado
- **ERROR** - Erros que precisam de atenção

## 🎯 Checklist para Troubleshooting

1. ✅ Verificar se o container está rodando: `docker-compose ps`
2. ✅ Verificar health check: `make health`
3. ✅ Visualizar últimos logs: `make logs`
4. ✅ Procurar por erros: `make logs-errors`
5. ✅ Acompanhar em tempo real: `make logs-tail`
6. ✅ Checar arquivo de log: `cat logs/videotodocumento.log`
7. ✅ Reiniciar container: `make restart`
8. ✅ Verificar espaço em disco: `df -h`
9. ✅ Verificar memória: `docker stats`
10. ✅ Checar permissões de pasta: `ls -la logs/`

.PHONY: help build up down logs logs-tail logs-errors restart clean shell health

help:
	@echo "VideoToDocumento - Comandos disponíveis:"
	@echo ""
	@echo "  make build           - Compila a imagem Docker"
	@echo "  make up              - Inicia o container"
	@echo "  make down            - Para o container"
	@echo "  make restart         - Reinicia o container"
	@echo "  make logs            - Mostra últimos 100 linhas de logs"
	@echo "  make logs-tail       - Acompanha logs em tempo real (tail -f)"
	@echo "  make logs-errors     - Mostra apenas erros (linhas com ERROR)"
	@echo "  make logs-extract    - Mostra apenas logs de extração"
	@echo "  make logs-export     - Mostra apenas logs de export"
	@echo "  make logs-worker     - Mostra apenas logs do worker"
	@echo "  make shell           - Acessa shell do container"
	@echo "  make health          - Verifica status da aplicação"
	@echo "  make clean           - Remove logs antigos"
	@echo "  make clean-storage   - Remove arquivos de storage (CUIDADO!)"
	@echo ""

build:
	@echo "🔨 Compilando imagem Docker..."
	docker build -t videotodocumento:2.0.0 .

up:
	@echo "🚀 Iniciando aplicação..."
	docker-compose up -d
	@echo "✅ Aplicação iniciada! Acesse em: http://localhost:9999"

down:
	@echo "🛑 Parando aplicação..."
	docker-compose down

restart: down up
	@echo "✅ Aplicação reiniciada!"

logs:
	@echo "📋 Últimas 100 linhas de logs:"
	@docker-compose logs --tail=100 videotodocumento

logs-tail:
	@echo "👁️ Acompanhando logs em tempo real (Ctrl+C para sair)..."
	@docker-compose logs -f videotodocumento

logs-errors:
	@echo "❌ Mostrando apenas ERROS:"
	@docker-compose logs videotodocumento | grep -i "ERROR\|ERRO\|FAIL\|❌"

logs-extract:
	@echo "🎬 Mostrando logs de EXTRAÇÃO:"
	@docker-compose logs videotodocumento | grep -i "EXTRACT\|WORKER\|WHISPER\|TRANSCR"

logs-export:
	@echo "📦 Mostrando logs de EXPORT:"
	@docker-compose logs videotodocumento | grep -i "EXPORT\|DOCX\|PDF\|ZIP"

logs-worker:
	@echo "🔄 Mostrando logs do WORKER:"
	@docker-compose logs videotodocumento | grep -i "WORKER"

shell:
	@echo "🐚 Acessando shell do container..."
	@docker-compose exec videotodocumento /bin/bash

health:
	@echo "🏥 Verificando saúde da aplicação..."
	@curl -s http://localhost:8080/api/health | jq . || echo "❌ Aplicação indisponível"

clean:
	@echo "🗑️ Removendo logs antigos..."
	@find logs -name "*.log" -mtime +7 -delete || true
	@echo "✅ Limpeza concluída!"

clean-storage:
	@echo "⚠️  REMOVENDO ARQUIVOS DE STORAGE (downloads, temporários, frames extraídos)..."
	@read -p "Tem certeza? (s/N): " confirm && [ "$$confirm" = "s" ] && rm -rf storage/temp_uploads/* storage/extracted_frames/* storage/outputs/* && echo "✅ Storage limpo!" || echo "Cancelado"

.SILENT: help

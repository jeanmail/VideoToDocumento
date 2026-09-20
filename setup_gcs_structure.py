"""
Script para provisionar o Bucket GCS e criar a estrutura inicial de pastas dos 7 produtos.
Uso:
    python setup_gcs_structure.py --bucket seu-bucket-unico [--project seu-gcp-project-id] [--key caminho/chave.json]
"""

import sys
import argparse
import os
from google.cloud import storage
from google.oauth2 import service_account

SUPPORTED_PROJECTS = [
    "prescricao-digital",
    "automation",
    "onetouch",
    "personal",
    "clinic",
    "monitoring",
    "agenda-online",
]

def setup_gcs(bucket_name: str, project_id: str = None, credentials_path: str = None, location: str = "us-central1"):
    print(f"🔧 Conectando ao Google Cloud Storage...")
    
    if credentials_path and os.path.exists(credentials_path):
        creds = service_account.Credentials.from_service_account_file(credentials_path)
        client = storage.Client(credentials=creds, project=project_id or creds.project_id)
    else:
        client = storage.Client(project=project_id)

    # 1. Obter ou Criar Bucket
    try:
        bucket = client.get_bucket(bucket_name)
        print(f"✅ Bucket já existe: gs://{bucket_name}")
    except Exception:
        print(f"🚀 Criando bucket: gs://{bucket_name} na região {location}...")
        bucket = client.create_bucket(bucket_name, project=project_id, location=location)
        print(f"✅ Bucket criado com sucesso!")

    # 2. Criar a estrutura de pastas dos 7 produtos (com arquivo .keep)
    print("\n📁 Criando estrutura de pastas para os 7 produtos:")
    for slug in SUPPORTED_PROJECTS:
        blob_path = f"{slug}/.keep"
        blob = bucket.blob(blob_path)
        blob.upload_from_string(f"Diretorio do produto: {slug}", content_type="text/plain")
        print(f"   [+] gs://{bucket_name}/{slug}/")

    print("\n🎉 Estrutura do GCS configurada com sucesso!")
    print("\nPróximos passos para o Vertex AI Agent Builder:")
    for slug in SUPPORTED_PROJECTS:
        print(f"   - Data Store '{slug}': apontar para gs://{bucket_name}/{slug}/*")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Configurar Bucket e estrutura GCS para o VideoToDocumento")
    parser.add_argument("--bucket", required=True, help="Nome global único do bucket (ex: kb-contact-center-jean)")
    parser.add_argument("--project", default=None, help="ID do projeto GCP")
    parser.add_argument("--key", default=None, help="Caminho do arquivo de chave Service Account .json")
    parser.add_argument("--location", default="us-central1", help="Região do bucket (default: us-central1)")
    args = parser.parse_args()

    setup_gcs(bucket_name=args.bucket, project_id=args.project, credentials_path=args.key, location=args.location)

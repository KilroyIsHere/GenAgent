# Kraken OCR service

Docker-based Kraken OCR server (FastAPI wrapper).
- Dockerfile: CUDA 13 / Ubuntu 24.04 image, Kraken from mittagessen/kraken
- docker-compose.yml: port 8008->8000, GPU limits, workspace/models/data volumes
- app/main.py: /ocr (upload), /ocr-path (workspace-restricted), /health, /models

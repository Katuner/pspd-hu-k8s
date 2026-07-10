# API Gateway — imagem baseada em python slim para reduzir tamanho
FROM python:3.11-slim

WORKDIR /app

# Dependências primeiro (aproveita cache de camadas do Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Compila os stubs gRPC a partir do .proto (copiado pelo build context na raiz)
COPY hospital.proto .
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. hospital.proto

COPY main.py .

EXPOSE 8000
# 2 workers uvicorn por pod: paralelismo interno sem competir demais com o HPA
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

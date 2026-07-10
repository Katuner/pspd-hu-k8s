# Patient Data Service (gRPC)
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY hospital.proto .
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. hospital.proto

COPY server.py .

EXPOSE 50051 9100
CMD ["python", "server.py"]

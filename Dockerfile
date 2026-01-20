FROM python:3.11-slim

WORKDIR /app

# Instalando dependências de sistema (necessário para algumas libs de IA e bancos de dados)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copia e instala os requirements primeiro (otimiza o cache do Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install \
      --no-cache-dir \
      --default-timeout=120 \
      --retries=5 \
      -r requirements.txt

# Copia o restante do código
COPY . .

# Expõe a porta que o FastAPI vai usar
EXPOSE 8000

# CONFIGURAÇÃO IMPORTANTE: 
# Ajustamos o comando para rodar o main.py que é o ponto de entrada unificado.
# O --proxy-headers é fundamental se você usa Easypanel/Nginx para pegar o IP real.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
FROM php:8.3-cli

RUN apt-get update \
    && apt-get install -y python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip3 install --break-system-packages -r requirements.txt

COPY main.py .

RUN mkdir -p /app/php_projects

CMD ["python3", "main.py"]

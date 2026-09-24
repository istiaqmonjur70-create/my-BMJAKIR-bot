FROM php:8.3-cli

ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        ca-certificates \
        curl \
        unzip \
        git \
    && rm -rf /var/lib/apt/lists/*

# Install Composer
RUN curl -sS https://getcomposer.org/installer \
    | php -- \
      --install-dir=/usr/local/bin \
      --filename=composer

WORKDIR /app

COPY requirements.txt .

RUN pip3 install \
    --break-system-packages \
    -r requirements.txt

COPY main.py .

RUN mkdir -p /app/data/projects

EXPOSE 10000

CMD ["python3", "main.py"]
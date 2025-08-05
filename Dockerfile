FROM python:3.9-alpine

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование скрипта
COPY cleanup.py .

# Создание non-root пользователя для безопасности
RUN adduser -D -s /bin/sh appuser
USER appuser

# Рабочая директория
WORKDIR /home/appuser

ENTRYPOINT ["python", "/cleanup.py"]

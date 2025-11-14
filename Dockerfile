# lightweight
FROM python:3.11-slim

# створимо робочу папку
WORKDIR /app

# копіюємо код і статичні файли
COPY main.py /app/
COPY index.html /app/
COPY message.html /app/
COPY error.html /app/
COPY style.css /app/
COPY logo.png /app/
COPY storage /app/storage

# залежності 
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# змінні за замовчуванням
ENV APP_HOST=0.0.0.0 \
    APP_PORT=3000 \
    SOCKET_HOST=0.0.0.0 \
    SOCKET_PORT=5000 \
    MONGO_URI=mongodb://mongo:27017 \
    MONGO_DB=goit \
    MONGO_COLLECTION=messages

EXPOSE 3000 5000

CMD ["python", "main.py"]

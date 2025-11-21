FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

RUN mkdir -p /app/data/groups /app/data/logs/private_chats

EXPOSE 10000

CMD ["python", "app.py"]

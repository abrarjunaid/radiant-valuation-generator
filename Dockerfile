FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Chromium is already installed in the base image
RUN playwright install chromium

COPY . .

ENV FLASK_APP=app.py
ENV FLASK_ENV=production

EXPOSE 8080

CMD flask run --host=0.0.0.0 --port=8080

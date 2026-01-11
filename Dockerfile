FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirement.txt /app/requirement.txt
RUN pip install --no-cache-dir -r /app/requirement.txt

COPY . /app

EXPOSE 7860

# Use PORT if provided by the platform (HF Spaces typically uses 7860).
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-7860}"]



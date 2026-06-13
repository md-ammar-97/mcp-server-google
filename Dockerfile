FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# credentials.json and token.json are excluded via .gitignore.
# Supply them via GOOGLE_CREDENTIALS_B64 / GOOGLE_TOKEN_B64 env vars (Railway)
# or bind-mount them at runtime (plain Docker).
RUN chmod +x start.sh

EXPOSE 8000

CMD ["/bin/sh", "start.sh"]

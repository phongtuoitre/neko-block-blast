# Neko Block Blast API

## Chạy local

```powershell
D:\python\Game 2\.venv_new\Scripts\python.exe -m pip install -r server\requirements.txt
```

```powershell
$env:SECRET_KEY="change-this-local-development-secret"
D:\python\Game 2\.venv_new\Scripts\python.exe -m uvicorn server.main:app --reload --host 127.0.0.1 --port 8000
```

Nếu không đặt `DATABASE_URL`, server dùng SQLite tại
`server/data/neko_game.db`. Có thể sao chép `server/.env.example` thành
`server/.env` để cấu hình local; file `.env` đã được git bỏ qua.

## Azure App Service

Thiết lập các Application Settings:

```text
SECRET_KEY=<secret-key-thật>
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require
ACCESS_TOKEN_EXPIRE_MINUTES=60
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=<gmail-gửi-mail>
SMTP_PASSWORD=<google-app-password-16-ký-tự>
EMAIL_FROM=<gmail-gửi-mail>
EMAIL_FROM_NAME=Neko Block Blast
AZURE_OPENAI_ENDPOINT=<azure-openai-endpoint>
AZURE_OPENAI_API_KEY=<azure-openai-api-key>
AZURE_OPENAI_DEPLOYMENT=<deployment-name-da-tao-tren-Azure>
AZURE_OPENAI_API_VERSION=2024-10-21
```

Startup command:

```text
gunicorn -w 2 -k uvicorn.workers.UvicornWorker server.main:app
```

Client dùng biến môi trường `NEKO_API_BASE_URL` để trỏ đến URL App Service.

Neko AI Guide dùng `POST /api/ai-guide/chat`. Nếu chưa cấu hình Azure OpenAI
hoặc Azure tạm thời lỗi, API vẫn trả về hướng dẫn cơ bản không cần secret.

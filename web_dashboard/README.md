# Neko Block Blast Cloud Dashboard

Dashboard tĩnh cho dự án Neko Block Blast. Website dùng HTML, CSS và JavaScript thuần, không có React, Node.js, thư viện ngoài, APIM subscription key, JWT cố định, password, secret hoặc connection string ở frontend.

## Backend endpoints đã xác minh

Nguồn kiểm tra: `server/main.py`, `server/routers/jobs.py`, `server/routers/matches.py`, `server/routers/rooms.py`, `server/schemas.py` và test hiện có.

Base APIM được frontend dùng:

```text
https://apim-neko-game-nhom2-2026.azure-api.net/neko
```

Endpoint public:

- `GET /health`
  - Response thật: `{"status":"ok","service":"neko-block-blast-api"}`
- `GET /version`
  - Response thật: `{"deploy_from":"github-actions","version":"ci-cd-test-01"}`

Endpoint leaderboard hiện có:

- `GET /jobs/leaderboard-online`
  - Backend yêu cầu header `X-Job-Key`.
  - Frontend không nhúng key nên chỉ gọi không key và hiển thị thông báo nếu nhận `401`, `403` hoặc `503`.
  - Response khi hợp lệ:

```json
{
  "leaderboard": [
    {
      "user_id": 1,
      "username": "player",
      "display_name": "Player",
      "wins": 0,
      "matches": 0,
      "total_score": 0
    }
  ]
}
```

Endpoint điểm/trận hiện có nhưng cần Bearer token:

- `POST /matches/{match_id}/score`
- `GET /matches/{match_id}`
- `GET /rooms/{room_code}/active-match`

Các endpoint này trả `MatchRead` gồm:

```json
{
  "match_id": 1,
  "room_code": "ABC123",
  "mode": "1v1",
  "status": "playing",
  "remaining_seconds": 120,
  "winner_user_id": null,
  "winner_team": null,
  "players": [
    {
      "user_id": 1,
      "username": "player",
      "display_name": "Player",
      "team": 1,
      "score": 0,
      "result": null
    }
  ],
  "event_blob_uploaded": false,
  "event_blob_path": null
}
```

Không tìm thấy endpoint FastAPI công khai cho danh sách trận gần đây hoặc thành tích riêng. Dashboard chỉ hiển thị điểm/thắng/trận từ leaderboard nếu endpoint đó truy cập được qua APIM mà không cần secret.

## File

- `index.html`: giao diện dashboard.
- `styles.css`: giao diện responsive.
- `app.js`: gọi `/health`, `/version`, `/jobs/leaderboard-online` qua APIM.
- `staticwebapp.config.json`: cấu hình Azure Static Web Apps, không dùng khi chạy bằng Nginx.
- `Dockerfile`: image Nginx Alpine cho Azure Container Apps.
- `nginx.conf`: static hosting, fallback về `index.html`, `/healthz`, security headers.
- `.dockerignore`: loại file không cần thiết khỏi Docker context.
- `README.md`: ghi chú vận hành.

## Hành vi frontend

- Khi trang mở, website gọi API một lần.
- Khi người dùng bấm `Kiểm tra lại`, website gọi lại các endpoint.
- Không polling liên tục.
- Nếu `/health` thành công, trạng thái hiển thị `Online` và service lấy từ JSON thật.
- Nếu request lỗi, trạng thái hiển thị `Offline` hoặc thông báo endpoint cần xác thực; website không crash.

## Chạy bằng Docker

Build từ thư mục repo gốc:

```powershell
docker build -t neko-block-blast-dashboard ./web_dashboard
```

Chạy local:

```powershell
docker run --rm -p 8080:80 neko-block-blast-dashboard
```

Mở `http://localhost:8080`. Healthcheck container dùng:

```text
GET /healthz
```

## Azure Container Apps

Container phục vụ static site bằng Nginx trên port `80`. Nginx không proxy backend; JavaScript trong trình duyệt gọi APIM trực tiếp:

```text
https://apim-neko-game-nhom2-2026.azure-api.net/neko
```

Nếu APIM chưa bật CORS cho domain của Container App, dashboard sẽ hiển thị lỗi kết nối thay vì crash.

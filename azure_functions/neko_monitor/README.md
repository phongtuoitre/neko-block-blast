# Neko Monitor Azure Functions

Azure Functions project nay dung Function App rieng de monitor va chay cac tac vu serverless cho backend Neko Block Blast tren Azure App Service.

## App Settings

Set cac bien moi truong trong Azure Function App:

```text
NEKO_API_BASE_URL=https://<backend-app-service-url>
NEKO_JOB_KEY=<same-value-as-backend-ADMIN_JOB_KEY>
```

Backend FastAPI can co App Setting:

```text
ADMIN_JOB_KEY=<same-value-as-function-NEKO_JOB_KEY>
```

Khong hard-code URL, job key, token, mat khau hoac secret trong source.

## HTTP functions

Health check thu cong:

```text
GET /api/monitor/health-check
```

Cloud Operations Dashboard:

```text
GET /api/demo/dashboard
```

Serverless job proxy:

```text
GET  /api/jobs/summary
POST /api/jobs/cleanup-expired-rooms
GET  /api/jobs/leaderboard-online
```

Function App goi backend bang header:

```text
X-Job-Key: <NEKO_JOB_KEY>
```

Backend chi chap nhan neu header nay khop `ADMIN_JOB_KEY`.

## Cloud Operations Dashboard

Mo dashboard sau khi deploy:

```text
https://<function-app-name>.azurewebsites.net/api/demo/dashboard
```

Dashboard la mot trang HTML self-contained duoc tra ve boi Azure Functions. Trang nay dung inline CSS va JavaScript thuan, khong dung CDN va khong chua secret. JavaScript chi goi cac endpoint cung domain:

```text
GET  /api/monitor/health-check
GET  /api/jobs/summary
GET  /api/jobs/leaderboard-online
POST /api/jobs/cleanup-expired-rooms
```

Dashboard dung de demo Azure Functions nhu mot lop Cloud Operations cho game: xem backend online/offline, latency, thong ke users/rooms/matches, online leaderboard va chay cleanup expired rooms thu cong.

## Timer functions

`health_monitor_timer` chay moi 5 phut va goi:

```text
GET {NEKO_API_BASE_URL}/health
```

`room_cleanup_timer` chay moi 5 phut va goi:

```text
POST {NEKO_API_BASE_URL}/jobs/cleanup-expired-rooms
```

`game_stats_timer` chay moi 30 phut va goi:

```text
GET {NEKO_API_BASE_URL}/jobs/summary
```

Log co the xem trong Azure Portal, muc Function App Log Stream hoac Application Insights.

## Y nghia cloud

Azure Functions dong vai tro serverless worker doc lap: monitor backend, don phong waiting qua lau, lay thong ke he thong va tong hop leaderboard online. Backend FastAPI van chay tren Azure App Service, game client va gameplay khong bi thay doi.

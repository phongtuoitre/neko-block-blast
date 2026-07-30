# Neko Block Blast Cloud Dashboard

Dashboard thành tích công khai cho dự án Neko Block Blast. Website dùng HTML, CSS và JavaScript thuần, không có React, Node.js, thư viện ngoài hoặc thông tin nhạy cảm trong frontend.

## API frontend sử dụng

Base APIM:

```text
https://apim-neko-game-nhom2-2026.azure-api.net/neko
```

Endpoint được gọi:

- `GET /health`: trạng thái backend và tên service.
- `GET /version`: phiên bản backend và nguồn deploy.
- `GET /public/dashboard`: dữ liệu thành tích công khai.

Frontend chỉ gọi API khi trang vừa mở hoặc khi người dùng bấm `Kiểm tra lại`. Không có polling liên tục.

## Dữ liệu dashboard

`GET /public/dashboard` trả dữ liệu tổng hợp công khai:

- `leaderboard`: tối đa 10 người chơi, gồm hạng, username, display name, số trận, số trận thắng, tổng điểm và điểm cao nhất.
- `highlights`: điểm cao nhất, người chơi nhiều trận nhất và người chơi thắng nhiều nhất.
- `recent_matches`: tối đa 10 trận hoàn thành gần đây.

Website không hardcode dữ liệu người chơi mẫu. Nếu chưa có dữ liệu, UI hiển thị trạng thái rỗng thân thiện.

## File

- `index.html`: giao diện dashboard.
- `styles.css`: giao diện responsive.
- `app.js`: gọi API public qua APIM.
- `staticwebapp.config.json`: cấu hình Azure Static Web Apps, không dùng khi chạy bằng Nginx.
- `Dockerfile`: image Nginx Alpine cho Azure Container Apps.
- `nginx.conf`: static hosting, fallback về `index.html`, `/healthz`, security headers.
- `.dockerignore`: loại file không cần thiết khỏi Docker context.

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

Container phục vụ static site bằng Nginx trên port `80`. Nginx không proxy backend; JavaScript trong trình duyệt gọi APIM trực tiếp.

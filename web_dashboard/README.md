# Neko Block Blast Cloud Dashboard

Dashboard tĩnh cho dự án Neko Block Blast. Website dùng HTML, CSS và JavaScript thuần, không có React, Node.js, thư viện ngoài, subscription key, token, mật khẩu hoặc secret ở frontend.

## File

- `index.html`: cấu trúc dashboard.
- `styles.css`: giao diện responsive.
- `app.js`: gọi health/version qua Azure API Management.
- `staticwebapp.config.json`: cấu hình Azure Static Web Apps và security headers.
- `README.md`: ghi chú vận hành.

## Endpoint

- Health: `https://apim-neko-game-nhom2-2026.azure-api.net/neko/health`
- Version: `https://apim-neko-game-nhom2-2026.azure-api.net/neko/version`
- Game download: `https://nekoblockblastnhom2.blob.core.windows.net/game-demo/NekoBlockBlast.exe`

## Hành vi

- Khi trang mở, website gọi `/health` và `/version` một lần.
- Khi người dùng bấm `Kiểm tra lại`, website gọi lại hai endpoint trên.
- Không có polling liên tục.
- Nếu `/health` trả thành công, trạng thái hiển thị `Online` và service được lấy từ JSON.
- Nếu request lỗi, trạng thái hiển thị `Offline`, có thông báo dễ hiểu và website không crash.

## Chạy local

Có thể mở trực tiếp `index.html` hoặc chạy static server:

```powershell
python -m http.server 8080 --directory web_dashboard
```

Sau đó mở `http://localhost:8080`. Nếu APIM chưa cho phép CORS cho origin local, dashboard sẽ hiển thị trạng thái `Offline` thay vì crash.

## Deploy

Khi deploy bằng Azure Static Web Apps, dùng `web_dashboard` làm thư mục chứa static site. File `staticwebapp.config.json` đã cấu hình fallback về `/index.html` và security headers phù hợp cho website tĩnh.

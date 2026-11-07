# SkyRoute 系統架構圖（floorplan 匯出的單一 HTML），由 Railway 的 floorplan 服務部署
FROM caddy:2.8-alpine
COPY index.html /srv/index.html
CMD ["sh", "-c", "caddy file-server --root /srv --listen :${PORT:-8080}"]

# 小魔女聚合音乐 UI

这是独立的 React + Vite + TypeScript 前端。它只依赖 Flask 暴露的 `/api/*` 和 `/assets/*`，可以单独由 UI 开发者运行和构建。

```powershell
npm install
npm run dev
```

开发时先在项目根目录启动 `python XMNMusic_Web.py`，Vite 会把 `/api` 与 `/assets` 代理到 `127.0.0.1:5050`。

生产构建：

```powershell
npm run typecheck
npm run test
npm run build
```

Flask 默认从 `frontend/dist` 托管构建产物，也可以通过 `XMN_MUSIC_FRONTEND_DIST` 指定其他目录。

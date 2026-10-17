# UI/API Contract

The React UI consumes the existing Flask endpoints without changing their URLs. The frontend normalizes legacy payloads at the API boundary so every feature receives the same shape.

## Song

```ts
type Song = {
  mid: string
  name: string
  singer: string
  album: string
  album_mid?: string
  interval: number
  durationMs?: number
  cover: string
  source: 'qq' | 'netease'
  platform: 'qq' | 'netease'
  region?: string
  lyrics?: string
}
```

`source` takes precedence over `platform`; a missing value defaults to `qq` for compatibility with older QQ payloads. Favorite identity is `${source}::${mid}`.

## Endpoints

- `GET /api/search?q=&page=&source=` returns `{ songs, page, total_pages, fallback }`.
- `GET /api/recommend?site=` returns `{ songs, fallback, site }`.
- `GET /api/toplist/:topId?site=` returns `{ songs, top_id, fallback, site? }`.
- `GET /api/song/:mid?source=&name=&singer=` returns `SongDetail` with a short-lived stream URL.
- `GET/POST /api/favorites` keeps the existing JSON-file persistence contract.
- `GET /api/status` exposes cookie and connectivity status for diagnostics.

## Local development

Run Flask on port 5050 and `npm run dev` in `frontend/`. Vite proxies `/api` and `/assets` to Flask. Set `VITE_API_BASE_URL` only when the API is hosted on another origin.

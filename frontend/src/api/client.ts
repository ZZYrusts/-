import type {
  ApiError,
  RecommendResponse,
  SearchResponse,
  Song,
  SongDetail,
  StatusResponse,
  ToplistResponse,
} from './types'
import { normalizeSong } from './types'

const apiBase = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

class ApiRequestError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
  }
}

const request = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(`${apiBase}${path}`, init)
  const body = (await response.json().catch(() => ({}))) as T & ApiError
  if (!response.ok) throw new ApiRequestError(body.error || `请求失败（${response.status}）`, response.status)
  return body as T
}

const normalizeSongs = (songs: unknown): Song[] =>
  Array.isArray(songs) ? songs.map((song) => normalizeSong(song as Record<string, unknown>)) : []

export const api = {
  async search(query: string, page: number, source: string): Promise<SearchResponse> {
    const result = await request<SearchResponse>(
      `/api/search?q=${encodeURIComponent(query)}&page=${page}&source=${encodeURIComponent(source)}`,
    )
    return { ...result, songs: normalizeSongs(result.songs) }
  },
  async recommend(site: string): Promise<RecommendResponse> {
    const result = await request<RecommendResponse>(`/api/recommend?site=${encodeURIComponent(site)}`)
    return { ...result, songs: normalizeSongs(result.songs) }
  },
  async toplist(topId: number, site: string): Promise<ToplistResponse> {
    const result = await request<ToplistResponse>(`/api/toplist/${topId}?site=${encodeURIComponent(site)}`)
    return { ...result, songs: normalizeSongs(result.songs) }
  },
  detail(song: Song): Promise<SongDetail> {
    return request<SongDetail>(
      `/api/song/${encodeURIComponent(song.mid)}?source=${song.source}&name=${encodeURIComponent(song.name)}&singer=${encodeURIComponent(song.singer)}`,
    ).then((result) => {
      const normalized = normalizeSong({ ...song, ...result })
      return {
        ...normalized,
        ...result,
        cover: result.cover || song.cover,
        name: result.name || song.name,
        singer: result.singer || song.singer,
        album: result.album || song.album,
        lyrics: result.lyrics || song.lyrics || '',
      }
    })
  },
  favorites(): Promise<Song[]> {
    return request<unknown[]>('/api/favorites').then(normalizeSongs)
  },
  setFavorite(song: Song, active: boolean): Promise<{ items: Song[] }> {
    return request<{ items: unknown[] }>(`/api/favorites?active=${active ? '1' : '0'}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(song),
    }).then((result) => ({ items: normalizeSongs(result.items) }))
  },
  status(): Promise<StatusResponse> {
    return request<StatusResponse>('/api/status')
  },
  downloadUrl(song: Song, quality: string, coverSize: number) {
    return `${apiBase}/api/download/${encodeURIComponent(song.mid)}?quality=${encodeURIComponent(quality)}&name=${encodeURIComponent(song.name)}&singer=${encodeURIComponent(song.singer)}&album=${encodeURIComponent(song.album)}&source=${song.source}&coverSize=${coverSize}`
  },
  coverUrl(song: Song) {
    return song.cover ? `${apiBase}/api/cover?url=${encodeURIComponent(song.cover)}` : ''
  },
}

export { ApiRequestError }

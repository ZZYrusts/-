export type MusicSource = 'qq' | 'netease'

export interface Song {
  mid: string
  name: string
  singer: string
  album: string
  album_mid?: string
  interval: number
  durationMs?: number
  cover: string
  source: MusicSource
  platform: MusicSource
  region?: string
  lyrics?: string
}

export interface SongDetail extends Song {
  success: boolean
  url: string
  lyrics: string
  quality: string
  format: string
  actual_quality?: string | null
}

export interface SearchResponse {
  songs: Song[]
  page: number
  total_pages: number
  fallback?: string
}

export interface RecommendResponse {
  songs: Song[]
  fallback?: string
  site: MusicSource
}

export interface ToplistResponse {
  songs: Song[]
  top_id: number
  fallback?: string
  site?: MusicSource
}

export interface ApiError {
  error: string
}

export interface StatusResponse {
  cookie_file: string
  cookie_found: boolean
  cookie_count: number
  uin: string
  netease_cookie_found: boolean
  netease_cookie_count: number
}

export const normalizeSong = (input: Partial<Song> & Record<string, unknown>): Song => {
  const source = (input.source || input.platform || 'qq') as MusicSource
  return {
    mid: String(input.mid ?? ''),
    name: String(input.name ?? ''),
    singer: String(input.singer ?? ''),
    album: String(input.album ?? ''),
    album_mid: input.album_mid ? String(input.album_mid) : undefined,
    interval: Number(input.interval ?? 0),
    durationMs: input.durationMs == null ? undefined : Number(input.durationMs),
    cover: String(input.cover ?? ''),
    source: source === 'netease' ? 'netease' : 'qq',
    platform: source === 'netease' ? 'netease' : 'qq',
    region: input.region ? String(input.region) : undefined,
    lyrics: input.lyrics ? String(input.lyrics) : undefined,
  }
}

export const songKey = (song?: Partial<Song> | null) =>
  `${song?.source || song?.platform || 'qq'}::${song?.mid || ''}`

export const formatTime = (seconds: number) => {
  const value = Math.max(0, Number(seconds || 0))
  return `${Math.floor(value / 60).toString().padStart(2, '0')}:${Math.floor(value % 60)
    .toString()
    .padStart(2, '0')}`
}

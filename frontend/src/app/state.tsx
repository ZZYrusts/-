import { createContext, useContext, useEffect, useMemo, useReducer, type Dispatch, type PropsWithChildren } from 'react'
import { api } from '../api/client'
import type { MusicSource, Song, SongDetail } from '../api/types'
import { songKey } from '../api/types'

export type ViewMode = 'recommend' | 'search' | 'favorite'
export type PlayMode = 'sequential' | 'single' | 'list_loop' | 'random'

export interface AppState {
  site: MusicSource
  source: MusicSource
  view: ViewMode
  topId: number
  topName: string
  query: string
  page: number
  totalPages: number
  songs: Song[]
  featured: Song[]
  favorites: Song[]
  current: SongDetail | null
  queue: Song[]
  queueIndex: number
  playMode: PlayMode
  loading: boolean
  message: string
  error: string
  playerExpanded: boolean
  playerFloating: boolean
}

const initialState: AppState = {
  site: 'qq', source: 'qq', view: 'recommend', topId: 26, topName: '热歌榜', query: '', page: 1,
  totalPages: 1, songs: [], featured: [], favorites: [], current: null, queue: [], queueIndex: -1,
  playMode: (localStorage.getItem('xmn-play-mode') as PlayMode) || 'sequential', loading: false,
  message: '', error: '', playerExpanded: false, playerFloating: false,
}

type Action =
  | { type: 'loading'; value: boolean }
  | { type: 'set-home'; site: MusicSource }
  | { type: 'set-list'; view: ViewMode; songs: Song[]; page?: number; totalPages?: number; query?: string; topId?: number; topName?: string; featured?: Song[] }
  | { type: 'set-favorites'; favorites: Song[] }
  | { type: 'set-current'; current: SongDetail; queue?: Song[]; queueIndex?: number }
  | { type: 'set-error'; error: string }
  | { type: 'message'; message: string }
  | { type: 'toggle-player'; expanded?: boolean }
  | { type: 'toggle-floating'; floating: boolean }
  | { type: 'play-mode'; mode: PlayMode }

const reducer = (state: AppState, action: Action): AppState => {
  switch (action.type) {
    case 'loading': return { ...state, loading: action.value, error: action.value ? '' : state.error }
    case 'set-home': return { ...state, site: action.site, source: action.site }
    case 'set-list': return { ...state, view: action.view, songs: action.songs, featured: action.featured ?? state.featured, page: action.page ?? 1, totalPages: action.totalPages ?? 1, query: action.query ?? state.query, topId: action.topId ?? state.topId, topName: action.topName ?? state.topName, loading: false, error: '' }
    case 'set-favorites': return { ...state, favorites: action.favorites, songs: state.view === 'favorite' ? action.favorites : state.songs }
    case 'set-current': return { ...state, current: action.current, queue: action.queue ?? state.queue, queueIndex: action.queueIndex ?? state.queueIndex, playerFloating: false }
    case 'set-error': return { ...state, loading: false, error: action.error }
    case 'message': return { ...state, message: action.message }
    case 'toggle-player': {
      const expanded = action.expanded ?? !state.playerExpanded
      return { ...state, playerExpanded: expanded, playerFloating: expanded ? false : state.playerFloating }
    }
    case 'toggle-floating': return { ...state, playerFloating: action.floating, playerExpanded: action.floating ? false : state.playerExpanded }
    case 'play-mode': localStorage.setItem('xmn-play-mode', action.mode); return { ...state, playMode: action.mode }
    default: return state
  }
}

interface AppActions {
  dispatch: Dispatch<Action>
  loadRecommend: (site?: MusicSource) => Promise<void>
  loadToplist: (topId: number, name: string) => Promise<void>
  search: (query: string, page?: number) => Promise<void>
  loadFavorites: () => Promise<void>
  play: (song: Song, queue?: Song[], queueIndex?: number) => Promise<void>
  toggleFavorite: (song: Song) => Promise<void>
}

const StateContext = createContext<AppState | null>(null)
const ActionsContext = createContext<AppActions | null>(null)

export function AppProvider({ children }: PropsWithChildren) {
  const [state, dispatch] = useReducer(reducer, initialState)
  const actions = useMemo<AppActions>(() => ({
    dispatch,
    async loadRecommend(site = state.site) {
      dispatch({ type: 'loading', value: true })
      try {
        const result = await api.recommend(site)
        dispatch({ type: 'set-list', view: 'recommend', songs: result.songs, featured: result.songs.slice(0, 5), page: 1, totalPages: 1, topName: '热歌榜' })
      } catch (error) { dispatch({ type: 'set-error', error: error instanceof Error ? error.message : '推荐加载失败' }) }
    },
    async loadToplist(topId, name) {
      dispatch({ type: 'loading', value: true })
      try {
        const result = await api.toplist(topId, state.site)
        dispatch({ type: 'set-list', view: 'recommend', songs: result.songs, featured: result.songs.slice(0, 5), topId, topName: name })
      } catch (error) { dispatch({ type: 'set-error', error: error instanceof Error ? error.message : '榜单加载失败' }) }
    },
    async search(query, page = 1) {
      if (!query.trim()) { dispatch({ type: 'message', message: '请输入搜索内容' }); return }
      dispatch({ type: 'loading', value: true })
      try {
        const result = await api.search(query.trim(), page, state.source)
        const songs = await Promise.all(result.songs.map(async (song) => { if (song.cover) return song; try { const detail = await api.detail(song); return { ...song, cover: detail.cover || song.cover } } catch { return song } }))
        dispatch({ type: 'set-list', view: 'search', songs, page: result.page, totalPages: result.total_pages, query: query.trim() })
      } catch (error) { dispatch({ type: 'set-error', error: error instanceof Error ? error.message : '搜索失败' }) }
    },
    async loadFavorites() {
      try { dispatch({ type: 'set-favorites', favorites: await api.favorites() }) }
      catch (error) { dispatch({ type: 'set-error', error: error instanceof Error ? error.message : '收藏读取失败' }) }
    },
    async play(song, queue = state.songs, queueIndex = queue.findIndex((item) => songKey(item) === songKey(song))) {
      dispatch({ type: 'loading', value: true })
      try {
        const detail = await api.detail(song)
        dispatch({ type: 'set-current', current: detail, queue, queueIndex })
      } catch (error) { dispatch({ type: 'set-error', error: error instanceof Error ? error.message : '播放解析失败' }) }
      finally { dispatch({ type: 'loading', value: false }) }
    },
    async toggleFavorite(song) {
      try {
        const result = await api.setFavorite(song, !state.favorites.some((item) => songKey(item) === songKey(song)))
        dispatch({ type: 'set-favorites', favorites: result.items })
        dispatch({ type: 'message', message: '收藏已更新' })
      } catch (error) { dispatch({ type: 'set-error', error: error instanceof Error ? error.message : '收藏保存失败' }) }
    },
  }), [state.site, state.source, state.songs, state.favorites])

  useEffect(() => { void actions.loadFavorites(); void actions.loadRecommend('qq') }, [])

  return <StateContext.Provider value={state}><ActionsContext.Provider value={actions}>{children}</ActionsContext.Provider></StateContext.Provider>
}

export const useAppState = () => {
  const context = useContext(StateContext)
  if (!context) throw new Error('useAppState must be used inside AppProvider')
  return context
}

export const useAppActions = () => {
  const context = useContext(ActionsContext)
  if (!context) throw new Error('useAppActions must be used inside AppProvider')
  return context
}

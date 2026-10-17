import { useEffect, useMemo, useRef, useState, type CSSProperties, type FormEvent, type SyntheticEvent } from 'react'
import {
  ChevronLeft, ChevronRight, Download, Heart, ListMusic, LoaderCircle, Menu, Music2,
  Pause, Play, Search, SlidersHorizontal, Sparkles, Volume2, X,
} from 'lucide-react'
import { api } from '../api/client'
import { formatTime, songKey, type MusicSource, type Song } from '../api/types'
import { useAppActions, useAppState, type PlayMode } from './state'
import './app.css'

const topLists = [
  { id: 26, name: '热歌榜' }, { id: 27, name: '新歌榜' }, { id: 4, name: '流行指数' },
  { id: 5, name: '内地榜' }, { id: 6, name: '港台榜' }, { id: 16, name: '欧美榜' },
  { id: 17, name: '韩国榜' }, { id: 18, name: '日本榜' },
]

const sourceLabel = (source: MusicSource) => source === 'netease' ? '网易云' : 'QQ 音乐'

const songFallbackCover = (event: SyntheticEvent<HTMLImageElement>) => {
  event.currentTarget.src = '/assets/default-cover.webp'
}

function App() {
  const state = useAppState()
  const actions = useAppActions()
  const [query, setQuery] = useState(state.query)
  const [mobileMenu, setMobileMenu] = useState(false)
  const [downloadSong, setDownloadSong] = useState<Song | null>(null)
  const [notice, setNotice] = useState('')

  useEffect(() => {
    if (state.message) { setNotice(state.message); const timer = window.setTimeout(() => setNotice(''), 2600); return () => window.clearTimeout(timer) }
  }, [state.message])

  const search = async (event: FormEvent) => { event.preventDefault(); await actions.search(query, 1) }
  const switchSite = async (site: MusicSource) => { actions.dispatch({ type: 'set-home', site }); setMobileMenu(false); await actions.loadRecommend(site) }
  const showFavorites = () => { actions.dispatch({ type: 'set-list', view: 'favorite', songs: state.favorites, featured: [] }); setMobileMenu(false) }

  return <div className="app-shell">
    <Background />
    <header className="topbar">
      <div className="topbar-inner">
        <button className="icon-button mobile-menu-button" aria-label="打开菜单" onClick={() => setMobileMenu((value) => !value)}><Menu size={19} /></button>
        <a className="brand" href="/" aria-label="小魔女聚合音乐首页"><span className="brand-mark"><Sparkles size={16} /></span><span>小魔女<span className="brand-muted">/</span>聚合音乐</span></a>
        <form className="search-bar" onSubmit={search} role="search"><Search size={18} aria-hidden="true" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索歌曲、歌手或专辑" aria-label="搜索歌曲、歌手或专辑" /><button type="submit" aria-label="开始搜索"><span>搜索</span><ChevronRight size={16} /></button></form>
        <div className={`top-actions ${mobileMenu ? 'is-open' : ''}`}>
          <button className={`source-switch ${state.site === 'qq' ? 'is-active' : ''}`} onClick={() => void switchSite('qq')}><span className="source-dot qq-dot" />QQ 音乐</button>
          <button className={`source-switch ${state.site === 'netease' ? 'is-active' : ''}`} onClick={() => void switchSite('netease')}><span className="source-dot netease-dot" />网易云</button>
          <button className="ghost-button" onClick={showFavorites}><Heart size={16} />我的收藏<span className="count-badge">{state.favorites.length}</span></button>
        </div>
      </div>
    </header>

    <main className="content-wrap">
      <section className="hero-copy"><div><p className="eyebrow"><span className="eyebrow-line" />今晚的音乐由你决定</p><h1>把夜色交给<br /><em>下一首歌。</em></h1><p className="hero-subtitle">穿过榜单、歌词和微光，找到一首刚好属于此刻的歌。</p></div><div className="hero-orbit" aria-hidden="true"><span /><span /><span /></div></section>

      <section className="section-block chart-section"><div className="section-heading"><div><p className="section-kicker">DISCOVER / 01</p><h2>探索榜单</h2></div><span className="section-note">{sourceLabel(state.site)} · {state.topName}</span></div><div className="toplist-tabs">{topLists.map((item) => <button key={item.id} className={state.topId === item.id ? 'is-active' : ''} onClick={() => void actions.loadToplist(item.id, item.name)}>{item.name}</button>)}</div></section>

      <section className="section-block"><div className="section-heading"><div><p className="section-kicker">CURATED / 02</p><h2>{state.view === 'favorite' ? '我的收藏' : '今晚精选'}</h2></div><span className="section-note">{state.loading ? '正在同步音乐宇宙…' : `${state.songs.length} 首可播放`}</span></div><FeaturedGrid songs={state.featured} onPlay={(song) => void actions.play(song, state.songs)} onFavorite={(song) => void actions.toggleFavorite(song)} favorites={state.favorites} /></section>

      <section className="workspace-grid section-block">
        <aside className="side-panel"><div className="side-panel-heading"><div><p className="section-kicker">YOUR SPACE</p><h3>收藏与排行</h3></div><ListMusic size={18} /></div><RankList title="我的收藏" songs={state.favorites.slice(0, 6)} onPlay={(song) => void actions.play(song, state.favorites)} empty="收藏几首歌，让这里变成你的夜间电台。" /><RankList title={`${sourceLabel(state.site)} · 精选`} songs={state.songs.slice(0, 6)} onPlay={(song) => void actions.play(song, state.songs)} empty="榜单正在赶来。" /></aside>
        <section className="catalog-panel"><div className="catalog-toolbar"><div><p className="section-kicker">LIBRARY / {state.view === 'search' ? 'SEARCH' : 'CHART'}</p><h2>{state.view === 'search' ? `“${state.query}”的结果` : `${sourceLabel(state.site)} ${state.topName}`}</h2></div><div className="catalog-meta"><span>{state.loading ? <LoaderCircle className="spin" size={15} /> : <span className="live-dot" />} {state.loading ? '同步中' : '在线'}</span><button className="filter-button"><SlidersHorizontal size={15} />筛选</button></div></div>{state.error && <div className="inline-alert" role="alert"><span>{state.error}</span><button onClick={() => actions.dispatch({ type: 'set-error', error: '' })}><X size={15} /></button></div>}<SongList songs={state.songs} favorites={state.favorites} current={state.current} onPlay={(song) => void actions.play(song, state.songs)} onFavorite={(song) => void actions.toggleFavorite(song)} onDownload={setDownloadSong} /><Pagination page={state.page} totalPages={state.totalPages} onPage={(page) => void actions.search(state.query, page)} /></section>
      </section>
    </main>

    <PlayerDock />
    {downloadSong && <DownloadSheet song={downloadSong} onClose={() => setDownloadSong(null)} onMessage={(value) => { setDownloadSong(null); setNotice(value) }} />}
    {notice && <div className="toast" role="status"><Sparkles size={16} />{notice}</div>}
  </div>
}

function Background() { return <div className="background-layer" aria-hidden="true"><picture><source media="(max-width: 700px)" srcSet="/assets/maid-bg-tall.webp" /><img src="/assets/maid-bg-wide.webp" alt="" /></picture><div className="background-veil" /><div className="background-grid" /></div> }

function FeaturedGrid({ songs, favorites, onPlay, onFavorite }: { songs: Song[]; favorites: Song[]; onPlay: (song: Song) => void; onFavorite: (song: Song) => void }) {
  if (!songs.length) return <div className="empty-surface"><Music2 size={24} /><span>正在寻找适合今晚的旋律…</span></div>
  return <div className="featured-grid">{songs.map((song, index) => <article className="featured-card" style={{ '--delay': `${index * 55}ms` } as CSSProperties} key={songKey(song)} onClick={() => onPlay(song)}><div className="cover-frame"><img src={song.cover || '/assets/default-cover.webp'} onError={songFallbackCover} alt={`${song.name}封面`} /><div className="cover-shine" /><button className="play-orb" aria-label={`播放 ${song.name}`} onClick={(event) => { event.stopPropagation(); onPlay(song) }}><Play size={18} fill="currentColor" /></button><button className={`cover-favorite ${favorites.some((item) => songKey(item) === songKey(song)) ? 'is-on' : ''}`} aria-label="收藏" onClick={(event) => { event.stopPropagation(); onFavorite(song) }}><Heart size={15} fill="currentColor" /></button></div><div className="featured-card-info"><strong>{song.name || '未命名歌曲'}</strong><span>{song.singer || '未知歌手'}</span></div></article>)}</div>
}

function RankList({ title, songs, onPlay, empty }: { title: string; songs: Song[]; onPlay: (song: Song) => void; empty: string }) {
  return <section className="rank-list-block"><div className="rank-list-title"><span>{title}</span><ChevronRight size={15} /></div>{songs.length ? songs.map((song, index) => <button key={songKey(song)} className="rank-row" onClick={() => onPlay(song)}><span className="rank-index">{String(index + 1).padStart(2, '0')}</span><span className="rank-copy"><strong>{song.name}</strong><small>{song.singer}</small></span><Play size={14} className="rank-play" /></button>) : <p className="rank-empty">{empty}</p>}</section>
}

function SongList({ songs, favorites, current, onPlay, onFavorite, onDownload }: { songs: Song[]; favorites: Song[]; current: Song | null; onPlay: (song: Song) => void; onFavorite: (song: Song) => void; onDownload: (song: Song) => void }) {
  if (!songs.length) return <div className="empty-table"><Music2 size={30} /><strong>这里还没有歌曲</strong><span>换一个关键词，或切换榜单试试。</span></div>
  return <div className="song-table" role="table"><div className="song-table-head" role="row"><span>#</span><span>歌曲</span><span>歌手</span><span>专辑</span><span>时长</span><span /></div>{songs.map((song, index) => { const favorite = favorites.some((item) => songKey(item) === songKey(song)); const active = current && songKey(current) === songKey(song); return <div className={`song-row ${active ? 'is-active' : ''}`} role="row" key={songKey(song)} onDoubleClick={() => onPlay(song)}><span className="song-number">{String(index + 1).padStart(2, '0')}</span><button className="song-main" onClick={() => onPlay(song)}><span className="song-thumb"><img src={song.cover || '/assets/default-cover.webp'} onError={songFallbackCover} alt="" /><Play size={13} fill="currentColor" /></span><span><strong>{song.name || '未命名歌曲'}</strong><small>{song.region || sourceLabel(song.source)}</small></span></button><span className="song-singer">{song.singer || '未知歌手'}</span><span className="song-album">{song.album || '—'}</span><span className="song-duration">{formatTime(song.interval)}</span><span className="song-actions"><button className={`row-icon ${favorite ? 'is-on' : ''}`} aria-label={favorite ? '取消收藏' : '收藏'} onClick={(event) => { event.stopPropagation(); onFavorite(song) }}><Heart size={15} fill={favorite ? 'currentColor' : 'none'} /></button><button className="row-icon" aria-label="下载歌曲" onClick={(event) => { event.stopPropagation(); onDownload(song) }}><Download size={15} /></button></span></div> })}</div>
}

function Pagination({ page, totalPages, onPage }: { page: number; totalPages: number; onPage: (page: number) => void }) {
  if (totalPages <= 1) return null
  return <div className="pagination"><button disabled={page <= 1} onClick={() => onPage(page - 1)}><ChevronLeft size={15} />上一页</button><span>{page} / {totalPages}</span><button disabled={page >= totalPages} onClick={() => onPage(page + 1)}>下一页<ChevronRight size={15} /></button></div>
}

function PlayerDock() {
  const state = useAppState(); const actions = useAppActions(); const audioRef = useRef<HTMLAudioElement>(null); const [playing, setPlaying] = useState(false); const [progress, setProgress] = useState(0); const [lyricsIndex, setLyricsIndex] = useState(-1); const [dockPosition, setDockPosition] = useState<{ x: number; y: number } | null>(null); const dragRef = useRef<{ dx: number; top: number; width: number; height: number; dy: number } | null>(null); const didDragRef = useRef(false)
  const [lyrics, setLyrics] = useState<{ time: number; text: string }[]>([]); const lyricsScrollRef = useRef<HTMLDivElement>(null)
  useEffect(() => { setLyrics(parseLyrics(state.current?.lyrics || '')); setProgress(0); if (audioRef.current) { audioRef.current.src = state.current?.url || ''; audioRef.current.load(); void audioRef.current.play().then(() => setPlaying(true)).catch(() => setPlaying(false)) } }, [state.current])
  useEffect(() => { const current = lyricsScrollRef.current?.querySelector('.is-current'); if (current) current.scrollIntoView({ block: 'center', behavior: 'smooth' }) }, [lyricsIndex])
  const sync = () => { const audio = audioRef.current; if (!audio) return; setProgress(audio.duration ? audio.currentTime / audio.duration : 0); let current = -1; lyrics.forEach((line, index) => { if (audio.currentTime >= line.time) current = index }); setLyricsIndex(current) }
  const next = (direction: 1 | -1) => { if (!state.queue.length) return; let index = state.queueIndex + direction; if (state.playMode === 'random') index = Math.floor(Math.random() * state.queue.length); if (index < 0) index = state.queue.length - 1; if (index >= state.queue.length) index = state.playMode === 'sequential' ? -1 : 0; if (index >= 0) void actions.play(state.queue[index], state.queue, index) }
  const toggle = () => { const audio = audioRef.current; if (!audio || !state.current) return; if (audio.paused) void audio.play().then(() => setPlaying(true)); else { audio.pause(); setPlaying(false) } }
  const cycleMode = () => { const modes: PlayMode[] = ['sequential', 'single', 'list_loop', 'random']; const labels = ['顺序', '单曲', '循环', '随机']; const index = (modes.indexOf(state.playMode) + 1) % modes.length; actions.dispatch({ type: 'play-mode', mode: modes[index] }); actions.dispatch({ type: 'message', message: `播放模式：${labels[index]}` }) }
  useEffect(() => { const move = (event: PointerEvent) => { if (!dragRef.current) return; didDragRef.current = true; setDockPosition({ x: Math.max(8, Math.min(window.innerWidth - dragRef.current.width - 8, event.clientX - dragRef.current.dx)), y: state.playerFloating ? dragRef.current.top : Math.max(8, Math.min(window.innerHeight - dragRef.current.height - 8, event.clientY - dragRef.current.dy)) }) }; const up = () => { dragRef.current = null }; window.addEventListener('pointermove', move); window.addEventListener('pointerup', up); return () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up) } }, [state.playerFloating]);
  if (!state.current) return null
  return <aside className={`player-dock ${state.playerExpanded ? 'is-expanded' : ''} ${state.playerFloating ? 'is-floating' : ''}`} style={(() => { if (!dockPosition || !state.playerFloating || state.playerExpanded) return undefined; return { left: Math.max(8, Math.min(dockPosition.x, window.innerWidth - 84 - 8)), top: Math.max(8, Math.min(dockPosition.y, window.innerHeight - 84 - 8)), right: 'auto', bottom: 'auto' }; })()} onPointerDown={(event) => { if (state.playerFloating && !(event.target as HTMLElement).closest('button')) { didDragRef.current = false; event.currentTarget.setPointerCapture(event.pointerId); const rect = event.currentTarget.getBoundingClientRect(); dragRef.current = { dx: event.clientX - rect.left, dy: event.clientY - rect.top, top: rect.top, width: rect.width, height: rect.height } } }} onPointerUp={() => { dragRef.current = null }} onPointerCancel={() => { dragRef.current = null }} onLostPointerCapture={() => { dragRef.current = null }} onClick={() => { if (state.playerFloating && !didDragRef.current) actions.dispatch({ type: 'toggle-floating', floating: false }); didDragRef.current = false }} aria-label={state.playerFloating ? '展开播放器，可拖动' : undefined}><div className="dock-backdrop" /><div className="dock-content"><div className="dock-art"><img src={state.current.cover || '/assets/default-cover.webp'} onError={songFallbackCover} alt="" draggable={false} onDragStart={(event) => event.preventDefault()} /><div className={`dock-ring ${playing ? 'is-playing' : ''}`} /></div><div className="dock-meta"><span className="dock-kicker">NOW PLAYING · {sourceLabel(state.current.source)}</span><strong>{state.current.name}</strong><span>{state.current.singer} · {state.current.album || '单曲'}</span><div className="dock-progress"><span style={{ transform: `scaleX(${progress})` }} /></div></div><div className="dock-controls"><button className="icon-button" onClick={() => next(-1)} aria-label="上一首"><ChevronLeft size={18} /></button><button className="dock-play" onClick={toggle} aria-label={playing ? '暂停' : '播放'}>{playing ? <Pause size={19} fill="currentColor" /> : <Play size={19} fill="currentColor" />}</button><button className="icon-button" onClick={() => next(1)} aria-label="下一首"><ChevronRight size={18} /></button></div><div className="dock-actions"><button className="icon-button" onClick={cycleMode} title="播放模式"><span className="mode-label">{state.playMode === 'random' ? '随机' : state.playMode === 'single' ? '单曲' : state.playMode === 'list_loop' ? '循环' : '顺序'}</span></button><button className="icon-button" onClick={() => actions.dispatch({ type: 'toggle-player', expanded: !state.playerExpanded })} aria-label="展开歌词"><ListMusic size={17} /></button><button className="icon-button" onClick={() => actions.dispatch({ type: 'toggle-floating', floating: !state.playerFloating })} aria-label="收起播放器">{state.playerFloating ? <X size={17} /> : <SlidersHorizontal size={17} />}</button></div></div>{state.playerExpanded && <div className="lyrics-drawer"><div className="drawer-head"><div><span className="section-kicker">LYRICS / LIVE</span><h3>歌词现场</h3></div><button className="icon-button" onClick={() => actions.dispatch({ type: 'toggle-player', expanded: false })}><X size={18} /></button></div><div className="lyrics-scroll" ref={lyricsScrollRef}>{lyrics.length ? lyrics.map((line, index) => <p key={`${line.time}-${index}`} className={lyricsIndex === index ? 'is-current' : ''}>{line.text}</p>) : <p className="lyrics-empty">当前歌曲暂无歌词</p>}</div></div>}<div className="dock-audio-hidden"><audio ref={audioRef} onTimeUpdate={sync} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} /></div></aside>
}

function DownloadSheet({ song, onClose, onMessage }: { song: Song; onClose: () => void; onMessage: (message: string) => void }) {
  const [quality, setQuality] = useState('320'); const [coverSize, setCoverSize] = useState(1200); const [status, setStatus] = useState('idle'); const [progress, setProgress] = useState(0); const [error, setError] = useState('')
  const download = async () => { setStatus('loading'); setError(''); try { const response = await fetch(api.downloadUrl(song, quality, coverSize)); if (!response.ok) { const result = await response.json().catch(() => ({})); throw new Error(result.error || '下载失败') } const total = Number(response.headers.get('content-length') || 0); const reader = response.body?.getReader(); const chunks: BlobPart[] = []; let loaded = 0; if (reader) { while (true) { const part = await reader.read(); if (part.done) break; chunks.push(part.value as BlobPart); loaded += part.value.length; if (total) setProgress(Math.round((loaded / total) * 100)) } } else chunks.push(new Uint8Array(await response.arrayBuffer()) as BlobPart); const blob = new Blob(chunks, { type: response.headers.get('content-type') || 'audio/mpeg' }); const filename = `${song.singer || '未知歌手'}-${song.name || '未知歌曲'}.${quality === 'flac' ? 'flac' : quality === 'm4a' ? 'm4a' : 'mp3'}`; if ('showSaveFilePicker' in window) { const picker = await (window as Window & { showSaveFilePicker?: (options: unknown) => Promise<{ name: string; createWritable: () => Promise<{ write: (data: Blob) => Promise<void>; close: () => Promise<void> }> }> }).showSaveFilePicker?.({ suggestedName: filename }); if (!picker) throw new Error('未选择保存位置'); const writable = await picker.createWritable(); await writable.write(blob); await writable.close() } else { const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; anchor.click(); URL.revokeObjectURL(url) } setStatus('done'); onMessage(`已准备下载：${filename}`) } catch (downloadError) { setStatus('error'); setError(downloadError instanceof Error ? downloadError.message : '下载失败') } }
  return <div className="sheet-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && status !== 'loading') onClose() }}><section className="download-sheet" role="dialog" aria-modal="true" aria-labelledby="download-title"><div className="sheet-handle" /><div className="sheet-heading"><div><span className="section-kicker">EXPORT / AUDIO</span><h2 id="download-title">保存这首歌</h2><p>{song.name} · {song.singer}</p></div><button className="icon-button" onClick={onClose} disabled={status === 'loading'}><X size={18} /></button></div><div className="quality-grid"><label className={quality === 'flac' ? 'is-selected' : ''}><input type="radio" checked={quality === 'flac'} onChange={() => setQuality('flac')} />FLAC<span>无损</span></label><label className={quality === '320' ? 'is-selected' : ''}><input type="radio" checked={quality === '320'} onChange={() => setQuality('320')} />320k<span>MP3</span></label><label className={quality === '128' ? 'is-selected' : ''}><input type="radio" checked={quality === '128'} onChange={() => setQuality('128')} />128k<span>MP3</span></label></div><label className="cover-select">封面尺寸<select value={coverSize} onChange={(event) => setCoverSize(Number(event.target.value))}><option value="1500">超高清 · 1500×1500</option><option value="1200">高清 · 1200×1200</option><option value="800">中清 · 800×800</option><option value="500">标清 · 500×500</option></select></label>{status === 'loading' && <div className="download-status"><div><span>正在整理音频</span><b>{progress}%</b></div><div className="download-track"><span style={{ transform: `scaleX(${progress / 100})` }} /></div></div>}{error && <div className="inline-alert" role="alert">{error}</div>}<div className="sheet-actions"><button className="secondary-button" onClick={onClose} disabled={status === 'loading'}>取消</button><button className="primary-button" onClick={() => void download()} disabled={status === 'loading'}>{status === 'loading' ? <LoaderCircle className="spin" size={16} /> : <Download size={16} />} {status === 'done' ? '已保存' : '开始下载'}</button></div></section></div>
}

const parseLyrics = (text: string) => String(text || '').split(/\r?\n/).flatMap((row) => { const matches = [...row.matchAll(/\[(\d+):(\d+(?:\.\d+)?)\]/g)]; const lyric = row.replace(/\[\d+:[\d.]+\]/g, '').trim() || ' '; return matches.map((match) => ({ time: Number(match[1]) * 60 + Number(match[2]), text: lyric })) }).sort((a, b) => a.time - b.time)

export default App



import { describe, expect, it } from 'vitest'
import { formatTime, normalizeSong, songKey } from './types'

describe('song contract', () => {
  it('normalizes legacy platform-only payloads', () => {
    const song = normalizeSong({ mid: 4, name: 'Night', platform: 'netease', interval: '71' } as never)
    expect(song).toMatchObject({ mid: '4', source: 'netease', platform: 'netease', interval: 71 })
    expect(songKey(song)).toBe('netease::4')
  })

  it('formats durations for player and catalog', () => {
    expect(formatTime(71)).toBe('01:11')
    expect(formatTime(0)).toBe('00:00')
  })
})

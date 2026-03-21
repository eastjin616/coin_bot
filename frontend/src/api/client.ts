import axios from 'axios'

const api = axios.create({ baseURL: 'http://localhost:8000' })

export const getTrades = () => api.get('/api/trades').then(r => r.data)
export const getSignals = (market?: string) =>
  api.get('/api/signals', { params: market ? { market } : {} }).then(r => r.data)
export const getBalance = () => api.get('/api/balance').then(r => r.data)
export const getWatchlist = () => api.get('/api/watchlist').then(r => r.data)
export const addWatchlist = (item: { market: string; symbol: string; name: string }) =>
  api.post('/api/watchlist', item).then(r => r.data)
export const removeWatchlist = (market: string, symbol: string) =>
  api.delete(`/api/watchlist/${market}/${symbol}`).then(r => r.data)

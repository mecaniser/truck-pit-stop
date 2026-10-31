import { mergeConfig } from 'vite'
import base from './vite.config'
export default (env: Parameters<typeof base>[0]) => mergeConfig(base(env), { cacheDir: '../output/equipment/vite-cache' })

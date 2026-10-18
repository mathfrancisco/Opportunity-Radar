import { fileURLToPath } from 'node:url'
import { pathToFileURL } from 'node:url'
import { createRequire } from 'node:module'

const appRequire = createRequire(new URL('../../apps/web/package.json', import.meta.url))
const appImport = (id: string) => import(/* @vite-ignore */ pathToFileURL(appRequire.resolve(id)).href)
const [{ defineConfig }, { default: react }, { default: tailwindcss }] = await Promise.all([
  appImport('vite'), appImport('@vitejs/plugin-react'), appImport('@tailwindcss/vite'),
])

export default defineConfig({
  plugins: [react(), tailwindcss()],
  root: process.cwd(),
  resolve: {
    alias: [
      { find: /^@clerk\/react$/, replacement: fileURLToPath(new URL('./ux-clerk-shim.tsx', import.meta.url)) },
      ...['react/jsx-runtime', 'react/jsx-dev-runtime', 'react-dom/client'].map((name) => ({
        find: new RegExp(`^${name.replaceAll('/', '\\/')}$`),
        replacement: appRequire.resolve(name),
      })),
      ...['react', 'react-dom', 'react-router-dom', '@tanstack/react-query'].map((name) => ({
        find: new RegExp(`^${name.replaceAll('/', '\\/')}$`), replacement: appRequire.resolve(name),
      })),
    ],
    dedupe: ['react', 'react-dom', 'react-router-dom', '@tanstack/react-query'],
  },
  server: {
    host: '127.0.0.1',
    strictPort: true,
    watch: {
      ignored: ['**/apps/web/.tmp/**'],
    },
  },
})

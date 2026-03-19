const { app, BrowserWindow, session } = require('electron')
const path = require('path')
const http = require('http')
const fs = require('fs')

app.disableHardwareAcceleration()

const MIME = {
  '.html': 'text/html',
  '.js':   'application/javascript',
  '.mjs':  'application/javascript',
  '.css':  'text/css',
  '.svg':  'image/svg+xml',
  '.png':  'image/png',
  '.jpg':  'image/jpeg',
  '.ico':  'image/x-icon',
  '.woff2':'font/woff2',
  '.woff': 'font/woff',
  '.ttf':  'font/ttf',
}

function startStaticServer(distPath) {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      // Strip query-string, prevent path traversal
      const urlPath = req.url.split('?')[0].replace(/\.\./g, '')
      const target  = urlPath === '/' ? '/index.html' : urlPath
      const filePath = path.join(distPath, target)

      fs.readFile(filePath, (err, data) => {
        if (err) {
          // SPA fallback — serve index.html for unknown paths
          fs.readFile(path.join(distPath, 'index.html'), (_e, html) => {
            if (_e) { res.writeHead(404); res.end('Not found'); return }
            res.writeHead(200, { 'Content-Type': 'text/html' })
            res.end(html)
          })
        } else {
          const mime = MIME[path.extname(filePath)] || 'application/octet-stream'
          res.writeHead(200, { 'Content-Type': mime })
          res.end(data)
        }
      })
    })

    // Port 0 → OS kiest een vrije poort
    server.listen(0, '127.0.0.1', () => {
      resolve({ server, port: server.address().port })
    })
  })
}

app.whenReady().then(async () => {
  const distPath = path.join(__dirname, 'dist')
  const { server, port } = await startStaticServer(distPath)

  // Microfoon toestemming verlenen (nodig voor Web Speech API)
  session.defaultSession.setPermissionRequestHandler((_wc, permission, callback) =>
    callback(permission === 'media'))

  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#23211D',
    autoHideMenuBar: true,
    show: false,
    webPreferences: { contextIsolation: true },
  })

  // Laad via localhost zodat Web Speech API werkt
  win.loadURL(`http://127.0.0.1:${port}`)
  win.once('ready-to-show', () => win.show())

  app.on('window-all-closed', () => {
    server.close()
    app.quit()
  })
})

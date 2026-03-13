const { app, BrowserWindow } = require('electron')
const path = require('path')

app.whenReady().then(() => {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#23211D',
    autoHideMenuBar: true,
    webPreferences: { contextIsolation: true }
  })
  win.loadFile(path.join(__dirname, 'dist', 'index.html'))
})

app.on('window-all-closed', () => app.quit())

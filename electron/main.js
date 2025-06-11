const { app, BrowserWindow } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let backend;

function createWindow() {
  const win = new BrowserWindow({
    width: 1024,
    height: 768,
    webPreferences: {
      contextIsolation: true,
    },
  });
  win.loadFile(path.join(__dirname, 'frontend', 'index.html'));
}

app.whenReady().then(() => {
  const backendPath = path.join(__dirname, 'backend', process.platform === 'win32' ? 'ai-finance-backend.exe' : 'app.py');
  if (process.platform === 'win32') {
    backend = spawn(backendPath);
  }

  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (backend) backend.kill();
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
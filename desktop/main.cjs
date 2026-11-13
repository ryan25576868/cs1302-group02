/**
 * Prism desktop shell.
 *
 * The web app is loaded from a short-lived local server on a random loopback
 * port. No ports are fixed, so a normal Prism install never fights another
 * process (or another copy of Prism).
 */
const { app, BrowserWindow, Menu, dialog, shell } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

let mainWindow = null;
let localServer = null;
let appOrigin = null;
let starting = false;

const isMac = process.platform === 'darwin';
const launchFullscreen = process.argv.includes('--fullscreen');

// A portable copy ships a portable.flag next to Prism.exe. Keep its browser
// profile beside the app instead of depending on AppData write access.
const executableDir = path.dirname(process.execPath);
if (fs.existsSync(path.join(executableDir, 'portable.flag'))) {
  const portableData = path.join(executableDir, 'PrismData');
  fs.mkdirSync(portableData, { recursive: true });
  app.setPath('userData', portableData);
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  });

  app.whenReady().then(bootstrap);
}

async function bootstrap() {
  if (starting) return;
  starting = true;
  try {
    const appPath = app.getAppPath();
    const serverModuleUrl = pathToFileURL(path.join(appPath, 'server.mjs')).href;
    const { startPrismServer } = await import(serverModuleUrl);
    localServer = await startPrismServer({
      host: '127.0.0.1',
      port: 0,
      root: appPath
    });
    appOrigin = new URL(localServer.url).origin;
    createWindow(localServer.url);
    installMenu();
  } catch (error) {
    dialog.showErrorBox(
      'Prism could not start',
      `The local application server failed to start.\n\n${error?.message || error}`
    );
    app.quit();
  } finally {
    starting = false;
  }
}

function createWindow(url) {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 960,
    minHeight: 680,
    show: false,
    backgroundColor: '#f4f1ea',
    title: 'Prism — see your code from every angle',
    icon: path.join(app.getAppPath(), 'assets', 'icon.png'),
    autoHideMenuBar: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: false
    }
  });

  mainWindow.loadURL(url);

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    if (launchFullscreen) mainWindow.setFullScreen(true);
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  mainWindow.webContents.setWindowOpenHandler(({ url: target }) => {
    if (appOrigin && target.startsWith(`${appOrigin}/`)) return { action: 'allow' };
    if (/^https?:/i.test(target)) shell.openExternal(target);
    return { action: 'deny' };
  });

  mainWindow.webContents.on('will-navigate', (event, target) => {
    if (appOrigin && target.startsWith(`${appOrigin}/`)) return;
    event.preventDefault();
    if (/^https?:/i.test(target)) shell.openExternal(target);
  });

  mainWindow.webContents.on('did-fail-load', (_event, code, description) => {
    if (code === -3) return; // navigation was intentionally aborted
    dialog.showErrorBox('Prism could not load', `${description} (${code})`);
  });
}

function installMenu() {
  const template = [
    {
      label: 'File',
      submenu: [
        {
          label: 'Reload app',
          accelerator: 'CmdOrCtrl+R',
          click: () => mainWindow?.reload()
        },
        { type: 'separator' },
        { role: isMac ? 'close' : 'quit' }
      ]
    },
    {
      label: 'View',
      submenu: [
        {
          label: 'Toggle full screen',
          accelerator: isMac ? 'Ctrl+Cmd+F' : 'F11',
          click: () => {
            if (!mainWindow) return;
            mainWindow.setFullScreen(!mainWindow.isFullScreen());
          }
        },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'toggleDevTools' }
      ]
    },
    {
      label: 'Help',
      submenu: [
        {
          label: 'About Prism',
          click: () => {
            dialog.showMessageBox(mainWindow, {
              type: 'info',
              title: 'About Prism',
              message: 'Prism — visual code lab',
              detail: `Version ${app.getVersion()}\n\nA local-first code visualizer. Your code is analyzed in this app; AI is optional and uses the provider you configure.`,
              buttons: ['OK']
            });
          }
        },
        {
          label: 'Open application folder',
          click: () => shell.openPath(app.getAppPath())
        }
      ]
    }
  ];

  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

app.on('window-all-closed', () => {
  if (!isMac) app.quit();
});

app.on('activate', () => {
  if (mainWindow || !localServer) return;
  createWindow(localServer.url);
});

app.on('before-quit', () => {
  if (localServer?.server) {
    try { localServer.server.close(); } catch { /* process exits anyway */ }
  }
});

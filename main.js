const { app, BrowserWindow, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const http = require('http');

const HOST_PORT = Number.parseInt(process.env.PORT || '8789', 10);
const HOST_URL = `http://127.0.0.1:${HOST_PORT}/`;
const HEALTH_URL = `http://127.0.0.1:${HOST_PORT}/api/health`;
const STARTUP_TIMEOUT_MS = 30_000;
const HEALTH_POLL_INTERVAL_MS = 500;

let mainWindow = null;
let hostProcess = null;
let hostExitExpected = false;
let quitting = false;

function isPackaged() {
  return app.isPackaged;
}

function resolveAppRoot() {
  return isPackaged() ? process.resourcesPath : __dirname;
}

function resolveHostDir() {
  return path.join(resolveAppRoot(), 'apps', 'host-python');
}

function resolveVendorSrc() {
  return path.join(resolveAppRoot(), 'vendor', 'OpenHarness', 'src');
}

function resolvePythonBin() {
  if (process.env.PYTHON_BIN) {
    return process.env.PYTHON_BIN;
  }

  if (process.platform === 'win32') {
    const candidates = [
      'C:\\Program Files\\Python312\\pythonw.exe',
      'C:\\Program Files\\Python312\\python.exe',
      'C:\\Windows\\py.exe',
    ];
    const found = candidates.find((candidate) => fs.existsSync(candidate));
    if (found) {
      return found;
    }
    return 'python';
  }

  return path.join(resolveHostDir(), '.venv', 'bin', 'python3');
}

function resolveWritableRoot() {
  return app.getPath('userData');
}

function resolveHostPythonPath(hostDir) {
  return path.join(hostDir, 'src');
}

function ensureDirExists(dirPath, label) {
  if (!fs.existsSync(dirPath)) {
    throw new Error(`${label} not found: ${dirPath}`);
  }
}

function ensureWindow() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    return mainWindow;
  }

  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 700,
    show: false,
    backgroundColor: '#111827',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      sandbox: false,
      nodeIntegration: false,
    },
  });

  mainWindow.on('ready-to-show', () => {
    mainWindow?.show();
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  return mainWindow;
}

function renderLoadingPage(message = 'Starting OpenHarness Host…') {
  const win = ensureWindow();
  const html = `<!doctype html>
  <html>
    <head>
      <meta charset="utf-8" />
      <title>OpenHarness Desktop</title>
      <style>
        body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0f172a; color: #e2e8f0; display: grid; place-items: center; height: 100vh; }
        .card { text-align: center; padding: 24px 32px; border: 1px solid rgba(148,163,184,.25); border-radius: 16px; background: rgba(15,23,42,.7); box-shadow: 0 10px 30px rgba(0,0,0,.25); }
        .sub { margin-top: 8px; color: #94a3b8; font-size: 14px; }
      </style>
    </head>
    <body>
      <div class="card">
        <div>${message}</div>
        <div class="sub">${HOST_URL}</div>
      </div>
    </body>
  </html>`;
  win.loadURL(`data:text/html;charset=UTF-8,${encodeURIComponent(html)}`);
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function requestJson(url) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, (res) => {
      if (res.statusCode !== 200) {
        res.resume();
        reject(new Error(`HTTP ${res.statusCode}`));
        return;
      }

      const chunks = [];
      res.on('data', (chunk) => chunks.push(chunk));
      res.on('end', () => {
        try {
          const raw = Buffer.concat(chunks).toString('utf8');
          resolve(JSON.parse(raw));
        } catch (error) {
          reject(error);
        }
      });
    });

    req.on('error', reject);
    req.setTimeout(2_000, () => {
      req.destroy(new Error('Request timeout'));
    });
  });
}

async function waitForHostReady(timeoutMs = STARTUP_TIMEOUT_MS) {
  const startedAt = Date.now();
  let lastError = null;

  while (Date.now() - startedAt < timeoutMs) {
    try {
      const health = await requestJson(HEALTH_URL);
      if (health && health.service) {
        return health;
      }
    } catch (error) {
      lastError = error;
    }

    if (hostProcess && hostProcess.exitCode !== null) {
      throw new Error(`Host exited early with code ${hostProcess.exitCode}`);
    }

    await wait(HEALTH_POLL_INTERVAL_MS);
  }

  throw new Error(`Host did not become ready in ${timeoutMs}ms${lastError ? `: ${lastError.message}` : ''}`);
}

function startHostProcess() {
  if (hostProcess) {
    return hostProcess;
  }

  const hostDir = resolveHostDir();
  const vendorSrc = resolveVendorSrc();
  const hostPythonPath = resolveHostPythonPath(hostDir);
  const pythonBin = resolvePythonBin();

  ensureDirExists(hostDir, 'Host directory');
  ensureDirExists(hostPythonPath, 'Host Python source');
  if (fs.existsSync(vendorSrc)) {
    // optional in some builds, but validate when present
    ensureDirExists(vendorSrc, 'Vendor source');
  }

  const env = {
    ...process.env,
    PORT: String(HOST_PORT),
    HOST: '127.0.0.1',
    PYTHON_BIN: pythonBin,
    HOST_DIR: hostDir,
    OPENHARNESS_REPO_ROOT: resolveAppRoot(),
    OPENHARNESS_VENDOR_SRC: vendorSrc,
    OPENHARNESS_CONFIG_DIR: path.join(resolveWritableRoot(), 'openharness-config'),
    OPENHARNESS_DATA_DIR: path.join(resolveWritableRoot(), 'openharness-data'),
  };

  hostExitExpected = false;

  const args = [
    '-m',
    'uvicorn',
    'host_mvp.ws_server:app',
    '--host',
    '127.0.0.1',
    '--port',
    String(HOST_PORT),
    '--log-level',
    'info',
  ];

  const spawnArgs = pythonBin.toLowerCase().endsWith('py.exe')
    ? ['-3.12', ...args]
    : args;

  console.log('[OpenHarness] hostDir =', hostDir);
  console.log('[OpenHarness] pythonBin =', pythonBin);
  console.log('[OpenHarness] PYTHONPATH =', hostPythonPath);

  hostProcess = spawn(pythonBin, spawnArgs, {
    cwd: hostDir,
    env: {
      ...env,
      PYTHONPATH: hostPythonPath,
    },
    stdio: process.platform === 'win32' ? 'ignore' : 'inherit',
    windowsHide: process.platform === 'win32',
    detached: process.platform !== 'win32',
  });

  hostProcess.on('exit', (code, signal) => {
    const expected = hostExitExpected || quitting;
    hostProcess = null;

    if (!expected) {
      const message = `Python host exited unexpectedly (${signal || code || 'unknown'}).`;
      if (mainWindow && !mainWindow.isDestroyed()) {
        dialog.showErrorBox('OpenHarness Desktop', message);
      } else {
        console.error(message);
      }
    }
  });

  hostProcess.on('error', (error) => {
    console.error('Failed to start Python host:', error);
  });

  return hostProcess;
}

function stopHostProcess() {
  if (!hostProcess) {
    return;
  }

  hostExitExpected = true;

  try {
    if (process.platform === 'win32') {
      hostProcess.kill();
    } else {
      process.kill(-hostProcess.pid, 'SIGTERM');
    }
  } catch (error) {
    console.warn('Failed to terminate host gracefully:', error);
    try {
      hostProcess.kill('SIGKILL');
    } catch (killError) {
      console.warn('Failed to force kill host:', killError);
    }
  }
}

async function bootApplication() {
  renderLoadingPage();
  startHostProcess();
  await waitForHostReady();
  const win = ensureWindow();
  await win.loadURL(HOST_URL);
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    const win = ensureWindow();
    if (win.isMinimized()) {
      win.restore();
    }
    win.focus();
  });

  app.whenReady().then(async () => {
    try {
      await bootApplication();
    } catch (error) {
      console.error(error);
      dialog.showErrorBox('OpenHarness Desktop', error.message || String(error));
      app.quit();
    }

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) {
        bootApplication().catch((error) => {
          console.error(error);
          dialog.showErrorBox('OpenHarness Desktop', error.message || String(error));
        });
      }
    });
  });

  app.on('before-quit', () => {
    quitting = true;
    stopHostProcess();
  });

  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
      app.quit();
    }
  });
}

const { app, BrowserWindow, ipcMain } = require('electron')
const path = require('path')
const net = require('net')
const { spawn, exec } = require('child_process')
const http = require('http')
const https = require('https')
const fs = require('fs')
const os = require('os')

let mainWindow
let backendProcess
let apiPort = 8000

function getAvailablePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.unref()
    server.on('error', reject)
    server.listen(0, () => {
      const port = server.address().port
      server.close(() => resolve(port))
    })
  })
}

function checkUrlReady(url, retries = 30) {
  return new Promise((resolve, reject) => {
    const check = (currentRetry) => {
      http.get(url, (res) => {
        if (res.statusCode === 200 || res.statusCode === 404) {
          resolve() // 404 is fine for an API root, means the server is running
        } else {
          retryOrReject(currentRetry)
        }
      }).on('error', () => {
        retryOrReject(currentRetry)
      })
    }
    
    const retryOrReject = (currentRetry) => {
      if (currentRetry >= retries) {
        reject(new Error(`Service at ${url} not ready`))
      } else {
        setTimeout(() => check(currentRetry + 1), 1000)
      }
    }
    
    check(0)
  })
}

async function startBackend() {
  try {
    apiPort = await getAvailablePort()
    console.log(`Starting backend on port ${apiPort}`)

    const isPackaged = app.isPackaged
    
    let command
    let args
    
    if (isPackaged) {
      command = path.join(process.resourcesPath, 'backend.exe')
      args = []
    } else {
      command = path.join(__dirname, '..', 'venv_desktop', 'Scripts', 'python.exe')
      if (process.platform === 'darwin') {
         command = path.join(__dirname, '..', 'venv_desktop', 'bin', 'python')
         if (!fs.existsSync(command)) {
            command = path.join(__dirname, '..', '.venv', 'bin', 'python')
            if (!fs.existsSync(command)) command = 'python3'
         }
      }
      args = [path.join(__dirname, '..', 'backend', 'main.py')]
    }

    backendProcess = spawn(command, args, {
      env: { ...process.env, API_PORT: apiPort.toString() }
    })

    backendProcess.stdout.on('data', (data) => console.log(`[Backend]: ${data.toString()}`))
    backendProcess.stderr.on('data', (data) => console.error(`[Backend ERR]: ${data.toString()}`))

    backendProcess.on('close', (code) => {
      console.log(`Backend process exited with code ${code}`)
    })

    await checkUrlReady(`http://127.0.0.1:${apiPort}/docs`)
    console.log("Backend is ready!")
    return true
  } catch (err) {
    console.error("Failed to start backend:", err)
    return false
  }
}

function checkOllamaInstall() {
  return new Promise((resolve) => {
    exec('ollama --version', (err) => {
      if (err) resolve(false)
      else resolve(true)
    })
  })
}

function installOllama() {
  return new Promise((resolve, reject) => {
     if (process.platform !== 'win32') {
       reject(new Error('Auto-install is only supported on Windows. Please install Ollama manually from ollama.com'))
       return
     }
     
     const installerPath = path.join(os.tmpdir(), 'OllamaSetup.exe')
     const file = fs.createWriteStream(installerPath)
     
     https.get('https://ollama.com/download/OllamaSetup.exe', (response) => {
       response.pipe(file)
       file.on('finish', () => {
         file.close(() => {
           console.log('Downloaded Ollama installer. Running silent install...')
           if (mainWindow) mainWindow.webContents.send('setup-status', 'Installing Ollama AI Engine... (Admin prompt may appear)')
           
           exec(`"${installerPath}" /S`, (err) => {
             if (err) {
               console.error('Silent install failed, manual install required.')
               reject(new Error('Silent install failed. Manual install required.'))
             } else {
               resolve(true)
             }
           })
         })
       })
     }).on('error', (err) => {
       fs.unlink(installerPath, () => {})
       reject(err)
     })
  })
}

function checkModel() {
  return new Promise((resolve) => {
    exec('ollama list', (err, stdout) => {
      if (err) return resolve(false)
      if (stdout.includes('llama3')) resolve(true)
      else resolve(false)
    })
  })
}

function pullModel() {
  return new Promise((resolve, reject) => {
    const pullProcess = spawn('ollama', ['pull', 'llama3'])
    
    pullProcess.stdout.on('data', (data) => {
      if (mainWindow) mainWindow.webContents.send('setup-status', `Downloading AI Model: ${data.toString().trim()}`)
    })
    
    pullProcess.stderr.on('data', (data) => {
      const output = data.toString().trim()
      if (output && mainWindow) mainWindow.webContents.send('setup-status', `Downloading AI Model: ${output}`)
    })

    pullProcess.on('close', (code) => {
      if (code === 0) resolve(true)
      else reject(new Error('Failed to pull llama3 model'))
    })
  })
}

async function runSetupSequence() {
  const isDev = !app.isPackaged

  if (isDev) {
    // In dev mode: backend is already started by start-backend.js on port 8000
    // Just wait for it to be ready, then signal complete
    try {
      mainWindow.webContents.send('setup-status', 'Connecting to dev backend...')
      await checkUrlReady('http://127.0.0.1:8000', 30)
      apiPort = 8000
      mainWindow.webContents.send('setup-complete', { apiPort })
    } catch (err) {
      mainWindow.webContents.send('setup-error', 'Backend not ready. Make sure npm run dev-backend is running. ' + err.message)
    }
    return
  }

  // Production mode: full setup sequence
  try {
    mainWindow.webContents.send('setup-status', 'Checking AI environment...')
    const hasOllama = await checkOllamaInstall()
    
    if (!hasOllama) {
      mainWindow.webContents.send('setup-status', 'Downloading Ollama AI Engine...')
      await installOllama()
    }
    
    mainWindow.webContents.send('setup-status', 'Verifying LLM Model availability...')
    const hasModel = await checkModel()
    if (!hasModel) {
      await pullModel()
    }
    
    mainWindow.webContents.send('setup-status', 'Waiting for AI Service (localhost:11434)...')
    await checkUrlReady('http://127.0.0.1:11434', 10)
    
    mainWindow.webContents.send('setup-status', 'Starting Application Backend...')
    const backendReady = await startBackend()
    
    if (!backendReady) throw new Error('Backend failed to start')
    
    mainWindow.webContents.send('setup-complete', { apiPort })
  } catch (err) {
    mainWindow.webContents.send('setup-error', err.message)
  }
}


function waitForVite(url, retries = 30) {
  return new Promise((resolve, reject) => {
    const check = (remaining) => {
      http.get(url, (res) => {
        resolve()
      }).on('error', () => {
        if (remaining <= 0) {
          reject(new Error('Vite dev server did not start in time'))
        } else {
          setTimeout(() => check(remaining - 1), 500)
        }
      })
    }
    check(retries)
  })
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    show: false, // Don't show until ready
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    }
  })

  let startUrl = process.env.ELECTRON_START_URL || 'http://127.0.0.1:5173'
  if (app.isPackaged) {
    const indexPath = path.join(__dirname, 'frontend', 'index.html')
    startUrl = `file://${indexPath}`
  }

  // In dev mode, wait for Vite to be ready before loading
  if (!app.isPackaged) {
    try {
      console.log('Waiting for Vite dev server...')
      await waitForVite('http://127.0.0.1:5173')
      console.log('Vite is ready!')
    } catch (e) {
      console.error('Could not connect to Vite:', e.message)
    }
  }
  
  mainWindow.loadURL(startUrl)

  // Show window only after page has loaded (no white flash)
  mainWindow.webContents.on('did-finish-load', () => {
    mainWindow.show()
    runSetupSequence()
  })

  mainWindow.on('closed', function () {
    mainWindow = null
    if (backendProcess) {
      backendProcess.kill()
    }
  })
}

app.whenReady().then(() => {
  createWindow()
})

app.on('window-all-closed', function () {
  if (process.platform !== 'darwin') {
    app.quit()
  }
  if (backendProcess) {
    backendProcess.kill()
  }
})

app.on('activate', function () {
  if (mainWindow === null) {
    createWindow()
  }
})

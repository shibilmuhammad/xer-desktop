const path = require('path');
const os = require('os');
const fs = require('fs');
const { spawn, exec } = require('child_process');
const net = require('net');

const isWindows = os.platform() === 'win32';
const backendDir = path.join(__dirname, '..', 'backend');
const PORT = 8000;

const pythonPath = isWindows 
  ? path.join(__dirname, '..', 'venv_desktop', 'Scripts', 'python.exe')
  : path.join(__dirname, '..', 'venv_desktop', 'bin', 'python3');

// Kill whatever is using port 8000 before starting
function killPort(port) {
  return new Promise((resolve) => {
    const cmd = isWindows
      ? `for /f "tokens=5" %a in ('netstat -aon ^| find ":${port}"') do taskkill /f /pid %a`
      : `lsof -ti :${port} | xargs kill -9`;
    exec(cmd, () => resolve()); // ignore errors (means port was free)
  });
}

function isPortFree(port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once('error', () => resolve(false));
    server.once('listening', () => { server.close(); resolve(true); });
    server.listen(port);
  });
}

async function start() {
  console.log(`--- Backend Diagnostic Start ---`);
  console.log(`Platform: ${os.platform()}`);
  console.log(`Current Dir: ${process.cwd()}`);
  console.log(`Backend Dir: ${backendDir}`);
  console.log(`Python Path: ${pythonPath}`);
  console.log(`Python Exists: ${fs.existsSync(pythonPath)}`);
  console.log(`--------------------------------`);

  const free = await isPortFree(PORT);
  if (!free) {
    console.log(`Port ${PORT} is in use. Killing stale process...`);
    await killPort(PORT);
    // Give OS a moment to release the port
    await new Promise(r => setTimeout(r, 1000));
  }

  const exe = fs.existsSync(pythonPath) ? pythonPath : (isWindows ? 'python' : 'python3');
  spawnBackend(exe);
}

function spawnBackend(exe) {
  console.log(`Spawning uvicorn with: ${exe}`);
  const backend = spawn(exe, ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(PORT), '--reload'], {
    cwd: backendDir,
    stdio: 'pipe',
    shell: isWindows 
  });

  backend.stdout.on('data', (data) => process.stdout.write(`[Backend-Out]: ${data}`));
  backend.stderr.on('data', (data) => process.stderr.write(`[Backend-Err]: ${data}`));
  backend.on('error', (err) => console.error('CRITICAL: Failed to start backend spawn:', err));
  backend.on('exit', (code) => {
    console.log(`Backend process exited with code ${code}`);
    if (code !== 0) console.error(`Backend exited with error. Check logs above.`);
  });
}

start();

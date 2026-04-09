const path = require('path');
const os = require('os');
const fs = require('fs');
const { spawn } = require('child_process');

const isWindows = os.platform() === 'win32';
const backendDir = path.join(__dirname, '..', 'backend');
const pythonPath = isWindows 
  ? path.join(__dirname, '..', 'venv_desktop', 'Scripts', 'python.exe')
  : path.join(__dirname, '..', 'venv_desktop', 'bin', 'python3');

console.log(`--- Backend Diagnostic Start ---`);
console.log(`Platform: ${os.platform()}`);
console.log(`Current Dir: ${process.cwd()}`);
console.log(`Backend Dir: ${backendDir}`);
console.log(`Python Path: ${pythonPath}`);
console.log(`Python Exists: ${fs.existsSync(pythonPath)}`);
console.log(`--------------------------------`);

if (!fs.existsSync(pythonPath)) {
  console.error(`\nERROR: Virtual environment Python not found at: ${pythonPath}`);
  console.log(`Falling back to system 'python'...`);
  const systemPython = isWindows ? 'python' : 'python3';
  spawnBackend(systemPython);
} else {
  spawnBackend(pythonPath);
}

function spawnBackend(exe) {
  console.log(`Spawning uvicorn with: ${exe}`);
  const backend = spawn(exe, ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8000', '--reload'], {
    cwd: backendDir,
    stdio: 'pipe',
    shell: isWindows 
  });

  backend.stdout.on('data', (data) => {
    process.stdout.write(`[Backend-Out]: ${data}`);
  });

  backend.stderr.on('data', (data) => {
    process.stderr.write(`[Backend-Err]: ${data}`);
  });

  backend.on('error', (err) => {
    console.error('CRITICAL: Failed to start backend spawn:', err);
  });

  backend.on('exit', (code) => {
    console.log(`Backend process exited with code ${code}`);
    if (code !== 0) {
      console.error(`This usually means a Python dependency is missing or there is a port conflict on 8000.`);
    }
  });
}

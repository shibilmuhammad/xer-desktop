const path = require('path');
const os = require('os');
const fs = require('fs');

const isWindows = os.platform() === 'win32';
const pythonPath = isWindows 
  ? path.join(__dirname, '..', 'venv_desktop', 'Scripts', 'python.exe')
  : path.join(__dirname, '..', 'venv_desktop', 'bin', 'python3');

console.log(`Starting backend with: ${pythonPath}`);

if (!fs.existsSync(pythonPath)) {
  console.error(`\nERROR: Python executable not found at: ${pythonPath}`);
  console.error(`Please ensure you have run 'setup_windows.bat' first.\n`);
  process.exit(1);
}

const { spawn } = require('child_process');
const backendDir = path.join(__dirname, '..', 'backend');

// Use shell: false to avoid issues with spaces in paths on Unix/Mac
// On Windows, shell: true might be needed for some environment variables or paths, 
// but for python.exe, false is generally safer if we provide the full path.
const backend = spawn(pythonPath, ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8000', '--reload'], {
  cwd: backendDir,
  stdio: 'inherit',
  shell: isWindows 
});

backend.stdout.on('data', (data) => {
  console.log(`[Backend-Out]: ${data}`);
});

backend.stderr.on('data', (data) => {
  console.error(`[Backend-Err]: ${data}`);
});

backend.on('error', (err) => {
  console.error('CRITICAL: Failed to start backend spawn:', err);
});

backend.on('exit', (code) => {
  if (code !== 0) {
    console.error(`\nCRITICAL: Backend process exited with code ${code}`);
    console.error(`This usually means a Python dependency is missing or there is a port conflict on 8000.`);
    console.error(`Try running: venv_desktop\\Scripts\\python.exe -m pip install -r backend/requirements.txt\n`);
  }
});

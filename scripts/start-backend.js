const { spawn } = require('child_process');
const path = require('path');
const os = require('os');

const isWindows = os.platform() === 'win32';
const pythonPath = isWindows 
  ? path.join(__dirname, '..', 'venv_desktop', 'Scripts', 'python.exe')
  : path.join(__dirname, '..', 'venv_desktop', 'bin', 'python3');

const backendDir = path.join(__dirname, '..', 'backend');

console.log(`Starting backend with: ${pythonPath}`);

const backend = spawn(pythonPath, ['-m', 'uvicorn', 'main:app', '--host', '0.0.0.0', '--port', '8000', '--reload'], {
  cwd: backendDir,
  stdio: 'inherit',
  shell: true
});

backend.on('error', (err) => {
  console.error('Failed to start backend:', err);
});

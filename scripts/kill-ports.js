// scripts/kill-ports.js
// Kills any stale processes on dev ports before starting
const { execSync } = require('child_process');
const net = require('net');

const PORTS = [8000, 5173];
const isWindows = process.platform === 'win32';

function killPort(port) {
  try {
    if (isWindows) {
      const result = execSync(`netstat -ano | findstr :${port}`, { encoding: 'utf8' }).trim();
      const pids = new Set();
      result.split('\n').forEach(line => {
        const parts = line.trim().split(/\s+/);
        const pid = parts[parts.length - 1];
        if (pid && !isNaN(pid) && parseInt(pid) > 0) pids.add(pid);
      });
      pids.forEach(pid => {
        try { execSync(`taskkill /F /PID ${pid}`, { stdio: 'ignore' }); } catch(e) {}
      });
    } else {
      execSync(`lsof -ti tcp:${port} | xargs kill -9 2>/dev/null || true`, { shell: true, stdio: 'ignore' });
    }
    console.log(`✓ Cleared port ${port}`);
  } catch(e) {
    console.log(`  Port ${port} was already free`);
  }
}

console.log('Clearing dev ports...');
PORTS.forEach(killPort);

// Give OS time to fully release ports
setTimeout(() => {
  console.log('Ports cleared. Starting dev servers...\n');
}, 1000);

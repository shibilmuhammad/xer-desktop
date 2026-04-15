const http = require('http');
http.get('http://127.0.0.1:5173', (res) => {
  console.log("127.0.0.1 responding with:", res.statusCode);
}).on('error', (e) => {
  console.log("127.0.0.1 failed:", e.message);
});
http.get('http://localhost:5173', (res) => {
  console.log("localhost responding with:", res.statusCode);
}).on('error', (e) => {
  console.log("localhost failed:", e.message);
});

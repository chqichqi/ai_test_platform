const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = 3000;

const MIME_TYPES = {
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon'
};

const server = http.createServer((req, res) => {
  console.log(`${req.method} ${req.url}`);
  
  // 默认页面
  let filePath = req.url === '/' ? '/index.html' : req.url;
  filePath = path.join(__dirname, 'public', filePath);
  
  const extname = path.extname(filePath);
  const contentType = MIME_TYPES[extname] || 'text/plain';
  
  fs.readFile(filePath, (error, content) => {
    if (error) {
      if (error.code === 'ENOENT') {
        // 文件不存在，返回index.html（用于React路由）
        fs.readFile(path.join(__dirname, 'public', 'index.html'), (err, html) => {
          if (err) {
            res.writeHead(500);
            res.end('Server Error');
          } else {
            res.writeHead(200, { 'Content-Type': 'text/html' });
            res.end(html, 'utf-8');
          }
        });
      } else {
        res.writeHead(500);
        res.end('Server Error: ' + error.code);
      }
    } else {
      res.writeHead(200, { 'Content-Type': contentType });
      res.end(content, 'utf-8');
    }
  });
});

server.listen(PORT, () => {
  console.log(`🎉 AI Agent Test Platform is running!`);
  console.log(`👉 Open your browser and go to: http://localhost:${PORT}`);
  console.log(`📁 Serving from: ${path.join(__dirname, 'public')}`);
  console.log(`\n📋 Available pages:`);
  console.log(`   • http://localhost:${PORT}/ - Dashboard`);
  console.log(`   • http://localhost:${PORT}/#login - Login Page`);
  console.log(`   • http://localhost:${PORT}/#dashboard - Dashboard`);
  console.log(`   • http://localhost:${PORT}/#rag - RAG Testing`);
  console.log(`   • http://localhost:${PORT}/#skills - SKILLS Management`);
  console.log(`   • http://localhost:${PORT}/#tests - Automated Testing`);
  console.log(`   • http://localhost:${PORT}/#reports - Reports`);
  console.log(`   • http://localhost:${PORT}/#settings - Settings`);
  console.log(`\n🚀 Press Ctrl+C to stop the server`);
});
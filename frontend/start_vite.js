import { exec } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

console.log('🚀 Starting AI Agent Test Platform with Vite...');

// 检查是否安装了vite
const checkVite = exec('npm list vite', { cwd: __dirname }, (error, stdout, stderr) => {
  if (error || stderr.includes('npm ERR!')) {
    console.log('📦 Installing Vite and dependencies...');
    
    // 安装vite和react插件
    const install = exec('npm install vite @vitejs/plugin-react --save-dev', { cwd: __dirname }, (installError, installStdout, installStderr) => {
      if (installError) {
        console.error('❌ Installation failed:', installError.message);
        console.log('Trying alternative installation method...');
        
        // 尝试使用更简单的方法
        const simpleInstall = exec('npm install vite@latest @vitejs/plugin-react@latest --no-optional --legacy-peer-deps', 
          { cwd: __dirname }, 
          (simpleError, simpleStdout, simpleStderr) => {
            if (simpleError) {
              console.error('❌ Simple installation also failed');
              startFallbackServer();
            } else {
              console.log('✅ Vite installed successfully');
              startDevServer();
            }
          }
        );
        
        simpleInstall.stdout.on('data', (data) => {
          console.log(data.toString());
        });
      } else {
        console.log('✅ Vite installed successfully');
        startDevServer();
      }
    });
    
    install.stdout.on('data', (data) => {
      console.log(data.toString());
    });
  } else {
    console.log('✅ Vite is already installed');
    startDevServer();
  }
});

function startDevServer() {
  console.log('🚀 Starting development server...');
  
  // 使用npx启动vite
  const vite = exec('npx vite', { cwd: __dirname });
  
  vite.stdout.on('data', (data) => {
    console.log(data.toString());
    
    // 检测服务器启动成功
    if (data.toString().includes('Local:')) {
      console.log('\n🎉 AI Agent Test Platform is running!');
      console.log('👉 Open your browser and go to: http://localhost:3000');
    }
  });
  
  vite.stderr.on('data', (data) => {
    console.error(data.toString());
  });
  
  vite.on('close', (code) => {
    console.log(`Vite process exited with code ${code}`);
  });
}

function startFallbackServer() {
  console.log('🔄 Starting fallback development server...');
  
  // 创建简单的Express服务器
  const expressCode = `
    const express = require('express');
    const path = require('path');
    const app = express();
    const port = 3000;
    
    // 提供静态文件
    app.use(express.static(path.join(__dirname, 'public')));
    
    // 所有路由返回index.html
    app.get('*', (req, res) => {
      res.sendFile(path.join(__dirname, 'public', 'index.html'));
    });
    
    app.listen(port, () => {
      console.log(\`🎉 AI Agent Test Platform running at http://localhost:\${port}\`);
      console.log('👉 Open this URL in your browser to see the application');
    });
  `;
  
  // 写入Express服务器文件
  const fs = require('fs');
  fs.writeFileSync(join(__dirname, 'server.js'), expressCode);
  
  // 安装express
  console.log('📦 Installing Express for fallback server...');
  const installExpress = exec('npm install express --no-optional', { cwd: __dirname }, (error) => {
    if (error) {
      console.error('❌ Failed to install Express');
      console.log('📋 Creating simple HTML demo instead...');
      createSimpleDemo();
    } else {
      console.log('✅ Express installed');
      
      // 启动Express服务器
      const server = exec('node server.js', { cwd: __dirname });
      server.stdout.on('data', (data) => console.log(data.toString()));
      server.stderr.on('data', (data) => console.error(data.toString()));
    }
  });
}

function createSimpleDemo() {
  console.log('📋 Creating standalone demo...');
  
  // 复制demo.html到public目录
  const fs = require('fs');
  const demoContent = fs.readFileSync(join(__dirname, 'demo.html'), 'utf8');
  fs.writeFileSync(join(__dirname, 'public', 'index.html'), demoContent);
  
  console.log('✅ Demo created at public/index.html');
  console.log('👉 Open file://' + join(__dirname, 'public', 'index.html') + ' in your browser');
}

checkVite.stdout.on('data', (data) => {
  console.log(data.toString());
});
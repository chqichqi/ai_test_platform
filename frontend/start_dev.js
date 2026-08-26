// 简单的开发服务器启动脚本
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

console.log('🚀 AI Agent测试平台 - 开发服务器启动');
console.log('====================================');

// 检查依赖
const nodeModules = path.join(__dirname, 'node_modules');
if (!fs.existsSync(nodeModules)) {
  console.log('❌ node_modules 目录不存在');
  console.log('请先运行: npm install');
  process.exit(1);
}

// 检查react-scripts
const reactScripts = path.join(nodeModules, 'react-scripts');
if (!fs.existsSync(reactScripts)) {
  console.log('❌ react-scripts 未安装');
  console.log('请运行: npm install react-scripts');
  process.exit(1);
}

console.log('✅ 依赖检查通过');
console.log('📦 启动开发服务器...');
console.log('🌐 访问地址: http://localhost:3000');
console.log('🛑 按 Ctrl+C 停止服务器');
console.log('====================================');

// 启动开发服务器
const child = spawn('node', [
  path.join(reactScripts, 'bin', 'react-scripts.js'),
  'start'
], {
  stdio: 'inherit',
  shell: true
});

child.on('error', (err) => {
  console.error('❌ 启动失败:', err.message);
  console.log('💡 尝试运行: npm install --force');
});

process.on('SIGINT', () => {
  console.log('\n🛑 停止服务器...');
  child.kill('SIGINT');
  process.exit(0);
});
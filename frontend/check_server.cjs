// 检查服务器状态
console.log('🔍 检查 AI Agent Test Platform 服务器状态...\n');

// 模拟浏览器访问
const http = require('http');

const options = {
  hostname: 'localhost',
  port: 3000,
  path: '/',
  method: 'GET',
  timeout: 5000
};

const req = http.request(options, (res) => {
  console.log(`✅ 服务器响应状态: ${res.statusCode}`);
  console.log(`📡 服务器地址: http://localhost:3000`);
  
  if (res.statusCode === 200) {
    console.log('\n🎉 服务器运行正常！');
    console.log('👉 请在浏览器中访问: http://localhost:3000');
    console.log('🔑 测试账号: admin@test.com / password');
  } else {
    console.log(`\n⚠️  服务器返回异常状态: ${res.statusCode}`);
  }
  
  let data = '';
  res.on('data', (chunk) => {
    data += chunk;
  });
  
  res.on('end', () => {
    // 检查是否是React应用
    if (data.includes('AI Agent Test Platform') || data.includes('React')) {
      console.log('📄 检测到 React 应用页面');
    }
    
    console.log('\n✅ 检查完成');
    console.log('\n📋 下一步:');
    console.log('1. 打开浏览器（Chrome/Firefox/Edge）');
    console.log('2. 访问 http://localhost:3000');
    console.log('3. 使用测试账号登录：');
    console.log('   - 邮箱: admin@test.com');
    console.log('   - 密码: password');
    console.log('4. 探索所有12个功能页面');
    console.log('\n📁 备用测试页面: http://localhost:3000/test.html');
  });
});

req.on('error', (e) => {
  console.log(`❌ 连接失败: ${e.message}`);
  console.log('\n🔧 解决方案:');
  console.log('1. 启动服务器: cd frontend && node server.cjs');
  console.log('2. 检查端口: netstat -ano | findstr :3000');
  console.log('3. 如果端口被占用，结束进程: taskkill /F /IM node.exe');
  console.log('4. 重新启动服务器');
});

req.on('timeout', () => {
  console.log('⏰ 请求超时，服务器可能未启动');
  console.log('请运行: cd frontend && node server.cjs');
  req.destroy();
});

req.end();
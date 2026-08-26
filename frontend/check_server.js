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
  console.log(`📊 响应头: ${JSON.stringify(res.headers, null, 2)}`);
  
  if (res.statusCode === 200) {
    console.log('\n🎉 服务器运行正常！');
    console.log('👉 请在浏览器中访问: http://localhost:3000');
    console.log('🔑 测试账号: admin@test.com / password');
  } else {
    console.log(`\n⚠️  服务器返回异常状态: ${res.statusCode}`);
  }
  
  res.on('data', (chunk) => {
    // 只显示前100个字符
    const content = chunk.toString().substring(0, 100);
    console.log(`📄 页面内容预览: ${content}...`);
  });
  
  res.on('end', () => {
    console.log('\n✅ 检查完成');
    console.log('\n📋 下一步:');
    console.log('1. 打开浏览器');
    console.log('2. 访问 http://localhost:3000');
    console.log('3. 使用测试账号登录');
    console.log('4. 探索所有12个功能页面');
  });
});

req.on('error', (e) => {
  console.log(`❌ 连接失败: ${e.message}`);
  console.log('\n🔧 解决方案:');
  console.log('1. 确保服务器已启动: cd frontend && node server.cjs');
  console.log('2. 检查端口3000是否被占用: netstat -ano | findstr :3000');
  console.log('3. 检查防火墙设置');
});

req.on('timeout', () => {
  console.log('⏰ 请求超时，服务器可能未启动或端口被阻止');
  req.destroy();
});

req.end();
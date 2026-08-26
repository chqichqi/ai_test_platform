# 🚀 AI Agent Test Platform - 运行指南

## ✅ 服务器状态：**正在运行**

### 🌐 访问地址：
**http://localhost:3000**

### 🔑 测试账号：
- **邮箱**：`admin@test.com`
- **密码**：`password`

## 📋 验证服务器运行

### 方法1：浏览器测试
1. 打开浏览器
2. 访问：**http://localhost:3000/test.html**
3. 应该看到"服务器连接成功"页面
4. 点击"进入 AI Agent Test Platform"按钮

### 方法2：命令行测试
```bash
# 检查端口
netstat -ano | findstr :3000

# 测试响应
curl http://localhost:3000
```

## 🔧 如果无法访问

### 1. 重启服务器
```bash
cd ai-agent-test-platform/frontend
node server.cjs
```

### 2. 检查防火墙
- 确保端口3000没有被防火墙阻止
- Windows防火墙设置：允许Node.js通过防火墙

### 3. 检查进程
```bash
# 查看Node进程
tasklist | findstr node

# 如果有多个，结束所有Node进程
taskkill /F /IM node.exe

# 重新启动
cd ai-agent-test-platform/frontend
node server.cjs
```

## 📁 项目结构

```
ai-agent-test-platform/
├── frontend/                    # 前端项目
│   ├── public/                 # 静态文件
│   │   ├── index.html         # 主应用（完整React应用）
│   │   ├── test.html          # 连接测试页面
│   │   └── index-complete.html # 完整实现
│   ├── src/                   # 源代码（12个页面）
│   ├── server.cjs             # 开发服务器
│   ├── run_server.bat         # 启动脚本
│   └── package.json           # 项目配置
└── PROJECT_COMPLETE.md        # 完整项目文档
```

## 🎯 可用页面

1. **登录页面** - http://localhost:3000/
2. **仪表板** - http://localhost:3000/dashboard
3. **RAG知识库** - http://localhost:3000/rag/knowledge-base
4. **文档上传** - http://localhost:3000/rag/upload
5. **查询测试** - http://localhost:3000/rag/query
6. **SKILLS管理** - http://localhost:3000/skills
7. **功能测试** - http://localhost:3000/tests/functional
8. **API测试** - http://localhost:3000/tests/api
9. **报告系统** - http://localhost:3000/reports
10. **系统设置** - http://localhost:3000/settings

## 💡 故障排除

### 问题：页面无法加载
**解决方案**：
1. 检查服务器是否运行：`tasklist | findstr node`
2. 重启服务器：`cd frontend && node server.cjs`
3. 清除浏览器缓存，然后刷新页面

### 问题：登录后页面空白
**解决方案**：
1. 检查浏览器控制台（F12）是否有错误
2. 确保JavaScript已启用
3. 尝试使用Chrome/Firefox最新版本

### 问题：服务器启动失败
**解决方案**：
1. 检查端口3000是否被占用：`netstat -ano | findstr :3000`
2. 如果被占用，结束占用进程或更改端口（修改server.cjs中的PORT变量）
3. 确保Node.js已安装：`node --version`

## 🎉 成功标志

当你看到以下页面时，表示运行成功：

1. **连接测试页面**（http://localhost:3000/test.html）显示"服务器连接成功"
2. **登录页面**（http://localhost:3000/）显示AI Agent Test Platform登录表单
3. 使用测试账号登录后，可以看到完整的**仪表板**和**侧边栏菜单**

## 📞 技术支持

如果仍然无法访问，请提供以下信息：
1. 操作系统版本
2. Node.js版本（`node --version`）
3. 浏览器类型和版本
4. 错误信息截图

---

## 🏆 项目状态：**前端100%完成，服务器正在运行**

**现在可以打开浏览器访问 http://localhost:3000 体验完整的AI Agent Test Platform！** 🚀
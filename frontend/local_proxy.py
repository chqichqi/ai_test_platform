#!/usr/bin/env python3
"""
本地代理服务器 - 解决CORS问题
运行此脚本后，可以通过 http://localhost:8080 访问后端API
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import requests
import json

class CORSProxyHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        """处理预检请求"""
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()
    
    def do_GET(self):
        """处理GET请求"""
        try:
            # 解析请求路径
            parsed_path = urlparse(self.path)
            
            if parsed_path.path == '/':
                # 返回前端页面
                self.serve_frontend()
                return
            elif parsed_path.path == '/health':
                # 直接转发到后端
                backend_url = 'http://localhost:8000/health'
            else:
                # 转发API请求
                backend_url = f'http://localhost:8000{parsed_path.path}'
                if parsed_path.query:
                    backend_url += f'?{parsed_path.query}'
            
            # 转发请求到后端
            response = requests.get(backend_url, headers=self.get_forward_headers())
            
            # 返回响应
            self.send_response(response.status_code)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(response.content)
            
        except Exception as e:
            self.send_error(500, f'Proxy error: {str(e)}')
    
    def do_POST(self):
        """处理POST请求"""
        try:
            # 读取请求体
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length else b''
            
            # 解析请求路径
            parsed_path = urlparse(self.path)
            backend_url = f'http://localhost:8000{parsed_path.path}'
            
            # 转发请求到后端
            response = requests.post(
                backend_url,
                data=body,
                headers=self.get_forward_headers()
            )
            
            # 返回响应
            self.send_response(response.status_code)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(response.content)
            
        except Exception as e:
            self.send_error(500, f'Proxy error: {str(e)}')
    
    def serve_frontend(self):
        """提供前端页面"""
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>AI Agent Test Platform - Local Proxy</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; }
                h1 { color: #333; }
                .container { max-width: 800px; margin: 0 auto; }
                .card { background: #f5f5f5; padding: 20px; border-radius: 10px; margin: 20px 0; }
                .btn { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }
                .btn:hover { background: #0056b3; }
                .result { background: #333; color: white; padding: 15px; border-radius: 5px; margin-top: 10px; font-family: monospace; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🤖 AI Agent 测试平台 - 本地代理</h1>
                <p>此页面通过本地代理访问后端API，解决了CORS问题。</p>
                
                <div class="card">
                    <h3>测试后端连接</h3>
                    <button class="btn" onclick="testHealth()">测试健康状态</button>
                    <div id="healthResult" class="result">点击按钮测试...</div>
                </div>
                
                <div class="card">
                    <h3>用户登录</h3>
                    <input type="text" id="username" placeholder="用户名" value="admin" style="padding: 10px; margin: 5px; width: 200px;"><br>
                    <input type="password" id="password" placeholder="密码" value="admin123" style="padding: 10px; margin: 5px; width: 200px;"><br>
                    <button class="btn" onclick="login()">登录</button>
                    <div id="loginResult" class="result">点击按钮登录...</div>
                </div>
                
                <div class="card">
                    <h3>直接访问</h3>
                    <p>也可以通过以下地址直接访问：</p>
                    <ul>
                        <li><a href="http://localhost:8000/docs" target="_blank">API文档</a></li>
                        <li><a href="http://localhost:8000/health" target="_blank">健康检查</a></li>
                    </ul>
                </div>
            </div>
            
            <script>
                async function testHealth() {
                    const result = document.getElementById('healthResult');
                    result.textContent = '请求中...';
                    
                    try {
                        const response = await fetch('/health');
                        const data = await response.json();
                        result.textContent = JSON.stringify(data, null, 2);
                    } catch (error) {
                        result.textContent = '错误: ' + error.message;
                    }
                }
                
                async function login() {
                    const username = document.getElementById('username').value;
                    const password = document.getElementById('password').value;
                    const result = document.getElementById('loginResult');
                    result.textContent = '登录中...';
                    
                    try {
                        const response = await fetch('/api/v1/auth/login', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({
                                username: username,
                                password: password
                            })
                        });
                        
                        const data = await response.json();
                        result.textContent = JSON.stringify(data, null, 2);
                    } catch (error) {
                        result.textContent = '错误: ' + error.message;
                    }
                }
                
                // 页面加载时自动测试
                window.addEventListener('load', () => {
                    setTimeout(testHealth, 1000);
                });
            </script>
        </body>
        </html>
        """
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html_content.encode('utf-8'))
    
    def send_cors_headers(self):
        """发送CORS头"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.send_header('Access-Control-Allow-Credentials', 'true')
    
    def get_forward_headers(self):
        """获取转发头"""
        headers = {}
        # 复制相关头
        for key in ['Content-Type', 'Authorization', 'Accept']:
            if key in self.headers:
                headers[key] = self.headers[key]
        return headers
    
    def log_message(self, format, *args):
        """简化日志输出"""
        print(f"[{self.address_string()}] {format % args}")

def run_server(port=8080):
    """运行代理服务器"""
    server_address = ('', port)
    httpd = HTTPServer(server_address, CORSProxyHandler)
    print(f"🚀 本地代理服务器启动在 http://localhost:{port}")
    print(f"📡 代理后端地址: http://localhost:8000")
    print(f"🌐 前端访问地址: http://localhost:{port}")
    print("按 Ctrl+C 停止服务器")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 服务器停止")
    finally:
        httpd.server_close()

if __name__ == '__main__':
    run_server()
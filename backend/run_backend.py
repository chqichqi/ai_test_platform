"""
稳定启动后端
"""

import subprocess
import time
import sys
import os

def start_backend():
    print("Starting AI Agent Test Platform Backend...")
    print(f"Working directory: {os.getcwd()}")
    
    # 启动命令
    cmd = [
        sys.executable,  # 使用当前Python解释器
        "-m", "uvicorn",
        "simple_run:app",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--reload",
        "--log-level", "info"
    ]
    
    print(f"Command: {' '.join(cmd)}")
    print("API Server: http://localhost:8000")
    print("API Docs: http://localhost:8000/docs")
    print("Frontend: http://localhost:3000")
    print("\nAvailable endpoints:")
    print("  • GET  /              - Welcome page")
    print("  • GET  /health        - Health check")
    print("  • GET  /docs          - API documentation")
    print("  • POST /api/v1/auth/login - User login")
    print("  • GET  /api/v1/auth/me   - Get current user")
    print("  • GET  /api/v1/rag/documents - Get documents")
    print("  • POST /api/v1/rag/query - Query documents")
    print("  • GET  /api/v1/skills    - Get SKILLS")
    print("  • GET  /api/v1/tests/functional - Get functional tests")
    print("  • GET  /api/v1/tests/api - Get API tests")
    print("  • GET  /api/v1/reports   - Get reports")
    print("\nTest credentials:")
    print("  • Username: admin")
    print("  • Password: password")
    print("\nStarting server...")
    
    try:
        # 启动进程
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        # 读取输出
        for line in iter(process.stdout.readline, ''):
            print(line.strip())
            if "Uvicorn running on" in line:
                print("\n✅ Backend server is running!")
                print("👉 Open http://localhost:8000/docs to view API documentation")
                print("👉 Open http://localhost:3000 to access the frontend")
                print("\n🛑 Press Ctrl+C to stop the server")
            
            # 检查进程是否结束
            if process.poll() is not None:
                break
        
        process.wait()
        
    except KeyboardInterrupt:
        print("\n🛑 Stopping server...")
        if process:
            process.terminate()
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    start_backend()
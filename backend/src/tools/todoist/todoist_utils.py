import uuid
import webbrowser
import json
import os
import http.server
import socketserver
import urllib.parse
import threading
import requests
from todoist_api_python.api import TodoistAPI
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent.parent.parent.parent  # 根据实际层级调整
sys.path.insert(0, str(project_root))


# 配置信息
CLIENT_ID = "51a2cc86b26944e68ef3f68fde8eb887"
CLIENT_SECRET = "668e2e56b26d4697b423cb2a180bc698"
current_dir = Path(__file__).resolve().parents[3]  # 向上三级到 backend 目录
TOKEN_FILE = str(current_dir / "credentials" / "todoist_credentials.json")
REDIRECT_PORT = 8080
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"
TODOIST_OAUTH_BASE = "https://todoist.com/oauth"

# 全局变量存储code
auth_code = None
auth_state = None

class AuthHandler(http.server.BaseHTTPRequestHandler):
    """处理授权回调的HTTP服务器"""
    def do_GET(self):
        global auth_code, auth_state
        
        # 解析URL
        parsed_url = urllib.parse.urlparse(self.path)
        if parsed_url.path == '/callback':
            # 提取code和state
            query_params = urllib.parse.parse_qs(parsed_url.query)
            auth_code = query_params.get('code', [None])[0]
            auth_state = query_params.get('state', [None])[0]
            
            # 返回成功页面
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write('''
                <html>
                <head><title>Authorization Success</title></head>
                <body>
                    <h1>Authorization Success!</h1>
                    <p>Close this window and return to the terminal.</p>
                </body>
                </html>
            '''.encode('utf-8'))

def start_auth_server():
    """启动本地HTTP服务器接收授权回调"""
    with socketserver.TCPServer(("", REDIRECT_PORT), AuthHandler) as httpd:
        httpd.handle_request()

def get_authentication_url(client_id, scopes, state):
    """构建授权URL"""
    from urllib.parse import urlencode
    endpoint = f"{TODOIST_OAUTH_BASE}/authorize"
    query = {
        "client_id": client_id,
        "scope": ",".join(scopes),
        "state": state,
    }
    return f"{endpoint}?{urlencode(query)}"

def exchange_code_for_token(code):
    """交换授权码获取访问令牌"""
    url = f"{TODOIST_OAUTH_BASE}/access_token"
    
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': code,
        'redirect_uri': REDIRECT_URI
    }
    
    print(f"正在交换授权码: {code}")
    print(f"请求URL: {url}")
    print(f"请求数据: {data}")
    
    try:
        response = requests.post(url, data=data)
        print(f"响应状态码: {response.status_code}")
        print(f"响应内容: {response.text}")
        
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"交换token时出错: {str(e)}")
        raise
    
def authenticate():
    state = str(uuid.uuid4())
    
    url = get_authentication_url(
        client_id=CLIENT_ID,
        scopes=["data:read", "task:add", "data:read_write"],
        state=state,
    )
    
    url += f"&redirect_uri={REDIRECT_URI}"
    
    server_thread = threading.Thread(target=start_auth_server)
    server_thread.daemon = True
    server_thread.start()
    
    webbrowser.open(url)
    
    server_thread.join(timeout=60)
    
    try:
        print("开始交换授权码获取token...")
        token_data = exchange_code_for_token(auth_code)
        
        print(f"获取到token数据: {token_data}")
        
        # 7. 保存token到文件
        save_data = {
            "access_token": token_data.get("access_token"),
            "token_type": token_data.get("token_type"),
            "expires_in": token_data.get("expires_in"),
            "state": state
        }
        
        # Ensure the credentials directory exists
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, indent=2, ensure_ascii=False)
            
    except Exception as e:
        print(f"\nAuthorization failed: {str(e)}")
        exit(1)
        
    return state
    

def main():
    with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
        try:
            token_data = json.load(f)
        except json.JSONDecodeError:
            authenticate()
            token_data = json.load(f)

        api = TodoistAPI(token_data['access_token'])
        

if __name__ == "__main__":
    main()
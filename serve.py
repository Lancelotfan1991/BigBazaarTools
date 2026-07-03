#!/usr/bin/env python3
"""本地数据查看服务器

启动后自动打开浏览器，加载 output 目录下的最新数据文件。
"""

import http.server
import json
import os
import socket
import socketserver
import webbrowser
from pathlib import Path

PORT = 8080
OUTPUT_DIR = "output"


class BazaarHandler(http.server.SimpleHTTPRequestHandler):
    """自定义请求处理器，提供数据 API"""

    def do_GET(self):
        if self.path == "/api/data":
            self._serve_latest_data()
        elif self.path == "/api/list":
            self._serve_file_list()
        else:
            super().do_GET()

    def _serve_latest_data(self):
        """返回最新的格式化数据 JSON"""
        data_dir = Path(OUTPUT_DIR)
        if not data_dir.exists():
            self._json_response({"error": "output 目录不存在，请先运行 python main.py 获取数据"}, 404)
            return

        json_files = list(data_dir.glob("*格式化数据*.json"))
        if not json_files:
            self._json_response({"error": "未找到数据文件，请先运行 python main.py 获取数据"}, 404)
            return

        latest = max(json_files, key=os.path.getctime)
        try:
            with open(latest, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._json_response(data)
        except Exception as e:
            self._json_response({"error": f"读取数据失败: {e}"}, 500)

    def _serve_file_list(self):
        """返回 output 目录下的所有数据文件列表"""
        data_dir = Path(OUTPUT_DIR)
        if not data_dir.exists():
            self._json_response([], 200)
            return

        files = []
        for f in sorted(data_dir.glob("*.json"), key=os.path.getctime, reverse=True):
            files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "modified": os.path.getctime(f),
            })
        self._json_response(files)

    def _json_response(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # 简化日志
        if "/api/" not in str(args[0]):
            super().log_message(format, *args)


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def main():
    os.chdir(Path(__file__).parent)

    port = find_free_port()

    with socketserver.TCPServer(("", port), BazaarHandler) as httpd:
        url = f"http://localhost:{port}/viewer.html"
        print(f"  🖥️  大巴扎数据查看器已启动")
        print(f"  📍 地址: {url}")
        print(f"  📁 数据目录: {os.path.abspath(OUTPUT_DIR)}")
        print(f"\n  按 Ctrl+C 停止服务器\n")

        webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\n  服务器已停止")


if __name__ == "__main__":
    main()

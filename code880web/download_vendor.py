"""Download frontend vendor libraries for offline use.

Run this script once after installation to enable offline mode:
    python code880web/download_vendor.py

Downloads Vue 3, Monaco Editor, and marked.js to code880web/static/vendor/.
"""

import os
import sys
import urllib.request
import zipfile
import shutil

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
VENDOR_DIR = os.path.join(STATIC_DIR, "vendor")

DOWNLOADS = [
    {
        "name": "vue.global.prod.js",
        "url": "https://unpkg.com/vue@3/dist/vue.global.prod.js",
        "dest": "vue.global.prod.js",
    },
    {
        "name": "marked.min.js",
        "url": "https://cdn.jsdelivr.net/npm/marked/marked.min.js",
        "dest": "marked.min.js",
    },
]

MONACO_BASE = "https://cdn.jsdelivr.net/npm/monaco-editor@0.47.0/min"
MONACO_FILES = [
    "vs/loader.js",
    "vs/editor/editor.main.js",
    "vs/editor/editor.main.css",
    "vs/editor/editor.main.nls.js",
    "vs/base/worker/workerMain.js",
    "vs/base/common/worker/simpleWorker.nls.js",
    "vs/basic-languages/python/python.js",
    "vs/basic-languages/javascript/javascript.js",
    "vs/basic-languages/typescript/typescript.js",
    "vs/basic-languages/json/json.js",
    "vs/basic-languages/html/html.js",
    "vs/basic-languages/css/css.js",
    "vs/basic-languages/markdown/markdown.js",
    "vs/basic-languages/yaml/yaml.js",
    "vs/basic-languages/xml/xml.js",
    "vs/basic-languages/bat/bat.js",
    "vs/basic-languages/powershell/powershell.js",
    "vs/basic-languages/shell/shell.js",
    "vs/basic-languages/sql/sql.js",
    "vs/basic-languages/ini/ini.js",
    "vs/language/json/jsonMode.js",
    "vs/language/json/jsonWorker.js",
]


def download_file(url: str, dest: str):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print(f"  下载: {url}")
    try:
        urllib.request.urlretrieve(url, dest)
    except Exception as e:
        print(f"  [WARN] 下载失败: {e}")


def main():
    print("Code880 Web 前端资源下载")
    print(f"目标目录: {VENDOR_DIR}")
    print()

    os.makedirs(VENDOR_DIR, exist_ok=True)

    for item in DOWNLOADS:
        dest = os.path.join(VENDOR_DIR, item["dest"])
        if os.path.isfile(dest):
            print(f"  已存在: {item['name']}")
            continue
        download_file(item["url"], dest)

    print()
    print("下载 Monaco Editor 核心文件...")
    for rel_path in MONACO_FILES:
        dest = os.path.join(VENDOR_DIR, "monaco", rel_path)
        if os.path.isfile(dest):
            continue
        download_file(f"{MONACO_BASE}/{rel_path}", dest)

    print()
    print("完成! 前端资源已下载到 vendor/ 目录。")
    print("index.html 会自动优先加载本地资源。")


if __name__ == "__main__":
    main()

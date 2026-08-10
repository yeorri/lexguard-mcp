#!/usr/bin/env python3
"""cwd와 무관하게 stdio MCP 서버를 실행하는 런처.

Claude Desktop 등 일부 클라이언트는 MCP 설정의 cwd를 적용하지 않아
`python -m src.stdio_server`가 ModuleNotFoundError로 즉시 죽는다.
이 런처는 자기 위치를 기준으로 sys.path와 작업 디렉터리를 맞춘 뒤 실행한다.

설정 예:
    "command": "<repo>/.venv/Scripts/python.exe",
    "args": ["<repo>/run_stdio.py"]
"""
import os
import runpy
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

runpy.run_module("src.stdio_server", run_name="__main__")

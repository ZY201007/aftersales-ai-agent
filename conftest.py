"""pytest 全局配置：确保从项目根目录导入 app / eval。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

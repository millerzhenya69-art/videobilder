"""
Локальный запуск: python run.py
Запускать из корня проекта: C:\...\videobilder-main> python run.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from bot.main import main
main()

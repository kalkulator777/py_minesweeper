#!/usr/bin/env python3
"""Офисная дота — запуск.

    python3 play.py

Поднимет сервер, откроет браузер и покажет матчи коллег в локальной сети.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from office_dota.launcher import main

if __name__ == "__main__":
    main()

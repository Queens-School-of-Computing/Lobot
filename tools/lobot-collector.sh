#!/bin/bash
# Launcher for lobot-collector service.
# WorkingDirectory must be /opt/Lobot/tools so lobot_tui is importable.
exec /opt/Lobot/tools/lobot_collector/.venv/bin/python3 -m lobot_collector

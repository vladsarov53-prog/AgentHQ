Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "D:\REDPEAK\Agent systems\AgentHQ\ai-news-bot"
WshShell.Run "D:\REDPEAK\Agent systems\AgentHQ\ai-news-bot\.venv\Scripts\pythonw.exe -m src.main", 0, False

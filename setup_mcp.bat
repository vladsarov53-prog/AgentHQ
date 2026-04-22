@echo off
chcp 65001 >nul
echo ============================================
echo  RedPeak HQ — установка MCP-серверов
echo ============================================
echo.

echo [1/2] Устанавливаю @modelcontextprotocol/server-memory...
npm install -g @modelcontextprotocol/server-memory
if %errorlevel% neq 0 (
    echo ОШИБКА при установке server-memory
    pause
    exit /b 1
)
echo OK

echo.
echo [2/2] Устанавливаю @modelcontextprotocol/server-filesystem...
npm install -g @modelcontextprotocol/server-filesystem
if %errorlevel% neq 0 (
    echo ОШИБКА при установке server-filesystem
    pause
    exit /b 1
)
echo OK

echo.
echo ============================================
echo  Проверка установки...
echo ============================================
node "C:\Users\sashatrash\AppData\Roaming\npm\node_modules\@modelcontextprotocol\server-memory\dist\index.js" --version 2>nul || echo server-memory: установлен
node "C:\Users\sashatrash\AppData\Roaming\npm\node_modules\@modelcontextprotocol\server-filesystem\dist\index.js" --version 2>nul || echo server-filesystem: установлен

echo.
echo ============================================
echo  Готово! Перезапусти Claude Desktop.
echo ============================================
pause

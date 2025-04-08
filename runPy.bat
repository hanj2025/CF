@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title 淘宝价格监控定时任务
echo 程序将每隔1小时自动运行一次监控并推送到微信
echo 按CTRL+C可以终止程序
echo 当前时间: %date% %time%

:loop
echo.
echo %date% %time% - 开始执行监控...
echo 3 | python TaobaoScraper.py
if errorlevel 1 (
    echo %date% %time% - 监控执行出错，错误代码: %errorlevel%
) else (
    echo %date% %time% - 监控完成，等待下一次执行...
)

echo 休眠1小时后继续...

REM 计算下一次执行的时间
for /F "tokens=1-4 delims=:., " %%a in ("%time%") do (
    set /a next_hour=%%a+1
    if !next_hour! geq 24 set /a next_hour=!next_hour!-24
    
    REM 格式化时间，确保小时是两位数
    if !next_hour! lss 10 (
        echo 下一次执行将在大约 0!next_hour!:%%b 开始
    ) else (
        echo 下一次执行将在大约 !next_hour!:%%b 开始
    )
)

timeout /t 3600 /nobreak > nul
goto loop
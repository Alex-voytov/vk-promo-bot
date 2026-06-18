@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

title Установка службы VK Promo Bot

echo ============================================
echo  Установка службы VK Promo Bot (Windows)
echo ============================================

:: Проверка прав администратора
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ОШИБКА] Запустите от имени администратора!
    pause
    exit /b 1
)

:: Путь к папке с ботом (текущая папка)
set BOT_DIR=%~dp0
set VENV_DIR=%BOT_DIR%venv
set SCRIPT=%BOT_DIR%bot.py
set SERVICE_NAME=VKPromoBot

:: Проверка наличия NSSM
if not exist "%BOT_DIR%nssm.exe" (
    echo [ОШИБКА] nssm.exe не найден в %BOT_DIR%
    echo Скачайте NSSM с https://nssm.cc/download и поместите в эту папку.
    pause
    exit /b 1
)

:: Проверка наличия Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ОШИБКА] Python не найден в PATH.
    pause
    exit /b 1
)

echo [1/4] Создание виртуального окружения...
if exist "%VENV_DIR%" (
    echo Виртуальное окружение уже существует, удаляю...
    rmdir /s /q "%VENV_DIR%"
)
python -m venv "%VENV_DIR%"
if %errorlevel% neq 0 (
    echo [ОШИБКА] Не удалось создать виртуальное окружение.
    pause
    exit /b 1
)

echo [2/4] Установка зависимостей...
call "%VENV_DIR%\Scripts\pip" install --upgrade pip >nul
call "%VENV_DIR%\Scripts\pip" install -r "%BOT_DIR%requirements.txt"
if %errorlevel% neq 0 (
    echo [ОШИБКА] Ошибка установки зависимостей.
    pause
    exit /b 1
)

echo [3/4] Настройка службы %SERVICE_NAME%...
:: Удаляем старую службу, если есть
"%BOT_DIR%nssm" remove %SERVICE_NAME% confirm >nul 2>&1
:: Устанавливаем новую (используем pythonw.exe для фонового запуска)
"%BOT_DIR%nssm" install %SERVICE_NAME% "%VENV_DIR%\Scripts\pythonw.exe" "%SCRIPT%"
if %errorlevel% neq 0 (
    echo [ОШИБКА] Не удалось установить службу.
    pause
    exit /b 1
)
"%BOT_DIR%nssm" set %SERVICE_NAME% AppDirectory "%BOT_DIR%"
"%BOT_DIR%nssm" set %SERVICE_NAME% Description "Бот для выдачи промокодов ВКонтакте"
"%BOT_DIR%nssm" set %SERVICE_NAME% Start SERVICE_AUTO_START
:: Перенаправление логов
if not exist "%BOT_DIR%logs" mkdir "%BOT_DIR%logs"
"%BOT_DIR%nssm" set %SERVICE_NAME% AppStdout "%BOT_DIR%logs\stdout.log"
"%BOT_DIR%nssm" set %SERVICE_NAME% AppStderr "%BOT_DIR%logs\stderr.log"
:: Настройка перезапуска
"%BOT_DIR%nssm" set %SERVICE_NAME% AppExit Default Restart
"%BOT_DIR%nssm" set %SERVICE_NAME% AppRestartDelay 10000

echo [4/4] Запуск службы...
"%BOT_DIR%nssm" start %SERVICE_NAME%
if %errorlevel% neq 0 (
    echo [ОШИБКА] Не удалось запустить службу. Проверьте логи в %BOT_DIR%logs\stderr.log
    pause
    exit /b 1
)

echo ============================================
echo Служба успешно установлена и запущена!
echo Проверьте: services.msc
echo Логи: %BOT_DIR%logs\
echo ============================================
pause
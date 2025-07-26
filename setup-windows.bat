@echo off
chcp 65001 > nul
title 🌳 日陰ルートアプリ - 自動セットアップ

echo.
echo ========================================
echo    🌳 日陰ルートアプリ 自動セットアップ
echo ========================================
echo.
echo このスクリプトが以下を自動で行います：
echo   ✅ 必要な依存関係のインストール
echo   ✅ バックエンドサーバーの起動
echo   ✅ フロントエンドサーバーの起動
echo   ✅ ブラウザでアプリを開く
echo.
pause

:: ログファイルの設定
set LOG_FILE=%~dp0setup.log
echo %date% %time% - セットアップ開始 > "%LOG_FILE%"

:: Python の確認
echo 🔍 Python の確認中...
python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python が見つかりません。
    echo    https://www.python.org/downloads/ からダウンロードしてください。
    echo    インストール時に「Add Python to PATH」にチェックを入れてください。
    pause
    exit /b 1
)
echo ✅ Python が見つかりました。

:: Node.js の確認
echo 🔍 Node.js の確認中...
node --version > nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Node.js が見つかりません。
    echo    https://nodejs.org/ からLTS版をダウンロードしてください。
    pause
    exit /b 1
)
echo ✅ Node.js が見つかりました。

:: バックエンドのセットアップ
echo.
echo 🔧 バックエンドのセットアップ中...
cd /d "%~dp0backend"
if not exist "main_optimized.py" (
    echo ❌ バックエンドファイルが見つかりません。
    pause
    exit /b 1
)

echo    依存関係をインストール中...
pip install fastapi uvicorn aiohttp aiofiles python-multipart >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python パッケージのインストールに失敗しました。
    echo    ログファイルを確認してください: %LOG_FILE%
    pause
    exit /b 1
)
echo ✅ バックエンドの準備完了

:: フロントエンドのセットアップ
echo.
echo 🎨 フロントエンドのセットアップ中...
cd /d "%~dp0frontend-pwa"
if not exist "package.json" (
    echo ❌ フロントエンドファイルが見つかりません。
    pause
    exit /b 1
)

echo    依存関係をインストール中...（時間がかかる場合があります）
call npm install >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
    echo ❌ npm install に失敗しました。
    echo    ログファイルを確認してください: %LOG_FILE%
    pause
    exit /b 1
)
echo ✅ フロントエンドの準備完了

:: サーバー起動用のバッチファイルを作成
echo.
echo 🚀 サーバー起動スクリプトを作成中...

:: バックエンド起動スクリプト
echo @echo off > "%~dp0start-backend.bat"
echo title 🔧 バックエンドサーバー - 日陰ルートアプリ >> "%~dp0start-backend.bat"
echo cd /d "%~dp0backend" >> "%~dp0start-backend.bat"
echo echo バックエンドサーバーを起動中... >> "%~dp0start-backend.bat"
echo echo http://localhost:8001 で稼働します >> "%~dp0start-backend.bat"
echo echo このウィンドウを閉じないでください >> "%~dp0start-backend.bat"
echo echo. >> "%~dp0start-backend.bat"
echo python main_optimized.py >> "%~dp0start-backend.bat"
echo pause >> "%~dp0start-backend.bat"

:: フロントエンド起動スクリプト
echo @echo off > "%~dp0start-frontend.bat"
echo title 🎨 フロントエンドサーバー - 日陰ルートアプリ >> "%~dp0start-frontend.bat"
echo cd /d "%~dp0frontend-pwa" >> "%~dp0start-frontend.bat"
echo echo フロントエンドサーバーを起動中... >> "%~dp0start-frontend.bat"
echo echo http://localhost:5176 で稼働します >> "%~dp0start-frontend.bat"
echo echo このウィンドウを閉じないでください >> "%~dp0start-frontend.bat"
echo echo. >> "%~dp0start-frontend.bat"
echo call npm run dev >> "%~dp0start-frontend.bat"
echo pause >> "%~dp0start-frontend.bat"

:: 統合起動スクリプト
echo @echo off > "%~dp0start-app.bat"
echo title 🌳 日陰ルートアプリ - 起動 >> "%~dp0start-app.bat"
echo echo 🌳 日陰ルートアプリを起動中... >> "%~dp0start-app.bat"
echo echo. >> "%~dp0start-app.bat"
echo echo ✅ バックエンドサーバーを起動中... >> "%~dp0start-app.bat"
echo start "バックエンド" "%~dp0start-backend.bat" >> "%~dp0start-app.bat"
echo timeout /t 3 /nobreak ^> nul >> "%~dp0start-app.bat"
echo echo ✅ フロントエンドサーバーを起動中... >> "%~dp0start-app.bat"
echo start "フロントエンド" "%~dp0start-frontend.bat" >> "%~dp0start-app.bat"
echo echo. >> "%~dp0start-app.bat"
echo echo 🎉 起動完了！ >> "%~dp0start-app.bat"
echo echo    バックエンド: http://localhost:8001 >> "%~dp0start-app.bat"
echo echo    フロントエンド: http://localhost:5176 >> "%~dp0start-app.bat"
echo echo. >> "%~dp0start-app.bat"
echo echo 📱 モバイルでアクセスする場合： >> "%~dp0start-app.bat"
echo for /f "tokens=2 delims=:" %%%%a in ('ipconfig ^| findstr "IPv4"') do set IP=%%%%a >> "%~dp0start-app.bat"
echo echo    http://%IP::=%:5176 >> "%~dp0start-app.bat"
echo echo. >> "%~dp0start-app.bat"
echo timeout /t 5 /nobreak ^> nul >> "%~dp0start-app.bat"
echo start http://localhost:5176 >> "%~dp0start-app.bat"
echo echo アプリがブラウザで開きます... >> "%~dp0start-app.bat"
echo pause >> "%~dp0start-app.bat"

echo ✅ 起動スクリプトを作成しました

echo.
echo ========================================
echo         🎉 セットアップ完了！
echo ========================================
echo.
echo 今後のアプリ起動方法：
echo   📁 start-app.bat をダブルクリック
echo.
echo 個別起動の場合：
echo   🔧 start-backend.bat （バックエンドのみ）
echo   🎨 start-frontend.bat （フロントエンドのみ）
echo.
echo 今すぐアプリを起動しますか？ (Y/N)
set /p choice="選択してください: "
if /i "%choice%"=="Y" (
    echo アプリを起動中...
    call "%~dp0start-app.bat"
) else (
    echo セットアップが完了しました。
    echo start-app.bat をダブルクリックしてアプリを起動してください。
)

echo %date% %time% - セットアップ完了 >> "%LOG_FILE%"
pause
#!/bin/bash

# 🌳 日陰ルートアプリ - 自動セットアップスクリプト（Mac/Linux用）

# 色設定
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ログファイル設定
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/setup.log"

# ログ関数
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

# エラーハンドリング
error_exit() {
    echo -e "${RED}❌ エラー: $1${NC}"
    log "ERROR: $1"
    exit 1
}

# 成功メッセージ
success() {
    echo -e "${GREEN}✅ $1${NC}"
    log "SUCCESS: $1"
}

# 情報メッセージ
info() {
    echo -e "${BLUE}🔍 $1${NC}"
    log "INFO: $1"
}

# 警告メッセージ
warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
    log "WARNING: $1"
}

# ヘッダー表示
clear
echo -e "${CYAN}"
echo "========================================"
echo "   🌳 日陰ルートアプリ 自動セットアップ"
echo "========================================"
echo -e "${NC}"
echo
echo "このスクリプトが以下を自動で行います："
echo "  ✅ 必要な依存関係のインストール"
echo "  ✅ バックエンドサーバーの起動準備"
echo "  ✅ フロントエンドサーバーの起動準備"
echo "  ✅ 起動スクリプトの作成"
echo

# 初期化
log "セットアップ開始"

# OS検出
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="mac"
    echo -e "${PURPLE}🍎 macOS が検出されました${NC}"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
    echo -e "${PURPLE}🐧 Linux が検出されました${NC}"
else
    error_exit "未対応のOSです: $OSTYPE"
fi

echo
read -p "続行しますか？ (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "セットアップを中止しました。"
    exit 0
fi

# Python確認
info "Python の確認中..."
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
    success "Python3 が見つかりました: $(python3 --version)"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
    success "Python が見つかりました: $(python --version)"
else
    error_exit "Python が見つかりません。https://www.python.org/downloads/ からインストールしてください。"
fi

# pip確認
info "pip の確認中..."
if command -v pip3 &> /dev/null; then
    PIP_CMD="pip3"
elif command -v pip &> /dev/null; then
    PIP_CMD="pip"
else
    error_exit "pip が見つかりません。Python と一緒にインストールされているはずです。"
fi
success "pip が見つかりました"

# Node.js確認
info "Node.js の確認中..."
if ! command -v node &> /dev/null; then
    warning "Node.js が見つかりません。"
    if [[ "$OS" == "mac" ]]; then
        echo "以下のいずれかでインストールしてください："
        echo "  • https://nodejs.org/ からダウンロード"
        echo "  • Homebrew: brew install node"
    else
        echo "以下のいずれかでインストールしてください："
        echo "  • https://nodejs.org/ からダウンロード"
        echo "  • パッケージマネージャー: sudo apt install nodejs npm"
    fi
    error_exit "Node.js をインストール後、再実行してください。"
fi
success "Node.js が見つかりました: $(node --version)"

# npm確認
if ! command -v npm &> /dev/null; then
    error_exit "npm が見つかりません。Node.js と一緒にインストールされているはずです。"
fi
success "npm が見つかりました: $(npm --version)"

# バックエンドセットアップ
echo
info "バックエンドのセットアップ中..."
cd "$SCRIPT_DIR/backend" || error_exit "backendディレクトリが見つかりません。"

if [[ ! -f "main_optimized.py" ]]; then
    error_exit "main_optimized.py が見つかりません。"
fi

info "Python 依存関係をインストール中..."
$PIP_CMD install fastapi uvicorn aiohttp aiofiles python-multipart >> "$LOG_FILE" 2>&1
if [[ $? -ne 0 ]]; then
    error_exit "Python パッケージのインストールに失敗しました。ログを確認してください: $LOG_FILE"
fi
success "バックエンドの準備完了"

# フロントエンドセットアップ
echo
info "フロントエンドのセットアップ中..."
cd "$SCRIPT_DIR/frontend-pwa" || error_exit "frontend-pwaディレクトリが見つかりません。"

if [[ ! -f "package.json" ]]; then
    error_exit "package.json が見つかりません。"
fi

info "npm 依存関係をインストール中...（時間がかかる場合があります）"
npm install >> "$LOG_FILE" 2>&1
if [[ $? -ne 0 ]]; then
    error_exit "npm install に失敗しました。ログを確認してください: $LOG_FILE"
fi
success "フロントエンドの準備完了"

# 起動スクリプト作成
echo
info "起動スクリプトを作成中..."

# バックエンド起動スクリプト
cat > "$SCRIPT_DIR/start-backend.sh" << 'EOF'
#!/bin/bash
echo "🔧 バックエンドサーバーを起動中..."
echo "http://localhost:8001 で稼働します"
echo "このターミナルを閉じないでください"
echo

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/backend"

# Python コマンドを決定
if command -v python3 &> /dev/null; then
    python3 main_optimized.py
elif command -v python &> /dev/null; then
    python main_optimized.py
else
    echo "❌ Python が見つかりません"
    exit 1
fi
EOF

# フロントエンド起動スクリプト
cat > "$SCRIPT_DIR/start-frontend.sh" << 'EOF'
#!/bin/bash
echo "🎨 フロントエンドサーバーを起動中..."
echo "http://localhost:5176 で稼働します"
echo "このターミナルを閉じないでください"
echo

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/frontend-pwa"
npm run dev
EOF

# 統合起動スクリプト
cat > "$SCRIPT_DIR/start-app.sh" << 'EOF'
#!/bin/bash

# 色設定
GREEN='\033[0;32m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}🌳 日陰ルートアプリを起動中...${NC}"
echo

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# バックエンド起動
echo -e "${GREEN}✅ バックエンドサーバーを起動中...${NC}"
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOSの場合
    osascript -e 'tell application "Terminal" to do script "'"$SCRIPT_DIR/start-backend.sh"'"' &
else
    # Linuxの場合
    if command -v gnome-terminal &> /dev/null; then
        gnome-terminal -- bash -c "$SCRIPT_DIR/start-backend.sh; exec bash" &
    elif command -v xterm &> /dev/null; then
        xterm -e "bash $SCRIPT_DIR/start-backend.sh" &
    else
        echo "新しいターミナルでバックエンドを起動してください:"
        echo "  bash $SCRIPT_DIR/start-backend.sh"
    fi
fi

sleep 3

# フロントエンド起動
echo -e "${GREEN}✅ フロントエンドサーバーを起動中...${NC}"
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOSの場合
    osascript -e 'tell application "Terminal" to do script "'"$SCRIPT_DIR/start-frontend.sh"'"' &
else
    # Linuxの場合
    if command -v gnome-terminal &> /dev/null; then
        gnome-terminal -- bash -c "$SCRIPT_DIR/start-frontend.sh; exec bash" &
    elif command -v xterm &> /dev/null; then
        xterm -e "bash $SCRIPT_DIR/start-frontend.sh" &
    else
        echo "新しいターミナルでフロントエンドを起動してください:"
        echo "  bash $SCRIPT_DIR/start-frontend.sh"
    fi
fi

echo
echo -e "${PURPLE}🎉 起動完了！${NC}"
echo "   バックエンド: http://localhost:8001"
echo "   フロントエンド: http://localhost:5176"
echo

# IPアドレス取得（モバイルアクセス用）
if command -v ifconfig &> /dev/null; then
    IP=$(ifconfig | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1' | head -1)
elif command -v ip &> /dev/null; then
    IP=$(ip route get 1 | awk '{print $NF;exit}')
fi

if [[ -n "$IP" ]]; then
    echo -e "${BLUE}📱 モバイルでアクセスする場合：${NC}"
    echo "   http://$IP:5176"
    echo
fi

echo "5秒後にブラウザでアプリを開きます..."
sleep 5

# ブラウザで開く
if [[ "$OSTYPE" == "darwin"* ]]; then
    open http://localhost:5176
else
    if command -v xdg-open &> /dev/null; then
        xdg-open http://localhost:5176
    elif command -v firefox &> /dev/null; then
        firefox http://localhost:5176 &
    elif command -v chromium-browser &> /dev/null; then
        chromium-browser http://localhost:5176 &
    else
        echo "ブラウザで http://localhost:5176 を開いてください"
    fi
fi

echo "アプリがブラウザで開きます..."
EOF

# 実行権限付与
chmod +x "$SCRIPT_DIR/start-backend.sh"
chmod +x "$SCRIPT_DIR/start-frontend.sh"
chmod +x "$SCRIPT_DIR/start-app.sh"

success "起動スクリプトを作成しました"

# セットアップ完了
echo
echo -e "${CYAN}"
echo "========================================"
echo "        🎉 セットアップ完了！"
echo "========================================"
echo -e "${NC}"
echo
echo "今後のアプリ起動方法："
echo "  📁 ./start-app.sh"
echo
echo "個別起動の場合："
echo "  🔧 ./start-backend.sh （バックエンドのみ）"
echo "  🎨 ./start-frontend.sh （フロントエンドのみ）"
echo

log "セットアップ完了"

read -p "今すぐアプリを起動しますか？ (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "アプリを起動中..."
    bash "$SCRIPT_DIR/start-app.sh"
else
    echo "セットアップが完了しました。"
    echo "./start-app.sh を実行してアプリを起動してください。"
fi
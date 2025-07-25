# 🌳 Shade Route App - 日陰回避ルート検索アプリ

建物の影を考慮したルート検索アプリケーション。OpenStreetMapデータを使用してリアルタイムに日陰率を計算し、最適なルートを提案します。

## 🚀 主要機能

- **日陰回避ルート検索**: 建物の影を考慮した最適ルート計算
- **リアルタイム影計算**: 時刻に応じた動的な日陰率計算
- **建物可視化**: OpenStreetMapの建物データ表示
- **アメニティ表示**: 自販機・コンビニの位置表示
- **カスタムノード**: お気に入りの場所をマーク・永続保存
- **ダイクストラ法**: 最適化アルゴリズムによるルート計算
- **マルチ交通手段**: 徒歩・自転車・車対応

## 🛠️ 技術スタック

### Backend
- **Python FastAPI**: 高速なWeb APIフレームワーク
- **OpenStreetMap Overpass API**: 地図データ取得
- **NetworkX**: グラフ理論アルゴリズム
- **NumPy**: 数値計算

### Frontend  
- **React + TypeScript**: モダンなUIフレームワーク
- **Vite**: 高速ビルドツール
- **Leaflet**: インタラクティブ地図ライブラリ
- **PWA対応**: オフライン機能・アプリインストール

## 📦 セットアップ

### Backend起動
```bash
cd backend
pip install -r requirements_optimized.txt
python main_optimized.py
```

### Frontend起動
```bash
cd frontend-pwa
npm install
npm run dev
```

## 🌐 アクセス
- **Backend**: http://localhost:8001
- **Frontend**: http://localhost:5174

## 🗺️ 使用方法

1. **ルート検索**
   - 地図上で開始地点をタップ
   - 終了地点をタップ  
   - 「ルート計算」ボタンをクリック

2. **カスタムノード追加**
   - 「📌 ノード追加」ボタンをクリック
   - 地図上の好きな場所をタップ
   - ノード名・タイプ・説明を入力

3. **設定変更**
   - 交通手段選択（徒歩・自転車・車）
   - 建物表示ON/OFF
   - 時刻指定・自動更新

## 📊 データソース

- **地図**: OpenStreetMap
- **建物データ**: OpenStreetMap Building Layer  
- **アメニティ**: OpenStreetMap Overpass API
- **影計算**: 太陽位置計算アルゴリズム

## 🎯 対象エリア

現在は東京近郊エリアに対応。検索範囲は最大5kmまで。

## 🔧 開発者向け情報

### API エンドポイント
- `POST /api/route/shade-avoid`: 日陰回避ルート
- `POST /api/route/dijkstra`: ダイクストラ法ルート  
- `POST /api/route/compare`: ルート比較
- `GET /api/buildings`: 建物データ取得
- `GET /api/amenities`: アメニティデータ取得

### 設定ファイル
- `backend/config.py`: サーバー設定
- `frontend-pwa/vite.config.ts`: フロントエンド設定

## 📝 ライセンス

このプロジェクトはMITライセンスの下で公開されています。

## 🤝 コントリビューション

Issues・Pull Requestsを歓迎します！

---

**開発: Claude Code Assistant** 🤖
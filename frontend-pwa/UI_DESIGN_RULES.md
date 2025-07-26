# UI_DESIGN_RULES.md - Shade Route App (Frontend Only, Updated)

## 🎯 アプリの目的（UI視点）
- 建物の影や快適度を視覚的に示し、暑い日でも快適に歩ける地図UIを提供
- モバイルで片手操作に配慮した直感的ナビゲーション設計
- 状況・時間帯・アクセシビリティに応じた適応型UI

---

## 📱 ナビゲーション設計

### Bottom Navigation（3〜5タブ推奨）
- ナビゲーションは3〜5個まで：6個以上は誤操作のリスク増 :contentReference[oaicite:1]{index=1}
- iOS設計目安：アイコン25×25pt（小型なら18×18pt）、ラベルはSF 10pt Medium :contentReference[oaicite:2]{index=2}
- タッチターゲットは最低44×44px（理想は48～60px）を確保する :contentReference[oaicite:3]{index=3}
- メイン画面で常時表示、内部画面では非表示にしてスクロールで再表示も可 :contentReference[oaicite:4]{index=4}

### コンテキストUI（地図上）
- ナビタブではアクション操作を置かず、地図上に専用ボタンを設置する
- 影切り替えやズーム・現在地ボタンは適切に余白を設定して誤タップ防止 :contentReference[oaicite:5]{index=5}

---

## 🗺️ 地図とオーバーレイ UI

- 地図は画面の70‑80%を占有し、下部にボトムシートを配置
- マップコントロールには余白（padding/safe area）を確保して視認性と応答性を維持 :contentReference[oaicite:6]{index=6}
- ボトムシートは `collapsed`／`peek`／`expanded` の3段階を実装し、スワイプで操作可能
- レイヤートグルや時間スライダーはオン／オフ切り替え可能にし、視覚情報の重複を避ける :contentReference[oaicite:7]{index=7}

---

## 🎨 カラー & テーマ設計

```css
:root {
  --primary-cool: #2196F3;
  --shadow-medium: rgba(26, 26, 46, 0.5);
  --comfort-cool: #4FC3F7;
  --comfort-comfortable: #66BB6A;
  --comfort-warm: #FFCA28;
  --comfort-hot: #FF7043;
  --comfort-extreme: #E53935;
}
```
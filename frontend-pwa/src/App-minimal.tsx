// 最小限のテスト版
import React from 'react';

const App = () => {
  return (
    <div style={{ padding: '20px' }}>
      <h1>🔧 最小テスト</h1>
      <p>このページが表示されれば、基本的なReactは動作しています。</p>
      <button onClick={() => alert('ボタンテスト成功!')}>
        テストボタン
      </button>
    </div>
  );
};

export default App;
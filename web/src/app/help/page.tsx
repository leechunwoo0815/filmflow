export default function HelpPage() {
  return (
    <main className="max-w-4xl mx-auto p-8 text-txt">
      <a className="btn" href="/">← 首页</a>
      <h1 className="text-2xl font-bold mt-4 mb-4">帮助 · FilmFlow</h1>
      <section className="card p-4 mb-4">
        <h2 className="font-semibold mb-2">快捷键</h2>
        <ul className="text-sm space-y-1">
          <li><b>←/→</b> 审阅切换静帧</li>
          <li><b>1 / 2</b> 100% / 200%</li>
          <li><b>C</b> A/B 对比上一版</li>
          <li><b>空格</b> 时间轴播放（R3）</li>
        </ul>
      </section>
      <section className="card p-4 mb-4">
        <h2 className="font-semibold mb-2">Scene DSL 组件速查</h2>
        <p className="text-sm text-dim">paper-card · headline · body-block · stamp · arrow-grow · hand-pointer ·
          roller · halftone-field · registration-cross · evidence-card · chart-bar · count-up</p>
      </section>
      <section className="card p-4">
        <h2 className="font-semibold mb-2">常见 QA 错误</h2>
        <ul className="text-sm space-y-1">
          <li><b>E_FINAL_REQUIRED</b>：先跑 F02 final，不能用 review 交付。</li>
          <li><b>E_LICENSE_MISSING</b>：音频页填写音乐来源/许可/授权。</li>
          <li><b>E_PROGRAM_INVALID</b>：场景 program 缺失或组件未知，检查 C01/D01/E03。</li>
          <li><b>E_PREVIEW_BUSY</b>：批量渲染中，稍后自动刷新。</li>
          <li><b>E_DELIVERY_QC</b>：查看交付 qc.json 的 checks，修复后重新生成。</li>
        </ul>
      </section>
    </main>
  );
}

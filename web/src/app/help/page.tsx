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
          <li><b>空格</b> 时间轴/审片播放 · <b>J/K/L</b> 倒/停/正</li>
          <li><b>←/→</b> 逐帧 · <b>Shift+←/→</b> 逐秒 · <b>I/O</b> 入出点 · <b>+/−</b> 缩放</li>
          <li><b>F</b> 审片全屏 · <b>S</b> 安全区</li>
        </ul>
      </section>
      <section className="card p-4 mb-4">
        <h2 className="font-semibold mb-2">R3 新页面</h2>
        <ul className="text-sm space-y-1">
          <li><a className="text-blue" href="/timeline">/timeline</a>：场景块拖拽/改时长/ripple、分割合并、文本、相机关键帧、转场、250ms 静帧预览。</li>
          <li><a className="text-blue" href="/player">/player</a>：审片播放器、帧锚定批注、resolve、场景/整片决议、JSON/CSV、审片包。</li>
          <li><a className="text-blue" href="/takes">/takes</a>：A/B Take 同步播放、差异叠加、评分/当前、场景采纳、分支与软删除保护。</li>
          <li><a className="text-blue" href="/assets">/assets</a>：全局/项目资产库、sha 去重、引用数与使用处、许可、替换/删除保护、字体缺字检查。</li>
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
          <li><b>E_DELIVERY_GATE</b>：G07 还没通过，先完成交付打包/审批。</li>
          <li><b>E_SCENE_READ_OVERFLOW</b>：场景时长读不完文案；拉长或删字，时间轴会二次确认。</li>
          <li><b>E_QC_LUFS/TRUE_PEAK</b>：G05 重新混音到 −16 LUFS，真峰留 1dB 余量。</li>
        </ul>
      </section>
    </main>
  );
}

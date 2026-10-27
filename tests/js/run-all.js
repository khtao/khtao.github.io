/**
 * 跑完三组 DOM 回归测试并汇总。
 * 用法：node tests/js/run-all.js
 * 依赖 jsdom：npm i jsdom
 */
const path = require('path');

const SUITES = [
  ['图片加载', './test-images'],
  ['版权与链接', './test-copyright'],
  ['性能 / 内存 / 健壮性', './test-performance'],
  ['覆盖缺口补充', './test-gaps'],
];

(async () => {
  let totalPass = 0;
  let totalFail = 0;
  for (const [name, mod] of SUITES) {
    let run;
    try {
      run = require(mod);
    } catch (e) {
      if (e && e.code === 'MODULE_NOT_FOUND' && /jsdom/.test(e.message)) {
        console.error('\n缺少 jsdom，请先安装：npm i jsdom\n');
        process.exit(2);
      }
      throw e;
    }
    const fail = await run();
    totalFail += fail;
  }
  // 各 suite 自己打印了明细，这里只汇总
  console.log('\n' + '='.repeat(56));
  console.log(totalFail === 0
    ? `✅ DOM 回归测试全部通过`
    : `❌ 有 ${totalFail} 项未通过`);
  console.log('='.repeat(56));
  process.exit(totalFail ? 1 : 0);
})();

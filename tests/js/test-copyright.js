/**
 * 版权与链接显示相关回归测试。
 *
 * 覆盖问题：
 *  #链接 版权框「原文链接」显示成 %E4%BB%8E… 编码，应显示中文
 *  #20  prettyURL 对含字面 % 的文件名会生成打不开的链接
 *  #6   复制监听未排除输入框（复制自己输入的文字也被追加出处）
 *  #7   iframe 内复制不受保护
 *  #23  文章自带灯箱可能读到占位图
 *  #postURL 同名函数覆盖导致全站链接变成绝对地址（#2 相关）
 */
const { boot, bare, wait, Suite } = require('./harness');

/** 模拟一次 copy 事件，返回被写入剪贴板的文本（未改写则返回 null） */
function fakeCopy(win, text) {
  const d = win.document;
  let captured = null;
  const ev = new win.Event('copy', { bubbles: true, cancelable: true });
  ev.clipboardData = { setData: (t, v) => { captured = v; } };
  win.getSelection = () => String(text);
  d.dispatchEvent(ev);
  return captured;
}

const LONG = '这是一段足够长的正文内容，用来触发复制溯源逻辑，必须超过四十个字的阈值才可以生效哦。';

async function run() {
  const s = new Suite('版权与链接');

  /* ---------- prettyURL：中文还原 vs 链接安全 ---------- */
  {
    const { W, close } = await bare();
    const f = W.eval('prettyURL');
    const cases = [
      ['https://x.io/#/p/%E4%BB%8E%E9%9B%B6%E9%83%A8%E7%BD%B2GitHub%E5%8D%9A%E5%AE%A2.md', '从零部署GitHub博客.md', true],
      ['https://x.io/#/p/hello.md', 'hello.md', false],
      ['https://x.io/#/p/%E4%B8%AD%E6%96%87%20%E7%A9%BA%E6%A0%BC.md', '中文 空格.md', true],
      // 文件名本身含 %（URL 里写作 %25）：解码会得到裸 %，链接就废了
      ['https://x.io/#/p/100%25.png', null, false],
      ['https://x.io/#/p/50%25off.jpg', null, false],
      ['https://x.io/#/p/%ZZ%E4%B8%AD.md', null, false],   // 非法转义
    ];
    for (const [url, expectText, shouldDecode] of cases) {
      const out = f(url);
      const decoded = out !== url;
      s.ok(decoded === shouldDecode,
        `#prettyURL ${shouldDecode ? '应解码' : '应原样'}：${url.slice(10)}`,
        `实际 ${out}`);
      if (expectText) s.ok(out.includes(expectText), `  显示含「${expectText}」`, out);
    }
    s.ok(!/%(?![0-9A-Fa-f]{2})/.test(f('https://x.io/#/p/100%25.png')),
      '#20 含字面 % 时不产生裸 %（链接不会被改坏）');
    close();
  }

  /* ---------- 版权框：href 保持编码、文字显示中文 ---------- */
  {
    const { W, D, wait, close } = await boot();
    W.location.hash = '#/p/' + encodeURIComponent('从零部署GitHub博客.md');
    W.dispatchEvent(new W.Event('hashchange'));
    await wait(800);

    const box = D.querySelector('.cr-box');
    s.ok(!!box, '文末版权框已渲染');
    s.ok(!!D.querySelector('.cr-line'), '标题下单行提示已渲染');
    const footLegal = D.getElementById('footLegal');
    s.ok(footLegal && footLegal.textContent.includes('未经许可不得转载'), '页脚常驻声明已渲染');
    s.eq(footLegal && footLegal.querySelectorAll('a').length, 1, '页脚含许可协议链接');

    const a = box && box.querySelector('.cr-meta a[href^="https"]');
    s.ok(!!a, '版权框含原文链接');
    if (a) {
      s.ok(/%[0-9A-Fa-f]{2}/.test(a.getAttribute('href')),
        'href 仍是百分号编码（保证可点击）', a.getAttribute('href'));
      s.ok(!/%[0-9A-Fa-f]{2}/.test(a.textContent),
        '#链接 显示文字已还原成中文（不再是一串 %XX）', a.textContent);
      s.ok(/[\u4e00-\u9fa5]/.test(a.textContent), '  显示文字确实含中文');
    }
    close();
  }

  /* ---------- 复制溯源 ---------- */
  {
    const { W, D, wait, close } = await boot();
    W.location.hash = '#/p/' + encodeURIComponent('从零部署GitHub博客.md');
    W.dispatchEvent(new W.Event('hashchange'));
    await wait(800);

    const long = fakeCopy(W, LONG);
    s.ok(long && long.includes('摘自'), '复制超过阈值 → 追加出处');
    s.ok(long && /[\u4e00-\u9fa5]/.test(long), '  出处里的链接是中文');
    s.eq(fakeCopy(W, '太短了'), null, '短摘引 → 不追加（不打扰正常引用）');

    // #6 输入框内复制不该被追加
    const input = D.createElement('input');
    D.body.appendChild(input);
    input.focus();
    s.eq(fakeCopy(W, LONG), null, '#6 输入框内复制 → 不追加出处');
    input.remove();

    const ta = D.createElement('textarea');
    D.body.appendChild(ta); ta.focus();
    s.eq(fakeCopy(W, LONG), null, '#6 textarea 内复制 → 不追加出处');
    ta.remove();
    close();
  }

  /* ---------- #7 iframe 内复制也受保护 ---------- */
  {
    const { W, close } = await bare();
    const sub = new (require('jsdom').JSDOM)('<body><p>正文</p></body>',
      { url: 'https://khtao.github.io/blog/x.html' }).window;
    W.eval('crAttachCopy')(sub);
    const out = fakeCopy(sub, LONG);
    s.ok(out && out.includes('摘自'), '#7 原样 HTML（iframe）内复制也追加出处');
    s.eq(fakeCopy(sub, '短'), null, '#7 iframe 内短摘引不追加');
    close();
  }

  /* ---------- #23 灯箱不会读到占位图 ---------- */
  {
    const { W, close } = await bare();
    const fr = W.document.createElement('div');
    W.document.body.appendChild(fr);
    fr.getBoundingClientRect = () => ({ top: 0, height: 5000, left: 0, width: 800, bottom: 5000, right: 800 });
    // 作者没写 data-full，且文章自带灯箱退化成读 img.src
    const sub = new (require('jsdom').JSDOM)(
      '<body>' + Array.from({ length: 8 }, (_, i) =>
        `<div class="ph"><img src="images/${String(i + 1).padStart(2, '0')}.jpg"></div>`).join('') + '</body>').window;
    [...sub.document.querySelectorAll('img')].forEach((im, i) => {
      im.getBoundingClientRect = () => ({ top: i * 320, height: 300, left: 0, width: 800, bottom: i * 320 + 300, right: 800 });
    });
    W.eval('fixFrameImages')(sub.document, fr);
    const imgs = [...sub.document.querySelectorAll('img')];
    const pending = imgs.filter((i) => i.getAttribute('data-lazysrc'));
    s.ok(pending.length > 0 && pending.every((i) => /\.jpe?g$|\.png$|\.webp$/i.test(i.getAttribute('data-full') || '')),
      '#23 缺 data-full 时已补真地址（灯箱不会读到透明占位）',
      pending.map((i) => i.getAttribute('data-full')).join(','));
    s.ok(pending.every((i) => !String(i.getAttribute('data-full')).startsWith('data:')),
      '#23 data-full 不是 base64 占位图');
    close();
  }

  /* ---------- #postURL 相对路由未被绝对地址覆盖 ---------- */
  {
    const { W, D, wait, close } = await boot();
    const link = D.querySelector('.post-item');
    s.ok(!!link, '列表页有文章卡片');
    if (link) {
      const href = link.getAttribute('href');
      s.ok(href.startsWith('#/p/'), '列表链接是相对哈希路由（未被绝对地址覆盖）', href);
      s.ok(!href.startsWith('http'), '  不含 http 前缀');
    }
    close();
  }

  return s.report();
}

module.exports = run;
if (require.main === module) run().then((f) => process.exit(f ? 1 : 0));

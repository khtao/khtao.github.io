/**
 * 图片加载相关回归测试。
 *
 * 覆盖问题：
 *  #1  iframe 撑到内容全高 → 原生 loading="lazy" 全失效（首屏拉满 9.2MB）
 *  #25 抽走 src 会让版面塌陷（容器无固定高度时）
 *  #26 每批加载后无条件重测，抵消了测量缓存
 *  #19 位置量不到时 top=NaN → 该图永远加载不到
 *  #5  WebP 缺失时每张图都先 404 再回退，请求数翻倍
 *  #8  封面图在 mdBody 之外，漏网
 */
const { boot, bare, wait, Suite } = require('./harness');

const BLANK_PREFIX = 'data:image/gif;base64';

/** 造一个带 N 张图的"iframe 文档"，可指定每张图量到的高度 */
function makeFrameDoc(W, n, height) {
  const body = Array.from({ length: n }, (_, i) =>
    `<div class="ph"><img src="images/${String(i + 1).padStart(2, '0')}.jpg"></div>`).join('');
  const sub = new (require('jsdom').JSDOM)(`<body>${body}</body>`).window;
  [...sub.document.querySelectorAll('img')].forEach((im, i) => {
    im.getBoundingClientRect = () => ({
      top: i * 320, height: typeof height === 'function' ? height(i) : height,
      left: 0, width: 800, bottom: i * 320 + 320, right: 800,
    });
  });
  return sub;
}

function makeFrame(W) {
  const fr = W.document.createElement('div');
  W.document.body.appendChild(fr);
  fr.getBoundingClientRect = () => ({ top: 0, height: 5000, left: 0, width: 800, bottom: 5000, right: 800 });
  return fr;
}

async function run() {
  const s = new Suite('图片加载');

  /* ---------- #1 iframe 内图片由父页面驱动，不再一次性全拉 ---------- */
  {
    const { W, close } = await bare();
    const fr = makeFrame(W);
    const sub = makeFrameDoc(W, 8, 300);
    W.eval('fixFrameImages')(sub.document, fr);
    const imgs = [...sub.document.querySelectorAll('img')];

    const real = imgs.filter((i) => !String(i.getAttribute('src')).startsWith(BLANK_PREFIX));
    const pending = imgs.filter((i) => i.getAttribute('data-lazysrc'));
    s.eq(real.length, 6, '#1 首屏只给 6 张真图（51 图不再是全部下载）');
    s.eq(pending.length, 2, '#1 其余图片挂起，等滚动再加载');
    s.ok(imgs.every((i) => !i.hasAttribute('loading')),
      '#1 已移除原生 loading（在 iframe 里它判定全部可见，无效）');
    s.ok(imgs.every((i) => i.getAttribute('decoding') === 'async'),
      '#1 全部图都带 decoding=async');
    close();
  }

  /* ---------- #25 抽走 src 前锁定高度，版面不塌陷 ---------- */
  {
    const { W, close } = await bare();
    const fr = makeFrame(W);
    const sub = makeFrameDoc(W, 8, 300);
    W.eval('fixFrameImages')(sub.document, fr);
    const imgs = [...sub.document.querySelectorAll('img')];
    const pending = imgs.filter((i) => i.getAttribute('data-lazysrc'));
    s.ok(pending.length > 0 && pending.every((i) => i.dataset.lockH === '1'),
      '#25 挂起的图都锁定了高度');
    s.ok(pending.every((i) => i.style.height === '300px'),
      '#25 锁定值等于实测高度（真图就位后尺寸一致，无跳动）',
      pending.map((i) => i.style.height).join(','));
    close();
  }

  /* ---------- #26a 已锁定 → 加载后不重测（保住测量缓存） ---------- */
  {
    const { W, close } = await bare();
    const fr = makeFrame(W);
    const sub = makeFrameDoc(W, 8, 300);   // 有高度 → 会被锁定
    W.innerHeight = 800;
    W.eval('fixFrameImages')(sub.document, fr);
    W.eval('pumpFrameLazy()');
    const imgs = [...sub.document.querySelectorAll('img')];
    const loadedNow = imgs.filter((i) => !i.getAttribute('data-lazysrc')).length;
    s.ok(loadedNow > 6, '#26a 滚动后确实加载了更多图', `已加载 ${loadedNow}`);
    s.ok(W.eval('frameLazy.measured') === true,
      '#26a 已锁定的图不改变布局 → 保持 measured=true（不重测）');
    close();
  }

  /* ---------- #26b 未锁定 → 加载后必须重测（位置确实会变） ---------- */
  {
    const { W, close } = await bare();
    const fr = makeFrame(W);
    const sub = makeFrameDoc(W, 8, 0);     // 量不到高度 → 不锁定
    W.innerHeight = 800;
    W.eval('fixFrameImages')(sub.document, fr);
    W.eval('pumpFrameLazy()');
    s.ok(W.eval('frameLazy.measured') === false,
      '#26b 未锁定的图会撑开版面 → measured 作废，下一轮重测');
    close();
  }

  /* ---------- #19 位置量不到时降级为直接加载（不能永远卡住） ---------- */
  {
    const { W, close } = await bare();
    const fr = makeFrame(W);
    const sub = makeFrameDoc(W, 5, 300);
    // 让测量抛异常（跨文档被拒等真实场景）
    [...sub.document.querySelectorAll('img')].forEach((im) => {
      im.getBoundingClientRect = () => { throw new Error('denied'); };
    });
    W.eval('frameLazy.fr = document.body.lastChild; frameLazy.items = []; frameLazy.measured = false;');
    const items = W.eval('frameLazy.items');
    [...sub.document.querySelectorAll('img')].forEach((im) => {
      im.setAttribute('data-lazysrc', im.getAttribute('src'));
      im.setAttribute('src', W.eval('BLANK_IMG'));
      items.push({ img: im, top: 0, h: 0 });
    });
    W.eval('pumpFrameLazy()');
    const imgs = [...sub.document.querySelectorAll('img')];
    s.eq(imgs.filter((i) => !i.getAttribute('data-lazysrc')).length, 5,
      '#19 量不到位置时全部放行（不会永远加载不到）');
    s.ok(W.eval('frameLazy.items.length') === 0, '#19 队列已清空');
    close();
  }

  /* ---------- #5 WebP 404 回退 + 目录级失败记忆 ---------- */
  {
    const { W, D, close } = await bare();
    W.HTMLCanvasElement.prototype.toDataURL = () => 'data:image/webp;base64,UklGRg==';
    s.eq(W.eval('webpSupported()'), true, '#5 已模拟浏览器支持 WebP');

    const mk = (src) => { const i = D.createElement('img'); i.setAttribute('src', src); return i; };
    const a = mk('images/01.jpg'), b = mk('images/02.jpg');
    W.eval('tuneImage')(a, true);
    W.eval('tuneImage')(b, true);
    s.ok(a.getAttribute('src').endsWith('.webp') && b.getAttribute('src').endsWith('.webp'),
      '#5 支持时优先换 WebP');

    a.dispatchEvent(new W.Event('error'));   // 第一张 404
    s.eq(a.getAttribute('src'), 'images/01.jpg', '#5 WebP 404 后回退原图');
    s.ok(W.eval('[...webpFailedDirs]').includes('images/'), '#5 记住了失败目录');

    const c = mk('images/99.jpg');
    W.eval('tuneImage')(c, true);
    s.eq(c.getAttribute('src'), 'images/99.jpg',
      '#5 同目录后续图不再尝试 WebP（只付 1 次 404，而非每张一次）');

    const d2 = mk('other/pic.png');
    W.eval('tuneImage')(d2, true);
    s.ok(d2.getAttribute('src').endsWith('.webp'), '#5 其他目录仍正常尝试 WebP');
    close();
  }

  /* ---------- #8 封面图也被治理 ---------- */
  {
    const { W, D, wait, close } = await boot();
    W.location.hash = '#/p/' + encodeURIComponent('从零部署GitHub博客.md');
    W.dispatchEvent(new W.Event('hashchange'));
    await wait(800);
    const cover = D.querySelector('.post-cover img');
    s.ok(!!cover, '#8 文章有封面图');
    if (cover) {
      // resolveMedia() 会把相对路径补成 ./blog/... 前缀，所以只比对结尾
      s.ok(String(cover.getAttribute('data-origsrc')).endsWith('images/guide/hero.svg'),
        '#8 封面被治理（在 mdBody 之外，容易漏网）', cover.getAttribute('data-origsrc'));
      s.eq(cover.getAttribute('loading'), 'eager', '#8 封面在首屏，立即加载');
      s.eq(cover.getAttribute('decoding'), 'async', '#8 封面带 decoding=async');
    }
    close();
  }

  /* ---------- 正文图片（md 文章）懒加载 ---------- */
  {
    const { W, D, wait, close } = await boot();
    W.location.hash = '#/p/' + encodeURIComponent('从零部署GitHub博客.md');
    W.dispatchEvent(new W.Event('hashchange'));
    await wait(800);
    const imgs = [...D.querySelectorAll('#mdBody img')];
    s.ok(imgs.length > 0, '正文有图片');
    s.eq(imgs.filter((i) => i.getAttribute('loading') === 'eager').length, 2,
      '正文前 2 张立即加载');
    s.ok(imgs.slice(2).every((i) => i.getAttribute('loading') === 'lazy'),
      '正文其余图片懒加载');
    close();
  }

  return s.report();
}

module.exports = run;
if (require.main === module) run().then((f) => process.exit(f ? 1 : 0));

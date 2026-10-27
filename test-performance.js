/**
 * 性能、内存与健壮性回归测试。
 *
 * 覆盖问题：
 *  #10 自动同步每 5 分钟无条件整页重绘两次（打断阅读 / iframe 重载回顶部）
 *  #11 state.refreshing 无人读取，开头那次 render() 纯属白做
 *  #12 每 5 分钟无条件 writeCache()，同步阻塞主线程
 *  #14 读原样 HTML 后点回首页，scroll/resize 监听未清理，每往返泄漏一组
 *  #17 resize 监听用匿名函数注册却拿另一个函数 remove → 根本摘不掉
 *  #21 进度条 width 动画每帧触发布局 + scroll 无节流
 *  #22 读文章返回列表后「已展开条数」被重置
 *  #24 postsSignature() 一次同步里被调用 4 次
 *  #13/#27/#28 localStorage 配额不足：降级、提示、不反复 stringify
 *  #29 config.json 关键字段为空 → 整站静默走错 URL
 */
const fs = require('fs');
const path = require('path');
const { boot, bare, wait, Suite, ROOT, mountRealArticle } = require('./harness');

async function run() {
  const s = new Suite('性能 / 内存 / 健壮性');

  /* ---------- #10/#11 无变化时静默，不打断阅读 ---------- */
  {
    const { W, D, wait, close } = await boot();
    let mutations = 0;
    const mo = new W.MutationObserver(() => { mutations++; });
    mo.observe(D.getElementById('app'), { childList: true });
    await wait(100);
    mutations = 0;

    await W.eval('refresh(false)');
    await wait(300);
    s.eq(mutations, 0, '#10 内容无变化 → 不重绘（阅读不被打断）');

    await W.eval('refresh(true)');
    await wait(300);
    s.ok(mutations > 0, '#11 手动刷新 → 正常重绘');
    close();
  }

  /* ---------- #12 内容未变时不写缓存 ---------- */
  {
    const { W, D, wait, close } = await boot();
    const orig = W.localStorage.setItem.bind(W.localStorage);
    let writes = 0;
    W.localStorage.setItem = (...a) => { if (a[0] && String(a[0]).includes('blog')) writes++; return orig(...a); };
    await W.eval('refresh(false)');
    await wait(300);
    s.eq(writes, 0, '#12 内容无变化 → 不写缓存（省掉一次同步序列化 + 写盘）');
    W.localStorage.setItem = orig;
    close();
  }

  /* ---------- #14/#17 路由往返不泄漏监听 ---------- */
  {
    const { W, wait, close } = await boot();
    let add = 0, rem = 0;
    const P = W.EventTarget.prototype;
    const oa = P.addEventListener, or = P.removeEventListener;
    P.addEventListener = function (t, ...a) { if (this === W && (t === 'scroll' || t === 'resize')) add++; return oa.call(this, t, ...a); };
    P.removeEventListener = function (t, ...a) { if (this === W && (t === 'scroll' || t === 'resize')) rem++; return or.call(this, t, ...a); };

    for (let i = 0; i < 4; i++) {
      W.location.hash = '#/p/' + encodeURIComponent('中国50个一生必去的地方.html');
      W.dispatchEvent(new W.Event('hashchange'));
      await wait(320);
      // 关键：jsdom 不会自己加载 iframe。不挂载的话 rawObservers 恒为 0，
      // 这条断言会变成假阳性 —— 之前正是这样漏掉了真实的泄漏。
      await mountRealArticle(W, '中国50个一生必去的地方.html');
      W.location.hash = '#/';
      W.dispatchEvent(new W.Event('hashchange'));
      await wait(220);
    }
    P.addEventListener = oa; P.removeEventListener = or;
    s.ok(add > 0, '#14 往返期间确实注册过监听（前提成立，否则断言无意义）', `add=${add}`);
    s.eq(add - rem, 0, '#14/#17 往返 4 次后 window 监听净残留为 0', `add=${add} remove=${rem}`);
    s.eq(W.eval('rawObservers.length'), 0, '#14 iframe 观察者已全部 disconnect');
    s.eq(W.eval('frameLazy.items.length'), 0, '#14 懒加载队列已清空');
    s.eq(W.eval('typeof onFrameResize'), 'function', '#17 resize 处理是具名函数（可摘除）');
    close();
  }

  /* ---------- #17 resize 监听确实被摘掉（行为验证，而非数调用次数）---------- */
  {
    const { W, D, wait, close } = await bare();
    const fr = D.createElement('div'); D.body.appendChild(fr);
    fr.getBoundingClientRect = () => ({ top: 0, height: 5000, left: 0, width: 800, bottom: 5000, right: 800 });
    const sub = new (require('jsdom').JSDOM)('<body><img src="a.jpg"></body>').window;

    const fix = W.eval('fixFrameImages');
    fix(sub.document, fr);
    W.eval('stopRawWatch()');                 // 离开文章：应当全部摘除

    // 用「事件是否还会触发」来判断，而不是数 remove 被调用了几次：
    // 匿名函数注册 + 拿另一个函数去 remove，remove 照样被调用，却根本摘不掉。
    W.eval('frameLazy.measured = true');
    W.dispatchEvent(new W.Event('resize'));
    await new Promise(r=>setTimeout(r,60));
    s.ok(W.eval('frameLazy.measured') === true,
      '#17 摘除后 resize 不再触发处理（监听真的没了）');

    W.eval('frameLazy.raf = 0');
    W.dispatchEvent(new W.Event('scroll'));
    await new Promise(r=>setTimeout(r,60));
    s.eq(W.eval('frameLazy.raf'), 0,
      '#14 摘除后 scroll 不再排入新帧（监听真的没了）');
    close();
  }

  /* ---------- #21 进度条用 transform，且滚动被 rAF 合并 ---------- */
  {
    const { W, D, wait, close } = await boot();
    W.eval('document.documentElement.scrollTop = 200');
    W.dispatchEvent(new W.Event('scroll'));
    await wait(120);
    const bar = D.getElementById('bar');
    s.ok(bar.style.transform && bar.style.transform.startsWith('scaleX'),
      '#21 进度条改用 transform（width 动画每帧触发布局）', bar.style.transform || '(空)');
    s.ok(!bar.style.width, '#21 不再设置 width');

    // 连续多次 scroll 只应触发一次 rAF 回调
    let frames = 0;
    const origRaf = W.requestAnimationFrame;
    W.requestAnimationFrame = (fn) => { frames++; return origRaf(fn); };
    for (let i = 0; i < 10; i++) W.dispatchEvent(new W.Event('scroll'));
    await wait(150);
    W.requestAnimationFrame = origRaf;
    s.ok(frames <= 1, '#21 连续 10 次 scroll 只排入 ≤1 帧回调（已节流）', `frames=${frames}`);
    close();
  }

  /* ---------- #22 返回列表保留已展开条数 ---------- */
  {
    const { W, wait, close } = await boot();
    W.eval('state.visible = 18; render();');
    await wait(120);
    W.location.hash = '#/p/' + encodeURIComponent('从零部署GitHub博客.md');
    W.dispatchEvent(new W.Event('hashchange'));
    await wait(400);
    W.location.hash = '#/';
    W.dispatchEvent(new W.Event('hashchange'));
    await wait(300);
    s.eq(W.eval('state.visible'), 18, '#22 读文章返回 → 保留已展开条数（不再白翻）');
    close();
  }

  /* ---------- #24 postsSignature 一次同步里不被重复计算 ---------- */
  {
    const { W, wait, close } = await boot();
    // function 声明会挂到 window，内部调用会解析到这里，所以替换可以真正计数
    const orig = W.postsSignature;
    s.eq(typeof orig, 'function', '#24 postsSignature 可观测');
    let calls = 0;
    W.postsSignature = function () { calls++; return orig.apply(this, arguments); };
    await W.eval('refresh(false)');
    await wait(300);
    // 1 次取 prevSig + 1 次算 dirty，互斥分支 → 上限 2
    s.ok(calls <= 2, '#24 一次同步内 postsSignature 至多 2 次（曾因写成函数而翻倍）', `实际 ${calls} 次`);
    W.postsSignature = orig;
    close();
  }

  /* ---------- #13/#28 配额不足时优雅降级 ---------- */
  {
    const { W, close } = await boot({ settle: 1400 });
    const orig = W.localStorage.setItem.bind(W.localStorage);
    let attempts = 0, thrown = 0;
    W.localStorage.setItem = (...a) => {
      attempts++;
      if (String(a[1]).length > 500) { thrown++; const e = new Error('quota'); e.name = 'QuotaExceededError'; throw e; }
      return orig(...a);
    };
    let crashed = false;
    try { W.eval('writeCache()'); } catch (e) { crashed = true; }
    s.ok(!crashed, '#13 配额不足时 writeCache 不抛异常（不会打断页面）');
    s.ok(attempts <= 4, '#28 降级尝试次数受控（先估长度再写，不再 7 次 stringify+setItem）', `attempts=${attempts}`);
    W.localStorage.setItem = orig;
    close();
  }

  /* ---------- #27 正文未就绪时给出提示而非空白 ---------- */
  {
    const { W, close } = await bare();
    const html = W.eval('bodyHTML({isHtml:false, body:""}, null)');
    s.ok(html.includes('md-wait') && html.includes('正文正在载入'),
      '#27 无正文时显示「正文正在载入…」而不是一片空白', html.slice(0, 60));
    const ok = W.eval('bodyHTML({isHtml:false, body:"# hi"}, null)');
    s.ok(ok.includes('mdBody'), '#27 有正文时正常渲染');
    close();
  }

  /* ---------- #29 config 关键字段为空时回落默认 ---------- */
  {
    const { W, close } = await bare();
    const bad = { blogDir: '', branch: '', owner: '', repo: '', title: 'x' };
    W.fetch = async () => ({ ok: true, status: 200, text: async () => JSON.stringify(bad) });
    await W.eval('loadConfig()');
    const cfg = W.eval('({blogDir:cfg.blogDir, branch:cfg.branch, owner:cfg.owner, repo:cfg.repo})');
    s.eq(cfg.blogDir, 'blog', '#29 blogDir 为空 → 回落 "blog"');
    s.eq(cfg.branch, 'main', '#29 branch 为空 → 回落 "main"');
    s.ok(cfg.owner && cfg.repo, '#29 owner/repo 非空', JSON.stringify(cfg));
    close();
  }

  return s.report();
}

module.exports = run;
if (require.main === module) run().then((f) => process.exit(f ? 1 : 0));

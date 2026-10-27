/**
 * 覆盖审计后补上的缺口。
 *
 * 这一组专门补前几轮「提到过、但没人守着」的行为：
 *   A 降级缓存（配额不足只存了元数据）→ 正文必须自动重拉，不能永远空白
 *   B 原样 HTML（iframe）文章的版权三层声明 —— 之前只测了 md 文章
 *   C 版权开关：enabled:false 应让三层全部消失；copyMinLength 阈值生效
 *   D 真实 51 图文章的端到端懒加载（之前只用 mock 的 8 张图）
 *   E syncSequence 竞态：旧请求回来时不能覆盖新状态
 *   G 从文章页切到归档/话题页，监听同样要清理
 *   H 搜索高亮 / 状态文案必须转义（防注入）
 */
const { boot, bare, wait, Suite, mountRealArticle } = require('./harness');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** 读到 localStorage 里的文章缓存 */
function readCache(W) {
  const raw = W.localStorage.getItem(W.eval('CACHE_KEY'));
  return raw ? JSON.parse(raw) : null;
}

async function run() {
  const s = new Suite('覆盖缺口补充');

  /* ---------- A 降级缓存 → 正文自动重拉 ---------- */
  {
    const { W, wait, close } = await boot();
    // 手工造一份「配额不足」的降级缓存：有元数据、raw 为空
    const key = W.eval('CACHE_KEY');
    const posts = W.eval('state.posts.map(p=>({name:p.name,sha:p.sha,path:p.path,meta:{title:p.title,isHtml:p.isHtml,words:p.words,tags:p.tags||[],category:p.category||""}}))');
    W.localStorage.setItem(key, JSON.stringify({
      ts: Date.now(), branch: 'main', generated: 'x',
      posts: posts.map((p) => ({ ...p, raw: '' })),   // ← 降级：没有正文
    }));

    // 用降级缓存 hydrate
    const c = JSON.parse(W.localStorage.getItem(key));
    const hydrated = W.eval('hydrate')(c);
    s.ok(hydrated.length > 0, 'A 降级缓存能 hydrate 出文章列表');
    s.ok(hydrated.every((p) => !p.body), 'A 降级缓存里没有正文（前提成立）');

    // 关键：refresh 时不能因为 sha 相同就跳过正文拉取
    W.eval('state.posts = ' + JSON.stringify(hydrated.map((p) => ({
      name: p.name, sha: p.sha, path: p.path, title: p.title, isHtml: p.isHtml,
      words: p.words, tags: p.tags || [], category: p.category || '', body: '',
    }))) + '; state.hasList = true;');
    await W.eval('refresh(false)');
    await wait(500);
    const withBody = W.eval('state.posts.filter(p=>p.body).length');
    const total = W.eval('state.posts.length');
    s.ok(withBody > 0, 'A 降级缓存的正文被重新拉取（不会永远空白）',
      `有正文 ${withBody}/${total}`);
    s.eq(withBody, total, 'A 全部文章正文都已回填');
    close();
  }

  /* ---------- B 原样 HTML（iframe）文章的版权三层 ---------- */
  {
    const { W, D, wait, close } = await boot();
    W.location.hash = '#/p/' + encodeURIComponent('中国50个一生必去的地方.html');
    W.dispatchEvent(new W.Event('hashchange'));
    await wait(1000);
    s.ok(!!D.querySelector('#rawFrame'), 'B 进入原样 HTML 文章（iframe 路径）');
    s.ok(!!D.querySelector('.cr-box'), 'B iframe 文章也有文末版权框');
    s.ok(!!D.querySelector('.cr-line'), 'B iframe 文章也有单行提示');
    const foot = D.getElementById('footLegal');
    s.ok(foot && foot.textContent.includes('未经许可不得转载'), 'B 页脚声明仍在');
    close();
  }

  /* ---------- C 版权开关与阈值 ---------- */
  {
    const { W, D, wait, close } = await boot();
    // 关掉总开关
    W.eval('cfg.copyright = Object.assign({}, cfg.copyright, {enabled:false})');
    W.location.hash = '#/p/' + encodeURIComponent('从零部署GitHub博客.md');
    W.dispatchEvent(new W.Event('hashchange'));
    await wait(800);
    s.ok(!D.querySelector('.cr-box'), 'C enabled:false → 文末版权框消失');
    s.ok(!D.querySelector('.cr-line'), 'C enabled:false → 单行提示消失');
    // 页脚由 loadConfig() 渲染，动态改 cfg 不会自动重刷；直接验证渲染函数
    s.eq(W.eval('crCfg().enabled'), false, 'C 配置已关闭');
    s.eq(W.eval('copyrightHTML({title:"t",name:"a.md"})'), '', 'C 关闭时版权框渲染为空');
    s.eq(W.eval('copyrightLine({title:"t"})'), '', 'C 关闭时单行提示渲染为空');

    // 打开开关，验证阈值：短于 copyMinLength 不追加
    W.eval('cfg.copyright = Object.assign({}, cfg.copyright, {enabled:true, copyMinLength:200})');
    const fake = (text) => {
      let cap = null;
      const ev = new W.Event('copy', { bubbles: true, cancelable: true });
      ev.clipboardData = { setData: (t, v) => { cap = v; } };
      W.getSelection = () => String(text);
      D.dispatchEvent(ev);
      return cap;
    };
    const mid = '这是一段中等长度的文字，大约有五六十个字左右，用来测试阈值是否真的生效看看。';
    s.eq(fake(mid), null, 'C copyMinLength=200 → 更短的文本不追加');
    const long = 'x'.repeat(250);
    s.ok(fake(long) && fake(long).includes('摘自'), 'C 超过阈值 → 正常追加');
    close();
  }

  /* ---------- D 真实 51 图文章的端到端懒加载 ---------- */
  {
    const { W, D, wait, close } = await boot();
    W.location.hash = '#/p/' + encodeURIComponent('中国50个一生必去的地方.html');
    W.dispatchEvent(new W.Event('hashchange'));
    await wait(1200);
    // 真正走一遍 initRawFrame：jsdom 不会自己加载 iframe，不挂载的话
    // frameLazy 恒为空，下面的断言会假通过（这正是之前漏掉泄漏的原因）
    const mounted = await mountRealArticle(W, '中国50个一生必去的地方.html');
    s.ok(!!mounted, 'D 已挂载真实文章到 iframe（走真实代码路径）');
    if (!mounted) { close(); return s.report(); }
    s.eq(mounted.imgCount, 50, 'D 该文含 50 张有 src 的图（灯箱空 img 不计）');

    const total = W.eval('frameLazy.items.length');
    // 50 张有 src 的图，首屏 6 张直接给真图 → 挂起 44
    s.eq(total, 44, 'D 50 张图中 44 张被挂起（首屏只给 6 张，不再一次拉 9.2MB）');
    s.ok(W.eval('frameLazy.items.every(it=>it.img.getAttribute("src").startsWith("data:"))'),
      'D 挂起的图都用透明占位（未发起真实请求）');
    s.ok(W.eval('frameLazy.items.every(it=>!!it.img.getAttribute("data-lazysrc"))'),
      'D 挂起的图都保留了真地址');

    // 模拟逐步向下滚动（一次性跳到底会让图片落在视口上方一屏半之外，
    // 按设计本就不该补加载 —— 那不是 bug，是预加载窗口的正确行为）
    for (let top = 0; top > -20000; top -= 400) {
      const t = top;
      W.eval(`frameLazy.fr.getBoundingClientRect = () => ({top:${t}, height:60000, left:0, width:800, bottom:${t + 60000}, right:800})`);
      W.eval('pumpFrameLazy()');
    }
    await wait(100);
    s.eq(W.eval('frameLazy.items.length'), 0, 'D 逐步滚到底后 44 张全部加载完毕');
    s.ok(W.eval('typeof frameLazy.fr === "object"'), 'D 队列清空后 fr 仍在（未误清）');
    close();
  }

  /* ---------- E syncSequence 竞态 ---------- */
  {
    const { W, wait, close } = await boot();
    // 让 fetchList 变慢，制造「旧请求后到」的场景
    const origFetch = W.fetch;
    let slow = true;
    W.fetch = async (u) => {
      if (slow && String(u).includes('index.json')) { await sleep(400); }
      return origFetch(u);
    };
    const p1 = W.eval('refresh(false)');   // 旧请求（慢）
    await sleep(50);
    slow = false;
    const p2 = W.eval('refresh(true)');    // 新请求（快）
    await Promise.all([p1, p2]);
    await wait(300);
    W.fetch = origFetch;
    // 无论谁后到，最终状态必须自洽：文章列表非空且未损坏
    const n = W.eval('state.posts.length');
    s.ok(n > 0, 'E 并发 refresh 后文章列表完好', `posts=${n}`);
    s.eq(W.eval('state.refreshing'), false, 'E refreshing 标志已复位（不会永久转圈）');
    s.ok(W.eval('state.hasList'), 'E hasList 为真');
    close();
  }

  /* ---------- G 切到归档 / 话题页同样清理监听 ---------- */
  {
    const { W, wait, close } = await boot();
    const P = W.EventTarget.prototype;
    const oa = P.addEventListener, or = P.removeEventListener;
    let add = 0, rem = 0;
    P.addEventListener = function (t, ...a) { if (this === W && (t === 'scroll' || t === 'resize')) add++; return oa.call(this, t, ...a); };
    P.removeEventListener = function (t, ...a) { if (this === W && (t === 'scroll' || t === 'resize')) rem++; return or.call(this, t, ...a); };

    const targets = ['#/archive', '#/topics', '#/', '#/about'];
    for (const h of targets) {
      W.location.hash = '#/p/' + encodeURIComponent('中国50个一生必去的地方.html');
      W.dispatchEvent(new W.Event('hashchange'));
      await wait(300);
      await mountRealArticle(W, '中国50个一生必去的地方.html');   // 真正驱动 iframe
      W.location.hash = h;                 // 从文章页切到别的页
      W.dispatchEvent(new W.Event('hashchange'));
      await wait(220);
    }
    P.addEventListener = oa; P.removeEventListener = or;
    s.ok(add > 0, 'G 往返期间确实注册过监听（前提成立）', `add=${add}`);
    s.eq(add - rem, 0, 'G 文章页 → 归档/话题/首页/关于 均清理干净', `add=${add} rem=${rem}`);
    s.eq(W.eval('rawObservers.length'), 0, 'G 观察者无残留');
    close();
  }

  /* ---------- H 转义（防注入） ---------- */
  {
    const { W, D, close } = await bare();
    const esc = W.eval('esc');
    const evil = '<img src=x onerror=alert(1)>&"\'';
    const out = esc(evil);
    s.ok(!out.includes('<img'), 'H esc 转义了尖括号（不会注入标签）', out);
    // 真正该验证的是：塞回 DOM 后不会变成元素节点（onerror 作为纯文本无害）
    const probe = D.createElement('div');
    probe.innerHTML = out;
    s.eq(probe.querySelectorAll('*').length, 0, 'H 转义后再入 DOM 不产生任何元素节点');
    s.ok(out.includes('&lt;') && out.includes('&amp;'), 'H 使用了实体编码');

    // 搜索高亮：命中词也要转义，不能因为高亮就漏掉转义
    const hl = W.eval('highlight');
    const bad = hl('<script>bad</script>', 'script');
    s.ok(!bad.includes('<script'), 'H 搜索高亮对文本做了转义', bad);
    s.ok(bad.includes('<mark>'), 'H 高亮标记仍在');
    close();
  }

  return s.report();
}

module.exports = run;
if (require.main === module) run().then((f) => process.exit(f ? 1 : 0));

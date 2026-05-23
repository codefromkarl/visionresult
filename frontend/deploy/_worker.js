// Visual Insight Agent - Cloudflare Pages Worker (v3)
// 多阶段 Pipeline + Gemini OCR + 多源搜索 + SSE 实时推送

const GEMINI_KEY = '<REDACTED>';
let baiduTokenCache = { token: null, expire: 0 };

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const cors = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET,POST,OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type' };
    if (request.method === 'OPTIONS') return new Response(null, { headers: cors });
    if (url.pathname === '/api/analyze' && request.method === 'POST') return handleAnalyze(request, env, cors);
    if (url.pathname.startsWith('/api/report/')) return handleReport(url, env, cors);
    if (url.pathname.startsWith('/api/events/')) return handleEvents(url, env, cors);
    return env.ASSETS.fetch(request);
  }
};

// ==================== 工具 ====================
function json(data, status = 200, h = {}) { return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json', ...h } }); }
function uint8ToBase64(u8) { let b = ''; const c = 0x8000; for (let i = 0; i < u8.length; i += c) { const ch = u8.subarray(i, Math.min(i + c, u8.length)); b += String.fromCharCode(...ch); } return btoa(b); }

// ==================== SSE 分析 API ====================
async function handleAnalyze(request, env, cors) {
  try {
    const formData = await request.formData();
    const file = formData.get('file');
    if (!file) return json({ error: 'No file' }, 400, cors);
    const buffer = await file.arrayBuffer();
    const uint8 = new Uint8Array(buffer);
    const taskId = crypto.randomUUID().slice(0, 8);
    const mimeType = file.type || 'image/jpeg';

    // 存 R2 + D1
    await env.IMAGE_BUCKET.put(`${taskId}/${file.name}`, buffer, { httpMetadata: { contentType: mimeType } });
    await env.DB.prepare('INSERT INTO analyses (id, status, filename, created_at) VALUES (?, ?, ?, ?)')
      .bind(taskId, 'processing', file.name, new Date().toISOString()).run();

    // 创建 SSE 流
    const { readable, writable } = new IdentityTransformStream();
    const writer = writable.getWriter();
    const enc = new TextEncoder();
    const sse = async (event, data) => { try { await writer.write(enc.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)); } catch(e) {} };
    const startTime = Date.now();

    // 后台执行 Pipeline（不 await，让 SSE 流先返回）
    (async () => {
      try {
        await sse('status', { task_id: taskId, status: 'processing' });
        const result = await runPipeline(env, taskId, uint8, mimeType, file.name, sse);
        const totalMs = Date.now() - startTime;
        await sse('complete', { task_id: taskId, status: 'completed', total_ms: totalMs, analysis: result.analysis, pipeline_trace: result.trace });

        // 更新 D1
        await env.DB.prepare('UPDATE analyses SET status = ?, result = ?, completed_at = ? WHERE id = ?')
          .bind('completed', JSON.stringify(result.analysis), new Date().toISOString(), taskId).run();
      } catch (error) {
        await sse('error', { error: error.message });
      } finally {
        try { await writer.close(); } catch(e) {}
      }
    })();

    return new Response(readable, { headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', 'Connection': 'keep-alive', ...cors } });
  } catch (error) {
    return json({ error: error.message }, 500, cors);
  }
}

// ==================== 多阶段 Pipeline ====================
async function runPipeline(env, taskId, uint8, mimeType, filename, sse) {
  const trace = { steps: [], total_duration_ms: 0 };

  // 通用阶段执行器：发 SSE + 计时 + 记 trace
  async function stage(name, stageName, icon, tool, pct, fn) {
    const t0 = Date.now();
    await sse('progress', { stage: name, percent: pct, label: stageName });
    try {
      const r = await fn();
      const ms = Date.now() - t0;
      trace.steps.push({ stage_name: name, status: 'success', duration_ms: ms, output_summary: r._summary || '', key_findings: r._findings || [] });
      if (r._insight) await sse('insight', { node: name, icon, title: stageName, tool, duration_ms: ms, ...r._insight });
      return r;
    } catch (error) {
      const ms = Date.now() - t0;
      trace.steps.push({ stage_name: name, status: 'failed', duration_ms: ms, error_message: error.message });
      await sse('insight', { node: name, icon: '❌', title: stageName + ' 失败', tool, duration_ms: ms, summary: error.message, results: [] });
      return { _error: error.message };
    }
  }

  // ① 预处理
  const pre = await stage('preprocess', '图片预处理', '🖼️', 'Image Parser', 10, async () => {
    let fmt = 'unknown', w = 0, h = 0;
    if (uint8[0] === 0xFF && uint8[1] === 0xD8) { fmt = 'JPEG'; let o = 2; while (o < uint8.length - 9) { if (uint8[o] !== 0xFF) break; const m = uint8[o+1]; if (m === 0xC0 || m === 0xC2) { h = (uint8[o+5]<<8)|uint8[o+6]; w = (uint8[o+7]<<8)|uint8[o+8]; break; } o += 2 + ((uint8[o+2]<<8)|uint8[o+3]); } }
    else if (uint8[0] === 0x89 && uint8[1] === 0x50) { fmt = 'PNG'; w = (uint8[16]<<24)|(uint8[17]<<16)|(uint8[18]<<8)|uint8[19]; h = (uint8[20]<<24)|(uint8[21]<<16)|(uint8[22]<<8)|uint8[23]; }
    else if (uint8[8] === 0x57) fmt = 'WebP';
    const kb = (uint8.byteLength / 1024).toFixed(1);
    return { w, h, fmt, size: uint8.byteLength,
      _summary: `${w}x${h}, ${kb}KB`, _findings: [`格式: ${fmt}`, `尺寸: ${w}x${h}`],
      _insight: { summary: `${w}x${h}, ${kb}KB`, results: [{ label: '尺寸', value: `${w}x${h}` }, { label: '格式', value: fmt }, { label: '大小', value: `${kb}KB` }] }
    };
  });

  // ② OCR：四引擎级联 Gemini → OCR.space → 百度 → Workers AI
  const ocr = await stage('ocr', 'OCR 文字识别', '📝', '多引擎级联', 25, async () => {
    const b64 = uint8ToBase64(uint8);
    const allResults = []; // 收集所有引擎结果用于融合
    const engines = []; // 记录使用了哪些引擎

    // ① OCR.space（免费，200+ 语言，25K/月）
    // 图片不能超过 1MB；用 urlencoded body 传 base64（FormData 模式解析有 bug）
    const imgSizeKB = uint8.byteLength / 1024;
    if (imgSizeKB <= 1024) {
      try {
        const params = new URLSearchParams();
        params.set('base64Image', `data:${mimeType};base64,${b64}`);
        params.set('language', 'chs'); // 中英混合
        params.set('isOverlayRequired', 'false');
        params.set('OCREngine', '1'); // Engine 1 速度快；Engine 2 对中文会超时
        const ocrSpaceResp = await fetch('https://api.ocr.space/parse/image', {
          method: 'POST',
          headers: { 'apikey': 'helloworld', 'Content-Type': 'application/x-www-form-urlencoded' },
          body: params.toString(),
          signal: AbortSignal.timeout(12000),
        });
        const ocrSpaceText = await ocrSpaceResp.text();
        try {
          const ocrSpaceData = JSON.parse(ocrSpaceText);
          if (ocrSpaceData.ParsedResults?.[0]?.ParsedText) {
            const raw = ocrSpaceData.ParsedResults[0].ParsedText;
            const lines = raw.split(/\r?\n/).map(t => t.trim()).filter(t => t.length > 0);
            if (lines.length > 0) { allResults.push(...lines); engines.push('OCR.space'); }
          } else if (ocrSpaceData.ErrorMessage) {
            console.error('OCR.space error:', ocrSpaceData.ErrorMessage);
          } else if (ocrSpaceData.error) {
            console.error('OCR.space API error:', ocrSpaceData.error);
          }
        } catch (parseErr) {
          console.error('OCR.space parse error:', ocrSpaceText.substring(0, 200));
        }
      } catch (e) { console.error('OCR.space error:', e.message); }
    }

    // ② 百度 OCR（需 API Key，免费 1000 次/月）
    const baiduAk = env.BAIDU_OCR_API_KEY || '';
    const baiduSk = env.BAIDU_OCR_SECRET_KEY || '';
    if (baiduAk && baiduSk) {
      try {
        // 获取 access_token（缓存 30 天）
        let token = baiduTokenCache.token;
        if (!token || Date.now() > baiduTokenCache.expire) {
          const tokenResp = await fetch(`https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id=${baiduAk}&client_secret=${baiduSk}`, { signal: AbortSignal.timeout(5000) });
          if (tokenResp.ok) { const td = await tokenResp.json(); token = td.access_token; baiduTokenCache = { token, expire: Date.now() + 29 * 86400000 }; }
        }
        if (token) {
          const b64url = encodeURIComponent(b64);
          const baiduResp = await fetch(`https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic?access_token=${token}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: `image=${b64url}&language_type=CHN_ENG&detect_direction=true`,
            signal: AbortSignal.timeout(10000),
          });
          if (baiduResp.ok) {
            const bd = await baiduResp.json();
            if (bd.words_result?.length > 0) {
              const bdTexts = bd.words_result.map(w => w.words).filter(t => t && t.trim().length > 0);
              allResults.push(...bdTexts); engines.push('百度OCR');
            }
          }
        }
      } catch (e) { console.error('Baidu OCR error:', e.message); }
    }

    // ③ Gemini OCR（高精度，需 API Key）
    try {
      const gemResp = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${GEMINI_KEY}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ contents: [{ parts: [
          { text: 'Extract ALL text visible in this image. Output ONLY the raw text characters, one per line. No labels, no explanations. If no text, say NONE.' },
          { inlineData: { mimeType, data: b64 } }
        ]}], generationConfig: { temperature: 0.0, maxOutputTokens: 512 } }), signal: AbortSignal.timeout(15000),
      });
      if (gemResp.ok) {
        const gemData = await gemResp.json();
        const raw = gemData.candidates?.[0]?.content?.parts?.[0]?.text || '';
        const lines = raw.split(/[\n;]/).map(t => t.replace(/^[-•*\d.)\s"']+/, '').replace(/["']+$/, '').trim())
          .filter(t => t.length > 0 && t.toUpperCase() !== 'NONE' && t.length < 100);
        if (lines.length > 0) { allResults.push(...lines); engines.push('Gemini'); }
      }
    } catch (e) { console.error('Gemini OCR error:', e.message); }

    // ④ Workers AI llava（始终可用的兜底）
    try {
      const aiRes = await env.AI.run('@cf/llava-hf/llava-1.5-7b-hf', {
        image: [...uint8], prompt: 'List all text on signs, boards, papers in this image. One text per line. If no text, say NONE.', max_tokens: 256,
      });
      const raw2 = aiRes.description || aiRes.response || '';
      const lines = raw2.split(/[\n;]/).map(t => t.replace(/^[-•*\d.)\s"']+/, '').replace(/["']+$/, '').trim())
        .filter(t => t.length > 0 && t.toUpperCase() !== 'NONE' && t.length < 100);
      if (lines.length > 0) { allResults.push(...lines); engines.push('Workers AI'); }
    } catch (e) { console.error('Workers OCR error:', e.message); }

    // 融合结果：去重，多引擎命中的文字优先排前
    const textFreq = {};
    allResults.forEach(t => { textFreq[t] = (textFreq[t] || 0) + 1; });
    const uniqueTexts = Object.entries(textFreq)
      .sort((a, b) => b[1] - a[1]) // 按命中次数降序
      .map(([t]) => t)
      .slice(0, 30);

    const engineLabel = engines.length > 0 ? engines.join(' → ') : '无可用引擎';
    return { texts: uniqueTexts, provider: engineLabel,
      _summary: `${uniqueTexts.length} text regions (${engineLabel})`,
      _findings: uniqueTexts.slice(0, 5).map(t => `"${t}"`),
      _insight: { summary: uniqueTexts.length > 0 ? `发现 ${uniqueTexts.length} 个文字区域 (${engines.length} 引擎交叉验证)` : '所有引擎均未检测到文字', results: [
        { label: '识别文字', value: uniqueTexts.length > 0 ? uniqueTexts : ['未检测到文字'] },
        { label: '引擎', value: engineLabel },
        { label: '交叉验证', value: uniqueTexts.filter(t => textFreq[t] > 1).length > 0 ? `${uniqueTexts.filter(t => textFreq[t] > 1).length} 个文字被多引擎确认` : '单引擎结果' },
      ] }
    };
  });

  // ③ VLM 场景分析
  const vlm = await stage('vlm_analysis', 'VLM 场景理解', '👁️', 'Workers AI Llava', 45, async () => {
    const ocrHint = ocr.texts?.length > 0 ? ` Visible text: ${ocr.texts.join(', ')}.` : '';
    const ai = await env.AI.run('@cf/llava-hf/llava-1.5-7b-hf', {
      image: [...uint8], max_tokens: 512,
      prompt: `Describe this image: 1) scene type (street/indoor/outdoor/restaurant/nature/urban), 2) specific location or country, 3) time of day, 4) season, 5) objects and people, 6) key visual evidence.${ocrHint}`,
    });
    const raw = ai.description || ai.response || '';
    const parsed = parseVLM(raw);
    const results = [{ label: '场景', value: parsed.scene_type }, { label: '描述', value: (parsed.description||'').substring(0,150) }];
    if (parsed.location_guess) results.push({ label: '地点', value: `${parsed.location_guess.location} (${Math.round((parsed.location_guess.confidence||0)*100)}%)` });
    if (parsed.time_guess) results.push({ label: '时间', value: [parsed.time_guess.time_of_day, parsed.time_guess.season].filter(s=>s&&s!=='unknown').join(' ') });
    if (parsed.key_evidence?.length) results.push({ label: '证据', value: parsed.key_evidence.slice(0,3) });
    return { ...parsed, _summary: parsed.scene_type, _findings: [`场景: ${parsed.scene_type}`, parsed.location_guess ? `地点: ${parsed.location_guess.location}` : ''], _insight: { summary: `${parsed.scene_type} | ${(parsed.description||'').substring(0,60)}...`, results } };
  });

  // ④ 实体抽取
  const entity = await stage('entity_extraction', '实体抽取', '🏷️', 'NLP 规则', 60, async () => {
    const ent = extractEntities(vlm, ocr.texts || []);
    const cnt = `${ent.brands.length} 品牌, ${ent.landmarks.length} 地标, ${ent.search_keywords.length} 搜索词`;
    const results = [];
    if (ent.brands.length) results.push({ label: '品牌', value: ent.brands });
    if (ent.landmarks.length) results.push({ label: '地标', value: ent.landmarks });
    if (ent.search_keywords.length) results.push({ label: '搜索词', value: ent.search_keywords });
    return { ...ent, _summary: cnt, _findings: ent.search_keywords.slice(0,3).map(k=>`搜索: ${k}`), _insight: { summary: cnt, results: results.length ? results : [{ label: '结果', value: '未抽取到高价值实体' }] } };
  });

  // ⑤ 多源网络搜索
  const search = await stage('web_search', '联网验证', '🌐', 'Wikipedia + DuckDuckGo', 75, async () => {
    const queries = (entity.search_keywords || []).slice(0, 3);
    const results = [];

    for (const q of queries) {
      // Wikipedia
      try {
        const wResp = await fetch(`https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(q)}`, { headers: { 'User-Agent': 'VIA/1.0' }, signal: AbortSignal.timeout(4000) });
        if (wResp.ok) { const wd = await wResp.json(); if (wd.title && wd.extract && !wd.title.includes('may refer to')) results.push({ title: wd.title, snippet: wd.extract.substring(0,200), source: 'wikipedia', url: wd.content_urls?.desktop?.page || '' }); }
      } catch(e) {}

      // DuckDuckGo Instant Answer
      try {
        const ddg = await fetch(`https://api.duckduckgo.com/?q=${encodeURIComponent(q)}&format=json&no_html=1&t=via`, { headers: { 'User-Agent': 'VIA/1.0' }, signal: AbortSignal.timeout(4000) });
        if (ddg.ok) {
          const dd = await ddg.json();
          if (dd.Abstract) results.push({ title: dd.Heading || q, snippet: dd.Abstract.substring(0,200), source: 'duckduckgo', url: dd.AbstractURL || '' });
          for (const t of (dd.RelatedTopics || []).slice(0,2)) { if (t.Text && !results.some(r=>r.snippet===t.Text)) results.push({ title: t.Text.substring(0,50), snippet: t.Text.substring(0,200), source: 'duckduckgo', url: t.FirstURL || '' }); }
        }
      } catch(e) {}
    }

    const resultsItems = [{ label: '搜索词', value: queries }, { label: '结果', value: `${results.length} 条` }];
    results.slice(0,2).forEach(r => resultsItems.push({ label: `[${r.source}] ${r.title}`, value: (r.snippet||'').substring(0,80) }));
    return { queries, results,
      _summary: `${results.length} results from ${queries.length} queries`,
      _findings: queries.map(q=>`搜索: "${q}"`),
      _insight: { summary: queries.length ? `搜索 ${queries.length} 词, ${results.length} 结果` : '无搜索词', results: resultsItems }
    };
  });

  // ⑥ 证据融合
  const fusion = await stage('evidence_fusion', '证据融合', '🔬', '规则推理', 85, async () => {
    const conclusions = fuseEvidence(vlm, ocr.texts||[], entity, search, pre);
    return { conclusions,
      _summary: `${conclusions.length} conclusions`,
      _findings: conclusions.slice(0,3).map(c=>`${c.category}: ${c.statement}`),
      _insight: { summary: `综合 ${conclusions.length} 条结论`, results: conclusions.slice(0,5).map(c=>({ label: c.category, value: `${c.statement} (${Math.round(c.probability*100)}%)` })) }
    };
  });

  // ⑦ 报告生成
  const report = await stage('report_generation', '报告生成', '📊', 'Markdown', 95, async () => {
    const md = genReport(taskId, filename, vlm, ocr.texts||[], entity, search, fusion.conclusions||[]);
    return { md, _summary: `${md.length} chars`, _findings: [`报告: ${md.length} 字符`] };
  });

  trace.total_duration_ms = trace.steps.reduce((s,st) => s + (st.duration_ms||0), 0);
  return { analysis: { ...vlm, ocr_texts: ocr.texts||[], entities: entity, search_results: search.results||[], conclusions: fusion.conclusions||[], report_markdown: report.md||'', image_metadata: { width: pre.w, height: pre.h, format: pre.fmt, file_size: pre.size } }, trace };
}

// ==================== 实体抽取 ====================
function extractEntities(vlm, ocrTexts) {
  const brands = [], landmarks = [], location_keywords = [], search_keywords = [];
  const desc = (vlm.description || '').toLowerCase();

  // 从描述中提取地点关键词
  const descLower = (vlm.description || '').toLowerCase();
  // 匹配 "location: China" 或 "country: China" 格式
  const locNameMatch = (vlm.description || '').match(/(?:location|country|region)[^\w]*[:：]\s*(.{2,40}?)(?:\.|\n|,|$)/i);
  if (locNameMatch) {
    const locName = locNameMatch[1].trim();
    location_keywords.push(locName);
    search_keywords.push(locName);
    const sp = locName.match(/(China|Japan|Korea|Thailand|Vietnam|India|Beijing|Shanghai|Tokyo|Seoul|Bangkok|Singapore|Hong Kong|Taiwan)/gi);
    if (sp) landmarks.push(...sp);
  }

  // 场景关键词 → 搜索词
  const sceneEnts = desc.match(/(chinese|japanese|korean|thai|vietnamese|asian|western)\s+(restaurant|temple|building|garden|market|shop|hotel|palace|pagoda)/gi) || [];
  search_keywords.push(...sceneEnts);

  // OCR 文字中找有意义的搜索词
  for (const t of (ocrTexts || [])) {
    if (t.length >= 2 && !/^(the|this|that|there|is|are|was|a|an)$/i.test(t)) {
      // 含中文直接作为搜索词
      if (/[\u4e00-\u9fff]/.test(t)) search_keywords.push(t);
    }
  }

  // VLM 描述中高频大写词
  const words = desc.match(/\b[A-Z][a-z]{2,}\b/g) || [];
  const freq = {};
  words.forEach(w => { const l = w.toLowerCase(); freq[l] = (freq[l]||0)+1; });
  Object.entries(freq).sort((a,b) => b[1]-a[1]).slice(0,2).forEach(([w,c]) => { if (c >= 2) search_keywords.push(w); });

  return { brands: [...new Set(brands)], landmarks: [...new Set(landmarks)], location_keywords: [...new Set(location_keywords)], search_keywords: [...new Set(search_keywords)].slice(0,5) };
}

// ==================== 证据融合 ====================
function fuseEvidence(vlm, ocrTexts, entity, search, pre) {
  const C = [];
  if (vlm.scene_type && vlm.scene_type !== 'unknown') C.push({ category: 'scene', statement: `场景: ${vlm.scene_type}`, probability: 0.85, sources: ['VLM'] });
  if (vlm.location_guess?.location) {
    let p = vlm.location_guess.confidence || 0.5;
    if ((search.results||[]).some(r => (r.title+(r.snippet||'')).toLowerCase().includes(vlm.location_guess.location.toLowerCase()))) p = Math.min(p+0.15,0.99);
    if ((ocrTexts||[]).some(t => t.includes(vlm.location_guess.location))) p = Math.min(p+0.1,0.99);
    C.push({ category: 'location', statement: `地点: ${vlm.location_guess.location}`, probability: p, sources: ['VLM', ...(search.results?.length ? ['Search'] : [])] });
  }
  if (vlm.time_guess) { const ts = [vlm.time_guess.time_of_day, vlm.time_guess.season].filter(s=>s&&s!=='unknown').join(' '); if (ts) C.push({ category: 'time', statement: `时间: ${ts}`, probability: 0.6, sources: ['VLM'] }); }
  if (ocrTexts.length > 0) C.push({ category: 'text', statement: `文字: ${ocrTexts.slice(0,5).join(', ')}`, probability: 0.9, sources: ['OCR'] });
  if ((search.results||[]).length > 0) C.push({ category: 'search', statement: `搜索: ${(search.results||[]).map(r=>r.title).join(', ')}`, probability: 0.7, sources: ['Wikipedia','DuckDuckGo'] });
  return C;
}

// ==================== 报告生成 ====================
function genReport(tid, fn, vlm, ocrTxts, ent, srch, concl) {
  let m = `# 图片分析报告\n\n**任务 ID**: ${tid}\n**文件**: ${fn||'未知'}\n**时间**: ${new Date().toISOString()}\n\n---\n\n`;
  if (vlm.description) m += `## 📋 场景描述\n\n${vlm.description}\n\n`;
  if (vlm.scene_type && vlm.scene_type !== 'unknown') m += `## 🏷️ 场景类型\n\n**${vlm.scene_type}**\n\n`;
  if (vlm.location_guess) { m += `## 📍 地点推测\n\n- **地点**: ${vlm.location_guess.location||'未知'}\n- **置信度**: ${Math.round((vlm.location_guess.confidence||0)*100)}%\n`; if (vlm.location_guess.evidence) m += `- **依据**: ${vlm.location_guess.evidence}\n`; m += '\n'; }
  if (vlm.time_guess) { m += `## ⏰ 时间推测\n\n`; const td = vlm.time_guess.time_of_day, ss = vlm.time_guess.season; if (td && td !== 'unknown') m += `- **时段**: ${td}\n`; if (ss && ss !== 'unknown') m += `- **季节**: ${ss}\n`; m += '\n'; }
  if (ocrTxts.length > 0) { m += `## 📝 检测文字\n\n`; ocrTxts.forEach(t => m += `- \`${t}\`\n`); m += '\n'; }
  if (srch.results?.length > 0) { m += `## 🌐 联网验证\n\n`; srch.results.forEach(r => { m += `### ${r.title}\n${r.snippet||''}\n${r.url?`[详情](${r.url})\n`:''}\n`; }); }
  if (vlm.key_evidence?.length) { m += `## 🔍 关键证据\n\n`; vlm.key_evidence.slice(0,5).forEach(e => m += `- ${e}\n`); m += '\n'; }
  if (concl.length > 0) { m += `## 🧪 综合结论\n\n| 结论 | 置信度 | 来源 |\n|------|--------|------|\n`; concl.forEach(c => m += `| ${c.statement} | ${Math.round(c.probability*100)}% | ${c.sources.join(', ')} |\n`); m += '\n'; }
  return m;
}

// ==================== VLM 响应解析 ====================
function parseVLM(text) {
  if (!text) return { scene_type: 'unknown', description: '无响应' };
  const jr = parseJSON(text);
  if (jr.scene_type && jr.scene_type !== 'unknown' && jr.description !== text) return jr;
  const r = { scene_type: 'unknown', description: text.trim(), detected_text: [], key_evidence: [] };
  // 场景类型 - 多种格式匹配
  const scenePatterns = [
    /scene\s*(?:type)?\s*[:：]\s*(.{3,50}?)(?:\.|\n|,|$)/i,
    /(?:scene|image|photo)\s+(?:is|shows|depicts|features)\s+(?:a |an |the )?(.{5,50}?)(?:\.|,|$)/i,
    /(?:located|situated|set|found)\s+(?:in|at)\s+(?:a |an |the )?(.{3,50}?)(?:[,\.\n]|$)/i,
  ];
  for (const p of scenePatterns) { const m = text.match(p); if (m) { r.scene_type = m[1].trim(); break; } }
  for (const p of [/(?:located|situated|set|found|taken)\s+(?:in|at|on)\s+(?:the\s+)?(.{3,50}?)(?:\.|,|$)/i, /(?:country|region|place)\s+(?:is|appears)\s+(?:to be\s+)?(.{3,50}?)(?:\.|,|$)/i]) {
    const m = text.match(p);
    if (m) { let loc = m[1].trim().replace(/^(an?|the)\s+/i,''); const sp = loc.match(/\b(China|Japan|Korea|Thailand|Vietnam|India|Beijing|Shanghai|Tokyo|Seoul|Bangkok|Singapore|Hong Kong|Taiwan)\b/i); if (sp) loc = sp[0]; r.location_guess = { location: loc, confidence: 0.6, evidence: m[0].trim() }; break; }
  }
  const l = text.toLowerCase();
  let tod = 'unknown', season = 'unknown';
  for (const [w,v] of Object.entries({morning:'morning',afternoon:'afternoon',evening:'evening',night:'night',daytime:'daytime',daylight:'daytime'})) { if (l.includes(w)) { tod = v; break; } }
  for (const [w,v] of Object.entries({spring:'spring',summer:'summer',fall:'fall',winter:'winter',autumn:'fall'})) { if (l.includes(w)) { season = v; break; } }
  if (tod !== 'unknown' || season !== 'unknown') r.time_guess = { time_of_day: tod, season, evidence: '' };
  const sents = text.split(/[.!?]/).filter(s => s.trim().length > 10);
  const evSents = sents.filter(s => /(?:evidence|suggest|indicate|appear|seem|likely|probably|because|due|based|visible|presence)/i.test(s));
  if (evSents.length) r.key_evidence = evSents.map(s => s.trim()).slice(0,5);
  return r;
}

function parseJSON(text) {
  if (!text) return { scene_type: 'unknown' };
  const c = text.replace(/\\_/g,'_').replace(/\\\//g,'/').replace(/\\\*/g,'*').replace(/```json\s*/g,'').replace(/```\s*/g,'');
  const m = c.match(/\{[\s\S]*\}/);
  if (!m) return { scene_type: 'unknown', description: text };
  try { return JSON.parse(m[0]); } catch(e) { try { return JSON.parse(m[0].replace(/\\(?=[^"\\])/g,'')); } catch(e2) { return { scene_type: 'unknown', description: text }; } }
}

// ==================== 报告 & 事件 API ====================
async function handleReport(url, env, cors) {
  const tid = url.pathname.split('/api/report/')[1]?.split('?')[0];
  try {
    const r = await env.DB.prepare('SELECT * FROM analyses WHERE id = ?').bind(tid).first();
    if (!r) return json({ error: 'Not found' }, 404, cors);
    const a = r.result ? JSON.parse(r.result) : null;
    return json({ id: r.id, task_id: r.id, status: r.status, filename: r.filename, created_at: r.created_at, completed_at: r.completed_at, analysis: a, error: r.error?.startsWith('[') ? null : r.error }, 200, cors);
  } catch (e) { return json({ error: e.message }, 500, cors); }
}

async function handleEvents(url, env, cors) {
  return json({ message: 'Events are now streamed via SSE during analysis. Use POST /api/analyze with EventSource.' }, 200, cors);
}

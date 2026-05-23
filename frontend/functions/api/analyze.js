// Cloudflare Pages Function — 图片分析 API
// 使用 Workers AI + R2 + D1 实现纯 Cloudflare 方案

export async function onRequestPost(context) {
  const { request, env } = context;

  try {
    // 1. 解析上传的图片
    const formData = await request.formData();
    const file = formData.get('file');

    if (!file) {
      return Response.json({ error: 'No file uploaded' }, { status: 400 });
    }

    const buffer = await file.arrayBuffer();
    const taskId = crypto.randomUUID().slice(0, 8);

    // 2. 上传到 R2 存储
    await env.IMAGE_BUCKET.put(`${taskId}/${file.name}`, buffer, {
      httpMetadata: { contentType: file.type },
    });

    // 3. 创建待处理记录到 D1
    await env.DB.prepare(
      'INSERT INTO analyses (id, status, filename, created_at) VALUES (?, ?, ?, ?)'
    ).bind(taskId, 'processing', file.name, new Date().toISOString()).run();

    // 4. 异步处理（使用 Workers AI）
    // 使用 waitUntil 进行异步处理
    const processingPromise = processImage(env, taskId, buffer, file.type);
    if (context.waitUntil) {
      context.waitUntil(processingPromise);
    } else {
      // Fallback: 不等待异步处理
      processingPromise.catch(console.error);
    }

    return Response.json({
      task_id: taskId,
      status: 'processing',
      message: 'Analysis started. Poll /api/report/{task_id} for results.',
    });

  } catch (error) {
    console.error('Error:', error);
    return Response.json({ error: error.message }, { status: 500 });
  }
}

// 异步处理图片
async function processImage(env, taskId, imageBuffer, mimeType) {
  try {
    // 使用 Workers AI 进行图像分析
    const analysis = await env.AI.run('@cf/llava-hf/llava-1.5-7b-hf', {
      image: [...new Uint8Array(imageBuffer)],
      prompt: `分析这张图片，用 JSON 格式回答：
{
  "scene_type": "场景类型",
  "description": "详细描述",
  "location_guess": {"location": "可能的地点", "confidence": 0.0-1.0},
  "time_guess": {"time_of_day": "时间段", "season": "季节"},
  "detected_text": ["图中文字"],
  "key_evidence": ["关键证据"]
}`,
      max_tokens: 1024,
    });

    // 解析 AI 响应 - 处理 Markdown 转义字符
    let result;
    try {
      // 先清理 Markdown 转义（llava 可能返回 \\/ \\_ \\* 等）
      const cleanedResponse = analysis.response
        .replace(/\\_/g, '_')
        .replace(/\\\//g, '/')
        .replace(/\\\*/g, '*');
      const jsonMatch = cleanedResponse.match(/\{[\s\S]*\}/);
      result = jsonMatch ? JSON.parse(jsonMatch[0]) : { description: analysis.response };
    } catch {
      // 尝试更激进的清理：移除所有反斜杠转义
      try {
        const stripped = analysis.response.replace(/\\(?=[^"\\])/g, '');
        const jsonMatch2 = stripped.match(/\{[\s\S]*\}/);
        result = jsonMatch2 ? JSON.parse(jsonMatch2[0]) : { description: analysis.response };
      } catch {
        result = { description: analysis.response };
      }
    }

    // 更新 D1 记录
    await env.DB.prepare(
      'UPDATE analyses SET status = ?, result = ?, completed_at = ? WHERE id = ?'
    ).bind('completed', JSON.stringify(result), new Date().toISOString(), taskId).run();

  } catch (error) {
    console.error('Processing error:', error);
    await env.DB.prepare(
      'UPDATE analyses SET status = ?, error = ? WHERE id = ?'
    ).bind('failed', error.message, taskId).run();
  }
}

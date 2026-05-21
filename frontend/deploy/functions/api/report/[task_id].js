// Cloudflare Pages Function — 查询分析结果

export async function onRequestGet(context) {
  const { params, env } = context;
  const { task_id } = params;

  try {
    // 从 D1 查询结果
    const result = await env.DB.prepare(
      'SELECT * FROM analyses WHERE id = ?'
    ).bind(task_id).first();

    if (!result) {
      return Response.json({ error: 'Task not found' }, { status: 404 });
    }

    // 解析 JSON 结果
    const analysis = result.result ? JSON.parse(result.result) : null;

    return Response.json({
      id: result.id,
      status: result.status,
      filename: result.filename,
      created_at: result.created_at,
      completed_at: result.completed_at,
      analysis: analysis,
      error: result.error,
    });

  } catch (error) {
    console.error('Error:', error);
    return Response.json({ error: error.message }, { status: 500 });
  }
}

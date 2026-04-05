import os
from pathlib import Path
import re

html_path = Path('/home/ubuntu/http-server/dev/openharness-desktop-electron/apps/host-python/frontend/index.html')
html = html_path.read_text()

# Patch sendMsg
old_sendMsg = """function sendMsg() {
  const input = $('#msgInput');
  const text = input.value.trim();
  if (!text && pendingAttachments.length === 0) return;
  if (busy) return;

  // Build full message with file references
  let fullText = text;
  if (pendingAttachments.length > 0) {
    const fileRefs = pendingAttachments.map(a => {
      return `[File: ${a.name} (attached)]`;
    }).join('\n');
    fullText = (text ? text + '\n\n' : '') + fileRefs;
  }

  window._lastSubmitted = fullText;
  addMsgToUI('user', text || `Uploaded ${pendingAttachments.length} files`);
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'session.submit', payload: { text: fullText } }));
  }
  input.value = '';
  input.style.height = 'auto';
  pendingAttachments = [];
  renderAttachments();
  setBusy(true);
}"""

new_sendMsg = """function sendMsg() {
  const input = $('#msgInput');
  const text = input.value.trim();
  if (!text && pendingAttachments.length === 0) return;
  if (busy) return;

  window._lastSubmitted = text || `Uploaded ${pendingAttachments.length} files`;
  addMsgToUI('user', window._lastSubmitted);
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ 
      type: 'session.submit', 
      payload: { 
        text: text, 
        attachments: pendingAttachments.map(a => ({ name: a.name, base64: a.base64 })) 
      } 
    }));
  }
  input.value = '';
  input.style.height = 'auto';
  pendingAttachments = [];
  renderAttachments();
  setBusy(true);
}"""
html = html.replace(old_sendMsg, new_sendMsg)

# Patch event matching for user message
old_transcript = """      if (payload.role === 'user' && payload.text === window._lastSubmitted) {
        return;
      }"""
new_transcript = """      if (payload.role === 'user' && payload.text.startsWith(window._lastSubmitted)) {
        return;
      }"""
html = html.replace(old_transcript, new_transcript)

# Patch renderArtifactList
old_renderArtifactList = """function renderArtifactList() {
  const list = $('#artifactList');
  if (!artifacts.length) {
    list.innerHTML = '<div style="color:var(--text-dim);text-align:center;padding:40px 0;font-size:13px;">No artifacts in this session.</div>';
    return;
  }
  list.innerHTML = artifacts.map(a => `
    <div class="artifact-item-card" onclick="showArtifactPreview('${a.artifact_id}')">
      <div style="font-size:13px;font-weight:600;">${esc(a.file_path || a.tool_name)}</div>
      <div style="font-size:11px;color:var(--text-dim);margin-top:4px;">${a.artifact_type} · ${new Date(a.created_at * 1000).toLocaleTimeString()}</div>
    </div>
  `).join('');
}"""

new_renderArtifactList = """function renderArtifactList() {
  const list = $('#artifactList');
  if (!artifacts.length) {
    list.innerHTML = '<div style="color:var(--text-dim);text-align:center;padding:40px 0;font-size:13px;">No artifacts in this session.</div>';
    return;
  }
  list.innerHTML = artifacts.map(a => `
    <div class="artifact-item-card" onclick="showArtifactPreview('${a.artifact_id}')">
      <div style="font-size:13px;font-weight:600;display:flex;justify-content:space-between;">
        <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(a.file_path || a.tool_name)}</span>
        <div style="display:flex;gap:4px;flex-shrink:0;">
          <button onclick="event.stopPropagation(); showArtifactPreview('${a.artifact_id}')" style="background:transparent;border:1px solid var(--border);color:var(--text);border-radius:4px;padding:2px 6px;font-size:11px;cursor:pointer;">打开</button>
          <button onclick="event.stopPropagation(); window.open('/api/artifacts/' + '${a.artifact_id}' + '/download', '_blank')" style="background:transparent;border:1px solid var(--border);color:var(--text);border-radius:4px;padding:2px 6px;font-size:11px;cursor:pointer;">下载</button>
        </div>
      </div>
      <div style="font-size:11px;color:var(--text-dim);margin-top:4px;">${a.artifact_type} · ${new Date(a.created_at * 1000).toLocaleTimeString()}</div>
    </div>
  `).join('');
}"""
html = html.replace(old_renderArtifactList, new_renderArtifactList)

# Patch showArtifactPreview
old_showArtifactPreview = """async function showArtifactPreview(id) {
  $('#artifactPreview').classList.remove('hidden');
  $('#previewContent').textContent = 'Loading...';
  try {
    const res = await fetch(`${API_BASE}/api/artifacts/${id}/preview`);
    const contentType = res.headers.get('content-type');
    if (contentType.includes('image')) {
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      $('#previewContent').innerHTML = `<img src="${url}" style="max-width:100%; border-radius:8px;" />`;
    } else {
      const text = await res.text();
      $('#previewContent').innerHTML = `<pre style="font-size:12px; overflow-x:auto;">${esc(text)}</pre>`;
    }
  } catch (e) { $('#previewContent').textContent = 'Error loading preview.'; }
}"""

new_showArtifactPreview = """async function showArtifactPreview(id) {
  $('#artifactPreview').classList.remove('hidden');
  $('#previewContent').textContent = 'Loading...';
  try {
    const res = await fetch(`${API_BASE}/api/artifacts/${id}/preview`);
    const contentType = res.headers.get('content-type');
    if (contentType && contentType.includes('image')) {
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      $('#previewContent').innerHTML = `<img src="${url}" style="max-width:100%; border-radius:8px;" />`;
    } else {
      const text = await res.text();
      const lowerText = text.trim().toLowerCase();
      const isHtml = (contentType && contentType.includes('html')) || lowerText.startsWith('<html') || lowerText.startsWith('<!doctype');
      if (isHtml) {
        const iframe = document.createElement('iframe');
        iframe.style.cssText = 'width:100%; height:400px; border:none; background:#fff; border-radius:8px;';
        iframe.srcdoc = text;
        $('#previewContent').innerHTML = '';
        $('#previewContent').appendChild(iframe);
      } else {
        $('#previewContent').innerHTML = `<pre style="font-size:12px; overflow-x:auto;">${esc(text)}</pre>`;
      }
    }
  } catch (e) { $('#previewContent').textContent = 'Error loading preview.'; }
}"""
html = html.replace(old_showArtifactPreview, new_showArtifactPreview)

html_path.write_text(html)

print("index.html patched")

server_path = Path('/home/ubuntu/http-server/dev/openharness-desktop-electron/apps/host-python/src/host_mvp/ws_server.py')
server = server_path.read_text()

# Patch ws_endpoint
old_ws_endpoint = """            elif t == "session.submit":
                text = data.get("payload", {}).get("text", "")
                await s.handle_submit(text)"""

new_ws_endpoint = """            elif t == "session.submit":
                text = data.get("payload", {}).get("text", "")
                attachments = data.get("payload", {}).get("attachments", [])
                await s.handle_submit(text, attachments=attachments)"""
server = server.replace(old_ws_endpoint, new_ws_endpoint)

# Patch handle_submit signature
old_handle_submit = """    async def handle_submit(self, text: str):
        \"\"\"处理用户消息.\"\"\"
        if self.busy:"""

new_handle_submit = """    async def handle_submit(self, text: str, attachments: list[dict] = None):
        \"\"\"处理用户消息.\"\"\"
        if attachments:
            att_dir = Path.home() / ".openharness" / "attachments" / self.session_id
            att_dir.mkdir(parents=True, exist_ok=True)
            for att in attachments:
                name = att.get("name", "unnamed")
                b64 = att.get("base64", "")
                if b64:
                    file_path = att_dir / name
                    file_path.write_bytes(base64.b64decode(b64))
                    text += f"\\n\\n[附件文件: {file_path}]"

        if self.busy:"""
server = server.replace(old_handle_submit, new_handle_submit)

# Add download endpoint
old_preview_artifact = """@app.get("/api/artifacts/{artifact_id}/preview")"""

download_endpoint = """@app.get("/api/artifacts/{artifact_id}/download")
async def download_artifact(artifact_id: str):
    artifact = db_get_artifact(artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="artifact not found")

    display_name = _artifact_display_name(artifact)
    from urllib.parse import quote
    encoded_name = quote(display_name)
    headers = {
        "X-Artifact-Name": display_name,
        "X-Artifact-Type": artifact.artifact_type or "text",
        "Content-Disposition": f"attachment; filename*=utf-8''{encoded_name}"
    }

    file_path = Path(artifact.file_path).expanduser() if artifact.file_path else None
    if file_path and file_path.exists() and file_path.is_file():
        mime, _ = mimetypes.guess_type(str(file_path))
        mime = mime or "application/octet-stream"
        return FileResponse(file_path, media_type=mime, filename=display_name, headers=headers)

    content = artifact.content or ""
    artifact_type = (artifact.artifact_type or "text").lower()

    if artifact_type in {"image", "pdf"}:
        mime, decoded = _decode_data_url(content)
        if decoded is not None:
            return Response(content=decoded, media_type=mime or ("image/png" if artifact_type == "image" else "application/pdf"), headers=headers)
        try:
            decoded = base64.b64decode(content, validate=True)
            media_type = "image/png" if artifact_type == "image" else "application/pdf"
            return Response(content=decoded, media_type=media_type, headers=headers)
        except Exception:
            if artifact_type == "pdf":
                return PlainTextResponse(content, media_type="text/plain", headers=headers)

    return PlainTextResponse(content, media_type="text/plain", headers=headers)

@app.get("/api/artifacts/{artifact_id}/preview")"""
server = server.replace(old_preview_artifact, download_endpoint)

# Patch ToolExecutionCompleted
old_tool_exec = """        elif isinstance(event, ToolExecutionCompleted):
            artifact_output = event.output if isinstance(event.output, str) else json.dumps(event.output, ensure_ascii=False, indent=2)

            # 工具结果 → SQLite
            save_message(MessageRecord(
                session_id=self._db_session_id,
                role="tool_result",
                content=artifact_output,
                tool_name=event.tool_name,
                tool_output=artifact_output,
                is_error=event.is_error,
                seq=self._msg_seq,
                created_at=time.time(),
            ))
            create_artifact(
                session_id=self._db_session_id,
                tool_name=event.tool_name,
                artifact_type="error" if event.is_error else ("text" if isinstance(event.output, str) else "json"),
                content=artifact_output,
                file_path="",
            )"""

new_tool_exec = """        elif isinstance(event, ToolExecutionCompleted):
            artifact_output = event.output if isinstance(event.output, str) else json.dumps(event.output, ensure_ascii=False, indent=2)
            artifact_type = "error" if event.is_error else ("text" if isinstance(event.output, str) else "json")

            if not event.is_error and isinstance(event.output, str):
                import re
                match = re.search(r'(/[^ ]+\.(?:png|jpg|jpeg|svg|gif))', event.output, re.IGNORECASE)
                if match:
                    img_path = Path(match.group(1))
                    if img_path.exists() and img_path.is_file():
                        try:
                            b64 = base64.b64encode(img_path.read_bytes()).decode("utf-8")
                            mime, _ = mimetypes.guess_type(str(img_path))
                            artifact_output = f"data:{mime or 'image/png'};base64,{b64}"
                            artifact_type = "image"
                        except Exception:
                            pass

            # 工具结果 → SQLite
            save_message(MessageRecord(
                session_id=self._db_session_id,
                role="tool_result",
                content=artifact_output,
                tool_name=event.tool_name,
                tool_output=artifact_output,
                is_error=event.is_error,
                seq=self._msg_seq,
                created_at=time.time(),
            ))
            create_artifact(
                session_id=self._db_session_id,
                tool_name=event.tool_name,
                artifact_type=artifact_type,
                content=artifact_output,
                file_path="",
            )"""
server = server.replace(old_tool_exec, new_tool_exec)

server_path.write_text(server)
print("ws_server.py patched")

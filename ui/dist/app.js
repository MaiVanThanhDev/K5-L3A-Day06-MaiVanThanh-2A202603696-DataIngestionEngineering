"use strict";
const $ = id => document.getElementById(id);
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const textBlock = text => `<div class="source-text">${esc(text)}</div>`;
const meta = data => `<pre class="metadata">${esc(JSON.stringify(data, null, 2))}</pre>`;
let data, dirty = false, currentKind = "coherence", currentIndex = 0, currentChunk = 0;
function status(message = "", error = false) { $("status").textContent = message; $("status").classList.toggle("error", error); }
async function api(path, body) {
  const response = await fetch(path, body ? {method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(body)} : {});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Không đọc được dữ liệu.");
  return result;
}
function canLeave() { return !dirty || window.confirm("Nhãn đang sửa chưa lưu. Bỏ thay đổi này?"); }
function showView(view) {
  if (!canLeave()) return;
  dirty = false;
  if (data) renderAudit();
  document.querySelectorAll(".view").forEach(el => el.hidden = el.id !== view);
  document.querySelectorAll(".nav").forEach(el => { el.classList.toggle("active", el.dataset.view === view); if(el.dataset.view === view) el.setAttribute("aria-current", "page"); else el.removeAttribute("aria-current"); });
}
function overview() {
  $("stats").innerHTML = [
    ["TRANG NỘI DUNG",data.validation.content_pages,"/ 54","Trang PDF 16–23, 28–51"],
    ["BỘ BENCHMARK",data.validation.questions,"câu","15 dev · 5 test · 4 câu có filter"],
    ["CHUNK ĐÃ LƯU",Object.values(data.validation.chunk_counts).reduce((a,b)=>a+b,0),"chunk","A: 66 · B: 69 · C: 69"],
    ["CHIẾN LƯỢC CHỌN",data.selection.selected_strategy,"","Theo Evidence Hit@3 trên dev"]
  ].map(([label,value,unit,note])=>`<article class="stat"><div class="stat-label">${label}</div><div class="stat-number">${esc(value)}<small>${unit}</small></div><div class="stat-note">${note}</div></article>`).join("");
  $("strategy-table").innerHTML = ["A","B","C"].map(s=>`<tr><td><strong class="strategy-name">${s}</strong>${s === "C" ? '<span class="strategy-note">Đã chọn</span>' : ""}</td><td>${s === "A" ? "Cố định · 900 ký tự" : "Theo đoạn · tối đa 900 ký tự"}</td><td>${s === "A" ? "90 ký tự" : "0"}</td><td>${s === "C" ? "Theo yêu cầu câu hỏi" : "Không"}</td><td>${data.validation.chunk_counts[s]}</td></tr>`).join("");
  renderMetrics(); progress();
}
function renderMetrics() {
  const split = $("metric-split").value;
  $("metric-bars").innerHTML = ["A","B","C"].map(s=>{ const r=data.metrics[`${s}/${split}`]; return `<div class="metric-row"><b>${s}</b><div class="bar-track"><div class="bar ${s===data.selection.selected_strategy?"selected":""}" id="bar-${s}"></div></div><strong>${r.hit3_n}/${r.questions}<small>${(r.hit3*100).toFixed(0)}%</small></strong></div>`; }).join("");
  for (const s of "ABC") $(`bar-${s}`).style.width = `${data.metrics[`${s}/${split}`].hit3*100}%`;
}
function progress() {
  const n = Object.values(data.audits).reduce((a,s)=>a+s.completed,0), total=Object.values(data.audits).reduce((a,s)=>a+s.total,0);
  $("audit-progress").style.width = `${n/total*100}%`;
  $("audit-count").textContent = `${n} / ${total} mẫu đã chấm`;
  $("nav-count").textContent = `${n}/${total}`;
  $("audit-description").textContent = n === total ? "Đã đủ nhãn. Bạn có thể tổng hợp và cập nhật bảng điểm trong báo cáo." : "Coherence, metadata và grounding cần nhãn của người chấm để hoàn thiện báo cáo.";
  $("sync-report").disabled = n !== total;
}
function renderChunks() {
  const strategy=$("chunk-strategy").value, query=$("chunk-search").value.toLocaleLowerCase("vi").trim();
  const rows=data.chunks[strategy].map((row,index)=>({row,index})).filter(({row})=>!query||row.text.toLocaleLowerCase("vi").includes(query)||String(row.page)===query);
  $("chunk-count").textContent=`${rows.length} chunk`;
  if(!rows.some(r=>r.index===currentChunk)) currentChunk=rows[0]?.index ?? -1;
  $("chunk-list").innerHTML=rows.length?rows.map(({row,index})=>`<button class="record ${index===currentChunk?"active":""}" data-chunk="${index}"><strong>Trang ${row.page} <span>· ${strategy}${String(index+1).padStart(2,"0")}</span></strong><p>${esc(row.text.slice(0,115))}…</p><small>${esc(row.metadata.category)} · ${row.text.length} ký tự</small></button>`).join(""):'<div class="empty">Không tìm thấy chunk phù hợp.</div>';
  const row=data.chunks[strategy][currentChunk];
  if(!row) { $("chunk-detail").innerHTML='<div class="empty">Thử từ khóa khác để tìm nội dung.</div>'; return; }
  const page=data.pages.find(p=>p.page===row.page);
  $("chunk-detail").innerHTML=`<div class="panel-heading"><div><h2>Trang ${row.page} · ${esc(row.metadata.section)}</h2><p>${esc(row.source)} · ${row.text.length} ký tự</p></div><span class="pill">Chiến lược ${strategy}</span></div>${textBlock(row.text)}<details class="details-text"><summary>Metadata & ID</summary>${meta(row.metadata)}<code class="chunk-id">${esc(row.chunk_id)}</code></details><details class="details-text"><summary>Đối chiếu toàn trang nguồn</summary>${textBlock(page?.text || "Không có trang nguồn.")}</details>`;
}
function renderQuestions() {
  const old=$("trace-question").value;
  const traces=data.traces.filter(t=>t.strategy===$("trace-strategy").value&&t.split===$("trace-split").value);
  $("trace-question").innerHTML=traces.map(t=>`<option value="${esc(t.question_id)}">${esc(t.question_id)} · ${esc(t.question.slice(0,100))}</option>`).join("");
  if(traces.some(t=>t.question_id===old)) $("trace-question").value=old;
  renderTrace();
}
function hitCard(hit) { return `<article class="panel"><div class="rank">HẠNG ${hit.rank} · score ${Number(hit.score).toFixed(4)}</div><h2>Trang ${esc(hit.metadata.page)}</h2><span class="pill">${hit.evidence_hit?"Đủ evidence đã đăng ký":"Chưa khớp đủ gold"}</span>${textBlock(hit.text)}<details class="details-text"><summary>Metadata</summary>${meta(hit.metadata)}</details></article>`; }
function renderTrace() {
  const t=data.traces.find(t=>t.strategy===$("trace-strategy").value&&t.split===$("trace-split").value&&t.question_id===$("trace-question").value);
  if(!t) return;
  $("trace-detail").innerHTML=`<div class="trace-top"><div class="tags"><span class="pill">${esc(t.question_id)} / ${esc(t.split)} / ${t.strategy}</span><span class="pill">Hit@1 ${t.hit1?"✓":"—"} · Hit@3 ${t.hit3?"✓":"—"}</span></div><h2>${esc(t.question)}</h2><p><b>Đáp án kỳ vọng:</b> ${esc(t.expected_answer)}</p><details><summary>Evidence & filter đã đăng ký</summary>${t.gold.map(g=>`<blockquote class="gold">Trang ${g.page}: ${esc(g.evidence_quote)}</blockquote>`).join("")}${meta({requested_filter:t.requested_filter,applied_filter:t.applied_filter})}</details></div><div class="hits-grid">${t.hits.map(hitCard).join("")}</div>`;
}
const rubrics={coherence:"0 = bị cắt giữa ý / không hiểu; 1 = hiểu một phần, thiếu ngữ cảnh; 2 = tự hiểu được và giữ trọn ý. Đối chiếu chunk với trang nguồn.",metadata:"Đối chiếu source, page và các trường metadata với nguồn. Đủ trường chưa chứng minh đúng. Với câu có filter, chấm tuân thủ phạm vi người hỏi yêu cầu, kể cả A/B không áp dụng lọc.",grounding:"0 = không có bằng chứng; 1 = có nhưng thiếu điều kiện / ngữ cảnh; 2 = đủ để trả lời và truy nguồn. Chấm toàn bộ top-3; Hit@3 tự động không thay nhãn của bạn."};
function auditOptions() {
  const rows=data.audits[currentKind].rows;
  const indices=rows.map((r,i)=>i).filter(i=>rows[i].strategy===$("audit-strategy").value);
  if(!indices.includes(currentIndex)) currentIndex=indices[0];
  const label=currentKind==="metadata"?"complete_and_correct":"label_0_1_2";
  $("audit-record").innerHTML=indices.map(i=>`<option value="${i}">${rows[i][label]===null?"○":"✓"} ${rows[i].question_id||`Trang ${rows[i].page}`} ${rows[i].chunk_id?"· "+rows[i].chunk_id.slice(0,8):""}</option>`).join("");
  $("audit-record").value=currentIndex;
  renderAudit();
}
function renderAudit() {
  if(!data) return;
  const state=data.audits[currentKind], r=state.rows[currentIndex];
  if(!r) return;
  $("audit-kind-count").textContent=`${state.completed}/${state.total} đã chấm`;
  $("rubric").textContent=rubrics[currentKind];
  $("audit-score").innerHTML='<option value="">Chọn nhãn…</option>'+(currentKind==="metadata"?'<option value="true">Đủ và đúng</option><option value="false">Thiếu hoặc sai</option>':'<option value="0">0 · Không đạt</option><option value="1">1 · Một phần</option><option value="2">2 · Đầy đủ</option>');
  const label=currentKind==="metadata"?"complete_and_correct":"label_0_1_2";
  $("audit-score").value=r[label]===null?"":String(r[label]);
  $("reason").value=r.reason;
  $("reviewer").value=r.reviewer || $("reviewer").value;
  $("filter-label").hidden=currentKind!=="metadata"||!Object.keys(r.requested_filter).length;
  $("audit-filter").required=!$("filter-label").hidden;
  $("audit-filter").value=r.obeys_requested_filter===null||r.obeys_requested_filter===undefined?"":String(r.obeys_requested_filter);
  if(currentKind==="coherence") {
    $("audit-evidence").innerHTML=`<h2>Trang ${r.page} · Chiến lược ${r.strategy}</h2><p class="muted">Chunk tại vị trí ${r.anchor} của trang nguồn</p>${textBlock(r.text)}<details class="details-text" open><summary>Trang nguồn để đối chiếu</summary>${textBlock(r.source_context)}</details>`;
  } else {
    const trace=data.traces.find(t=>t.strategy===r.strategy&&t.question_id===r.question_id&&t.split==="test");
    if(currentKind==="metadata") {
      const hit=trace.hits.find(h=>h.chunk_id===r.chunk_id), page=data.pages.find(p=>p.page===r.metadata.page);
      $("audit-evidence").innerHTML=`<h2>${esc(trace.question)}</h2><p class="muted">${r.strategy} · ${esc(r.question_id)} · Hạng ${hit.rank}</p>${meta(r.metadata)}<p class="muted">Filter yêu cầu: ${esc(JSON.stringify(r.requested_filter))} · Đã áp dụng: ${esc(JSON.stringify(r.applied_filter))}</p>${textBlock(hit.text)}<details class="details-text" open><summary>Trang nguồn ${r.metadata.page}</summary>${textBlock(page?.text)}</details>`;
    } else {
      $("audit-evidence").innerHTML=`<h2>${esc(r.question)}</h2><p class="muted">${r.strategy} · ${esc(r.question_id)}</p><p class="gold">Đáp án kỳ vọng: ${esc(trace.expected_answer)}</p>${r.gold.map(g=>`<details class="details-text"><summary>Gold · trang ${g.page}</summary>${textBlock(g.evidence_quote)}</details>`).join("")}${r.hits.map(h=>`<div class="audit-hit"><h2>Hạng ${h.rank} · Trang ${h.metadata.page}</h2>${textBlock(h.text)}</div>`).join("")}`;
    }
  }
  const options=[...$("audit-record").options], position=options.findIndex(o=>Number(o.value)===currentIndex);
  $("audit-prev").disabled=position===0; $("audit-next").disabled=position===options.length-1;
}
document.querySelectorAll(".nav").forEach(el=>el.addEventListener("click",()=>showView(el.dataset.view)));
$("go-audit").addEventListener("click",()=>showView("audit"));
$("metric-split").addEventListener("change",renderMetrics);
$("chunk-strategy").addEventListener("change",()=>{currentChunk=0;renderChunks();});
$("chunk-search").addEventListener("input",renderChunks);
$("chunk-list").addEventListener("click",event=>{const el=event.target.closest("[data-chunk]");if(el){currentChunk=Number(el.dataset.chunk);renderChunks();}});
["trace-strategy","trace-split"].forEach(id=>$(id).addEventListener("change",renderQuestions));
$("trace-question").addEventListener("change",renderTrace);
$("audit-kind").addEventListener("change",()=>{if(!canLeave()){$("audit-kind").value=currentKind;return;}dirty=false;currentKind=$("audit-kind").value;currentIndex=0;auditOptions();});
let auditStrategy="A";
$("audit-strategy").addEventListener("change",()=>{if(!canLeave()){$("audit-strategy").value=auditStrategy;return;}dirty=false;auditStrategy=$("audit-strategy").value;auditOptions();});
$("audit-record").addEventListener("change",()=>{if(!canLeave()){$("audit-record").value=currentIndex;return;}dirty=false;currentIndex=Number($("audit-record").value);renderAudit();});
$("audit-form").addEventListener("input",()=>{dirty=true;});
for (const [id,step] of [["audit-prev",-1],["audit-next",1]]) $(id).addEventListener("click",()=>{if(!canLeave())return;dirty=false;$("audit-record").selectedIndex+=step;currentIndex=Number($("audit-record").value);renderAudit();});
$("audit-form").addEventListener("submit",async event=>{
  event.preventDefault();$("save-label").disabled=true;
  try {
    const score=$("audit-score").value;
    const labels={reason:$("reason").value.trim(),reviewer:$("reviewer").value.trim()};
    if(currentKind==="metadata") {labels.complete_and_correct=score==="true";labels.obeys_requested_filter=$("filter-label").hidden?null:$("audit-filter").value==="true";}
    else labels.label_0_1_2=Number(score);
    data.audits[currentKind]=await api("/api/audit",{kind:currentKind,index:currentIndex,revision:data.audits[currentKind].revision,labels});
    dirty=false;auditOptions();progress();status("Đã lưu nhãn trên máy. Bạn có thể chuyển sang mẫu tiếp theo.");
  } catch(error){status(error.message,true);} finally{$("save-label").disabled=false;}
});
$("sync-report").addEventListener("click",async()=>{
  if(dirty){status("Hãy lưu nhãn đang sửa trước khi đồng bộ.",true);return;}
  $("sync-report").disabled=true;
  try{const result=await api("/api/sync",{});data.audit_metrics=result.metrics;status("Đã tổng hợp điểm và cập nhật báo cáo cá nhân cùng bảng kết quả.");}
  catch(error){status(error.message,true);}finally{progress();}
});
window.addEventListener("beforeunload",event=>{if(dirty){event.preventDefault();event.returnValue="";}});
(async()=>{try{data=await api("/api/data");overview();renderChunks();renderQuestions();auditOptions();status();}catch(error){status("Không tải được kết quả: "+error.message,true);}})();

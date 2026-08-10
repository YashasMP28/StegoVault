const $ = (s) => document.querySelector(s);
const CSRF = window.CSRF_TOKEN || '';
const authHeaders = {'X-CSRF-Token': CSRF};

function setStatus(el, text, ok=false) {
  el.textContent = text || "";
  el.className = "status" + (text ? (ok ? " ok" : " error") : "");
}

function setupDropzone(dropId, inputId, previewId, wrapId) {
  const drop = $(dropId), input = $(inputId), preview = $(previewId), wrap = $(wrapId);
  if (!drop) return;
  drop.addEventListener("click", e => {
    if (!e.target.closest("button")) input.click();
  });
  drop.querySelector(".browse")?.addEventListener("click", e => { e.stopPropagation(); input.click(); });
  ["dragenter","dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("drag"); }));
  ["dragleave","drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("drag"); }));
  drop.addEventListener("drop", e => {
    const file = e.dataTransfer.files[0];
    if (file) { input.files = e.dataTransfer.files; showPreview(file, preview, wrap); input.dispatchEvent(new Event("change")); }
  });
  input.addEventListener("change", () => {
    const file = input.files[0];
    if (file) showPreview(file, preview, wrap);
  });
}

function showPreview(file, img, wrap) {
  if (!file || !img) return;
  img.src = URL.createObjectURL(file);
  wrap.classList.add("show");
}

setupDropzone("#encodeDrop","#encodeImage","#encodePreview","#encodePreviewWrap");
setupDropzone("#decodeDrop","#decodeImage","#decodePreview","#decodePreviewWrap");

document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    document.querySelectorAll(".panel").forEach(p => p.classList.add("hidden"));
    $("#" + tab.dataset.tab + "-panel").classList.remove("hidden");
  });
});

const message = $("#message");
message.addEventListener("input", () => {
  $("#charCount").textContent = `${message.value.length.toLocaleString()} / 50,000`;
  updateCapacity();
});

function updateCapacity() {
  const file = $("#encodeImage").files[0];
  if (!file) { $("#capacityText").textContent = "Select an image"; $("#capacityBar").style.width="0%"; return; }
  const img = new Image();
  img.onload = () => {
    const capacity = Math.max(0, Math.floor((img.width * img.height * 3 * 2) / 8) - 43);
    const used = new TextEncoder().encode(message.value).length;
    const pct = Math.min(100, capacity ? used / capacity * 100 : 100);
    $("#capacityText").textContent = `${used.toLocaleString()} / ${capacity.toLocaleString()} bytes`;
    $("#capacityBar").style.width = pct + "%";
  };
  img.src = URL.createObjectURL(file);
}
$("#encodeImage").addEventListener("change", updateCapacity);

async function downloadResponse(response, fallbackName) {
  if (!response.ok) {
    const data = await response.json().catch(() => ({error:"Request failed."}));
    throw new Error(data.error || "Request failed.");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href=url; a.download=fallbackName; a.click();
  URL.revokeObjectURL(url);
}

$("#encodeBtn").addEventListener("click", async () => {
  const file = $("#encodeImage").files[0], text = message.value.trim();
  if (!file) return setStatus($("#encodeStatus"), "Select an image first.");
  if (!text) return setStatus($("#encodeStatus"), "Enter a secret message first.");
  const fd = new FormData(); fd.append("image", file); fd.append("message", text);
  setStatus($("#encodeStatus"), "Encoding image...");
  try {
    await downloadResponse(await fetch("/api/encode",{method:"POST",headers:authHeaders,body:fd}),"encoded-image.png");
    setStatus($("#encodeStatus"), "Done — encoded-image.png downloaded.", true);
  } catch(e) { setStatus($("#encodeStatus"), e.message); }
});

$("#decodeBtn").addEventListener("click", async () => {
  const file = $("#decodeImage").files[0];
  if (!file) return setStatus($("#decodeStatus"), "Select an encoded image first.");
  const fd = new FormData(); fd.append("image",file);
  setStatus($("#decodeStatus"), "Revealing message...");
  try {
    const res = await fetch("/api/decode",{method:"POST",headers:authHeaders,body:fd});
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not decode image.");
    $("#revealedMessage").textContent = data.message;
    setStatus($("#decodeStatus"), "Message revealed successfully.", true);
  } catch(e) { setStatus($("#decodeStatus"), e.message); }
});

$("#copyBtn").addEventListener("click", async () => {
  const text = $("#revealedMessage").textContent;
  if (!text || text === "Your hidden message will appear here.") return;
  await navigator.clipboard.writeText(text);
  $("#copyBtn").textContent = "Copied!";
  setTimeout(()=>$("#copyBtn").textContent="Copy",1200);
});

document.querySelectorAll(".utility-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    const input = document.querySelector(`.utility-file[data-action="${btn.dataset.action}"]`);
    input.click();
  });
});
document.querySelectorAll(".utility-file").forEach(input => {
  input.addEventListener("change", async () => {
    const action = input.dataset.action, files = [...input.files];
    if (!files.length) return;
    if (action === "merge" && files.length < 2) return setStatus($("#utilityStatus"), "Select two images for merging.");
    const fd = new FormData();
    if (action === "merge") { fd.append("image1",files[0]); fd.append("image2",files[1]); }
    else fd.append("image",files[0]);
    setStatus($("#utilityStatus"), "Processing...");
    try {
      await downloadResponse(await fetch(`/api/${action}`,{method:"POST",headers:authHeaders,body:fd}), action==="merge"?"merged-image.png":`${action}-image.png`);
      setStatus($("#utilityStatus"), "Done — your file was downloaded.", true);
    } catch(e) { setStatus($("#utilityStatus"), e.message); }
    input.value="";
  });
});


async function unlockGroup(){
  const groupId=$("#groupSelect")?.value;
  const username=$("#groupUsername")?.value.trim();
  const password=$("#groupPassword")?.value;
  if(!groupId||!username||!password){return setStatus($("#groupStatus"),"Select a group and enter the Group username/password.");}
  const fd=new FormData();fd.append('group_id',groupId);fd.append('username',username);fd.append('password',password);
  setStatus($("#groupStatus"),"Unlocking group...");
  try{const r=await fetch('/api/group/login',{method:'POST',headers:authHeaders,body:fd});const j=await r.json();if(!r.ok)throw new Error(j.error||'Unable to unlock group.');
    $("#activeGroupName").textContent=j.group_name;$("#tools").classList.remove('locked');setStatus($("#groupStatus"),'Group unlocked successfully.',true);loadActivity();
  }catch(e){setStatus($("#groupStatus"),e.message)}
}
$("#unlockGroup")?.addEventListener('click',unlockGroup);

async function loadActivity(){
 const box=$("#activityTable"); if(!box)return; box.textContent='Loading...';
 try{const r=await fetch('/api/group/activity');const j=await r.json();if(!r.ok)throw new Error(j.error||'Could not load activity.');
  if(!j.activity.length){box.textContent='No group activity yet.';return;}
  box.innerHTML='<table><thead><tr><th>User</th><th>Operation</th><th>Image</th><th>Secret message</th><th>Time</th></tr></thead><tbody>'+j.activity.map(a=>`<tr><td>${escapeHtml(a.user_name)}</td><td>${escapeHtml(a.operation)}</td><td>${escapeHtml(a.output_filename||a.original_filename||'—')}</td><td>${escapeHtml(a.secret_message||'')}</td><td>${escapeHtml(a.created_at)}</td></tr>`).join('')+'</tbody></table>';
 }catch(e){box.textContent=e.message}
}
function escapeHtml(v){return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}
document.querySelector('.tab[data-tab="activity"]')?.addEventListener('click',loadActivity);

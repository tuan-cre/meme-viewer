"use strict";
const $ = (id) => document.getElementById(id);
const list = $("list"), search = $("search"), img = $("img"),
  empty = $("empty"), bar = $("bar"), nameEl = $("name");
let names = [], sel = null;

async function load(q = "") {
  const r = await fetch("/api/memes?q=" + encodeURIComponent(q));
  names = await r.json();
  render();
}
function render() {
  list.innerHTML = "";
  for (const n of names) {
    const li = document.createElement("li");
    if (n === sel) li.className = "sel";
    const im = document.createElement("img");
    im.loading = "lazy";
    im.src = "/thumb/" + encodeURIComponent(n);
    im.alt = "";
    const sp = document.createElement("span");
    sp.textContent = n;
    li.append(im, sp);
    li.onclick = () => select(n);
    li.ondblclick = copy;
    list.append(li);
  }
  if (sel && !names.includes(sel)) show(null);
  else if (!sel && names.length) select(names[0]);
}
function show(n) {
  sel = n;
  document.querySelectorAll("#list li").forEach((li, i) =>
    li.classList.toggle("sel", names[i] === n));
  if (!n) {
    img.hidden = bar.hidden = true; empty.hidden = false; return;
  }
  empty.hidden = true; img.hidden = bar.hidden = false;
  img.src = "/images/" + encodeURIComponent(n);
  img.alt = n; nameEl.textContent = n;
}
const select = show;

async function copy() {
  if (!sel) return;
  const blob = await (await fetch("/images/" + encodeURIComponent(sel))).blob();
  try {
    await navigator.clipboard.write([new ClipboardItem({ [blob.type || "image/png"]: blob })]);
  } catch {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = sel; a.click();
    URL.revokeObjectURL(url);
  }
}
async function upload(files) {
  if (!files.length) return;
  const fd = new FormData();
  for (const f of files) fd.append("files", f, f.name);
  await fetch("/upload", { method: "POST", body: fd });
  load(search.value);
}
search.oninput = () => load(search.value);
$("copy").onclick = copy;
$("open").onclick = () => sel && window.open("/images/" + encodeURIComponent(sel), "_blank");
$("rename").onclick = async () => {
  if (!sel) return;
  const v = prompt("New filename:", sel);
  if (!v || v === sel) return;
  const r = await fetch("/api/rename", { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ old: sel, new: v }) });
  if (r.ok) { sel = (await r.json()).filename; load(search.value); }
  else alert("Rename failed");
};
$("trash").onclick = async () => {
  if (!sel || !confirm("Trash " + sel + "?")) return;
  await fetch("/api/trash", { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: sel }) });
  sel = null; load(search.value);
};
$("add").onclick = () => $("file").click();
$("file").onchange = (e) => { upload([...e.target.files]); e.target.value = ""; };
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => {
  e.preventDefault();
  if (e.dataTransfer.files.length) upload([...e.dataTransfer.files]);
});
document.addEventListener("keydown", (e) => {
  if (e.target === search) return;
  if (e.key === "c" && (e.ctrlKey || e.metaKey)) copy();
  else if (e.key === "Delete") $("trash").click();
  else if (e.key === "/") { e.preventDefault(); search.focus(); }
});
load();

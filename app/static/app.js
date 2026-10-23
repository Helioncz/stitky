// Tabulka přístrojů: přidání/odebrání/posun řádků a našeptávání z katalogu.

function addDeviceRow() {
  const tpl = document.getElementById("devrow");
  const body = document.querySelector("#devtable tbody");
  if (!tpl || !body) return;
  const row = tpl.content.firstElementChild.cloneNode(true);
  body.appendChild(row);
  row.querySelector("input").focus();
}

function moveRow(btn, dir) {
  const tr = btn.closest("tr");
  const sib = dir < 0 ? tr.previousElementSibling : tr.nextElementSibling;
  if (!sib) return;
  dir < 0 ? sib.before(tr) : sib.after(tr);
}

(function catalogLookup() {
  const list = document.getElementById("catlist");
  if (!list) return;
  let cache = {};
  let timer = null;

  document.addEventListener("input", (e) => {
    const inp = e.target;
    if (!inp.classList || !inp.classList.contains("typecode")) return;
    const q = inp.value.trim();
    const hit = cache[q];
    if (hit) { fillRow(inp.closest("tr"), hit); return; }
    clearTimeout(timer);
    if (q.length < 2) return;
    timer = setTimeout(async () => {
      const res = await fetch("/catalog/search?q=" + encodeURIComponent(q));
      if (!res.ok) return;
      const rows = await res.json();
      list.innerHTML = "";
      rows.forEach((r) => {
        cache[r.type_code] = r;
        const o = document.createElement("option");
        o.value = r.type_code;
        o.label = `${r.manufacturer} · ${r.rated_current_a ?? ""} A ${r.curve ?? ""}${r.verified ? " ✓" : ""}`;
        list.appendChild(o);
      });
    }, 250);
  });

  function fillRow(tr, r) {
    const set = (name, v) => {
      const el = tr.querySelector(`[name="d_${name}"]`);
      if (el && v !== null && v !== undefined && v !== "") el.value = String(v).replace(".", ",");
    };
    ["manufacturer", "kind", "poles", "rated_current_a", "curve", "breaking_capacity_ka", "residual_ma", "rcd_type"]
      .forEach((f) => set(f, r[f]));
    set("source", "catalog");
  }
})();

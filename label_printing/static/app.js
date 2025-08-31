// static/app.js
const $ = sel => document.querySelector(sel);
const $$ = sel => document.querySelectorAll(sel);

const productSearch = $("#productSearch");
const suggestions = $("#suggestions");
const previewImg = $("#labelPreview");
const printBtn = $("#printBtn");
const countInput = $("#count");
const expInput = $("#exp");
const storeNameInput = $("#storeName");
const metaDiv = $("#meta");

let selectedProduct = null;
let searchTimer = null;

// --- Typeahead search ---
productSearch.addEventListener("input", (e) => {
  const q = e.target.value.trim();
  selectedProduct = null;
  printBtn.disabled = true;
  metaDiv.textContent = "";
  previewImg.removeAttribute("src");

  if (searchTimer) clearTimeout(searchTimer);
  if (!q) { suggestions.style.display = "none"; return; }

  searchTimer = setTimeout(async () => {
    const res = await fetch(`/api/products?q=${encodeURIComponent(q)}`);
    const items = await res.json();
    suggestions.innerHTML = "";
    if (!items.length) { suggestions.style.display = "none"; return; }

    items.forEach(p => {
      const li = document.createElement("li");
      li.textContent = `${p.name} — ${p.quantity} ${p.measure} | ₹${p.retail_price}`;
      li.addEventListener("click", () => selectProduct(p));
      suggestions.appendChild(li);
    });
    suggestions.style.display = "block";
  }, 180);
});

function selectProduct(p) {
  selectedProduct = p;
  productSearch.value = p.name;
  suggestions.style.display = "none";
  printBtn.disabled = false;
  updatePreview();
}

function updatePreview() {
  if (!selectedProduct) return;
  const params = new URLSearchParams({
    barcode: selectedProduct.barcode,
    store: storeNameInput.value.trim(),
    exp: expInput.value.trim()
  });
  const src = `/preview?${params.toString()}`;
  previewImg.src = src;

  metaDiv.textContent =
    `Barcode: ${selectedProduct.barcode} | ` +
    `QTY: ${selectedProduct.quantity} ${selectedProduct.measure} | ` +
    `MRP: ₹${selectedProduct.mrp} | RP: ₹${selectedProduct.retail_price}`;
}

// Change store/exp -> refresh preview
storeNameInput.addEventListener("input", updatePreview);
expInput.addEventListener("input", updatePreview);

// --- Print ---
printBtn.addEventListener("click", async () => {
  if (!selectedProduct) return;
  const payload = {
    barcode: selectedProduct.barcode,
    count: Math.max(1, parseInt(countInput.value || "1", 10)),
    store_name: storeNameInput.value.trim(),
    exp: expInput.value.trim()
  };

  printBtn.disabled = true;
  printBtn.textContent = "Printing…";

  try {
    const res = await fetch("/api/print", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok && data.ok) {
      alert(`Printed ${data.printed} label(s).`);
    } else {
      alert(`Partial/failed print. Printed: ${data.printed}. Errors: ${data.errors?.join("; ")}`);
    }
  } catch (e) {
    alert("Print failed: " + e.message);
  } finally {
    printBtn.textContent = "Print";
    printBtn.disabled = false;
  }
});

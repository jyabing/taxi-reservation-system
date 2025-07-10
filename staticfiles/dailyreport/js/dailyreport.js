document.addEventListener('DOMContentLoaded', () => {
  // —— 1. flatpickr 时间选择器 —— 
  flatpickr(".time-input", {
    enableTime: true,
    noCalendar:  true,
    dateFormat: "H:i",
    time_24hr:  true,
    locale:     "ja"
  });

  // —— 2. 计算并更新 勤務時間、実働時間、残業時間 —— 
  function updateDuration() {
  const inEl  = document.querySelector("input[name='clock_in']");
  const outEl = document.querySelector("input[name='clock_out']");
  const workDisplay   = document.getElementById("work-duration");
  const actualDisplay = document.getElementById("actual-work-time");
  const overtimeDisplay = document.getElementById("overtime");

  const breakTimeDisplay = document.getElementById("break-time-display"); // ✅ 显示休憩+20分
  const breakTimeHidden  = document.getElementById("break-time-plus20");  // ✅ 隐藏字段提交

  if (!inEl || !outEl || !workDisplay || !actualDisplay || !overtimeDisplay) return;

  const inVal  = inEl.value;
  const outVal = outEl.value;
  if (!inVal || !outVal) {
    workDisplay.textContent   = "--:--";
    actualDisplay.textContent = "--:--";
    overtimeDisplay.textContent = "--:--";

    if (breakTimeDisplay) breakTimeDisplay.textContent = "--:--";
    if (breakTimeHidden)  breakTimeHidden.value = "";

    return;
  }

  const [h1,m1] = inVal.split(":").map(Number);
  const [h2,m2] = outVal.split(":").map(Number);
  let d1 = new Date(0,0,0,h1,m1);
  let d2 = new Date(0,0,0,h2,m2);
  if (d2 <= d1) d2.setDate(d2.getDate()+1);
  const workMin = Math.floor((d2 - d1) / 60000);

  let breakMin = 0;
  const breakEl = document.getElementById("break-time-input");
  if (breakEl && breakEl.value) {
    const [bh,bm] = breakEl.value.split(":").map(Number);
    breakMin = (bh||0)*60 + (bm||0);
  }

  const realBreak = breakMin + 20;
  const actualMin = workMin - realBreak;
  const overtimeMin = actualMin - 480;

  const toHM = m => `${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`;

  workDisplay.textContent    = toHM(workMin);
  actualDisplay.textContent  = toHM(actualMin);
  overtimeDisplay.textContent = (overtimeMin<0?"-":"") + toHM(Math.abs(overtimeMin));
  overtimeDisplay.style.color = (overtimeMin>=0 ? "red" : "blue");

  // ✅ 更新休憩 +20分展示和提交值
  if (breakTimeDisplay) breakTimeDisplay.textContent = toHM(realBreak);
  if (breakTimeHidden)  breakTimeHidden.value = toHM(realBreak);
}

  // —— 3. FormSet 行号 & 索引同步 —— 
  function updateRowNumbersAndIndexes() {
    const rows = document.querySelectorAll("tr.report-item-row");
    let index = 0;
    rows.forEach(row => {
      if (row.style.display === "none") return;

      const numCell = row.querySelector(".row-number");
      if (numCell) numCell.textContent = index + 1;

      row.querySelectorAll("input, select, textarea, label").forEach(el => {
        ["name", "id", "for"].forEach(attr => {
          if (el.hasAttribute(attr)) {
            el.setAttribute(attr, el.getAttribute(attr).replace(/-\d+-/, `-${index}-`));
          }
        });
      });

      index++;
    });

    const totalEl = document.querySelector("input[name$='-TOTAL_FORMS']");
    if (totalEl) totalEl.value = index;
  }

  // —— 4. 给某一行绑定 flatpickr、删除事件 —— 
  function bindRowEvents(row) {
    row.querySelectorAll(".time-input").forEach(el => {
      flatpickr(el, {
        enableTime: true, noCalendar:true, dateFormat:"H:i", time_24hr:true, locale:"ja"
      });
    });

    row.querySelectorAll(".delete-row").forEach(btn => {
      btn.addEventListener("click", () => {
        if (!confirm("确定删除此行？")) return;
        const cb = row.querySelector("input[name$='-DELETE']");
        if (cb) cb.checked = true;
        row.style.display = "none";
        updateRowNumbersAndIndexes();
      });
    });

    const checkbox = row.querySelector(".mark-checkbox");
    if (checkbox) {
      row.classList.toggle("has-note", checkbox.checked);
      checkbox.addEventListener("change", () => {
        row.classList.toggle("has-note", checkbox.checked);
      });
    }
  }

  // —— 5. 「增加一行」按钮 —— 
  document.getElementById("add-row-btn")?.addEventListener("click", () => {
    const totalEl = document.querySelector("input[name$='-TOTAL_FORMS']");
    const template = document.getElementById("empty-form-template");
    if (!template || !totalEl) return;

    const count = parseInt(totalEl.value, 10);
    const newHtml = template.innerHTML
      .replace(/__num__/g, count + 1)
      .replace(/__prefix__/g, count);

    const row = document.createElement("tr");
    row.classList.add("report-item-row");
    row.innerHTML = newHtml;

    const tbody = document.querySelector("table.report-table > tbody");
    tbody.appendChild(row);
    bindRowEvents(row);

    totalEl.value = count + 1;
    updateRowNumbersAndIndexes();
  });

  // —— 6. 「向下插入一行」按钮 —— 
  document.querySelector("table.report-table").addEventListener("click", (e) => {
    if (!e.target.classList.contains("insert-below")) return;

    const totalEl = document.querySelector("input[name$='-TOTAL_FORMS']");
    const template = document.querySelector("#empty-form-template");
    if (!template || !totalEl) return;

    const count = parseInt(totalEl.value, 10);
    const newHtml = template.innerHTML
      .replace(/__prefix__/g, count)
      .replace(/__num__/g, count + 1);

    const newRow = document.createElement("tr");
    newRow.classList.add("report-item-row");
    newRow.innerHTML = newHtml;

    const currentRow = e.target.closest("tr");
    currentRow.parentNode.insertBefore(newRow, currentRow.nextSibling);

    bindRowEvents(newRow);
    totalEl.value = count + 1;

    updateRowNumbersAndIndexes();
  });

  // —— 7. 初始执行一次 & 监听输入变化 ——
  updateDuration();
  ["clock_in","clock_out"].forEach(nm => {
    document.querySelector(`input[name='${nm}']`)?.addEventListener("input", updateDuration);
  });
  document.getElementById("break-time-input")?.addEventListener("input", updateDuration);
});

// 用于点击“削除”按钮即隐藏该行并标记为删除
function bindDeleteRowButtons() {
  document.querySelectorAll('.delete-row').forEach(function (btn) {
    btn.removeEventListener('click', handleDelete); // 避免重复绑定
    btn.addEventListener('click', handleDelete);
  });
}

function handleDelete(event) {
  const row = event.target.closest('tr');
  if (!row) return;

  // 标记 DELETE 字段为 true
  const deleteInput = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
  if (deleteInput) {
    deleteInput.checked = true;
  }

  // 隐藏整行
  row.style.display = 'none';

  // 重新更新编号等（可选）
  updateRowNumbersAndIndexes();
}

// 页面加载后立即绑定一次
document.addEventListener('DOMContentLoaded', function () {
  bindDeleteRowButtons();
});
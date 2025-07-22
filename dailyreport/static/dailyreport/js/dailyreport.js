document.addEventListener('DOMContentLoaded', () => {
  // —— 1. flatpickr 时间选择器 ——
  flatpickr(".time-input", {
    enableTime: true,
    noCalendar: true,
    dateFormat: "H:i",
    time_24hr: true,
    locale: "ja"
  });

  // —— 2. 勤務 / 実働 / 残業時間计算 ——
  function updateDuration() {
    const inEl = document.querySelector("input[name='clock_in']");
    const outEl = document.querySelector("input[name='clock_out']");
    const workDisplay = document.getElementById("work-duration");
    const actualDisplay = document.getElementById("actual-work-time");
    const overtimeDisplay = document.getElementById("overtime");
    const breakTimeDisplay = document.getElementById("break-time-display");
    const breakTimeHidden = document.getElementById("break-time-plus20");

    if (!inEl || !outEl) return;

    const [h1, m1] = (inEl.value || "00:00").split(":").map(Number);
    const [h2, m2] = (outEl.value || "00:00").split(":").map(Number);
    let d1 = new Date(0, 0, 0, h1, m1);
    let d2 = new Date(0, 0, 0, h2, m2);
    if (d2 <= d1) d2.setDate(d2.getDate() + 1);
    const workMin = Math.floor((d2 - d1) / 60000);

    let breakMin = 0;
    const breakEl = document.getElementById("break-time-input");
    if (breakEl && breakEl.value) {
      const [bh, bm] = breakEl.value.split(":").map(Number);
      breakMin = (bh || 0) * 60 + (bm || 0);
    }

    const realBreak = breakMin + 20;
    const actualMin = workMin - realBreak;
    const overtimeMin = actualMin - 480;

    const toHM = m => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;

    workDisplay.textContent = toHM(workMin);
    actualDisplay.textContent = toHM(actualMin);
    overtimeDisplay.textContent = (overtimeMin < 0 ? "-" : "") + toHM(Math.abs(overtimeMin));
    overtimeDisplay.style.color = overtimeMin >= 0 ? "red" : "blue";

    if (breakTimeDisplay) breakTimeDisplay.textContent = toHM(realBreak);
    if (breakTimeHidden) breakTimeHidden.value = toHM(realBreak);
  }

  // —— 3. 行号与索引同步 ——
  function updateRowNumbersAndIndexes() {
    const rows = document.querySelectorAll("tr.report-item-row");
    let index = 0;
    rows.forEach(row => {
      if (row.style.display === "none") return;
      row.querySelector(".row-number").textContent = index + 1;
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

  // —— 4. 单行事件绑定 ——
  function bindRowEvents(row) {
    row.querySelectorAll(".time-input").forEach(el => {
      flatpickr(el, { enableTime: true, noCalendar: true, dateFormat: "H:i", time_24hr: true, locale: "ja" });
    });

    row.querySelectorAll(".delete-row").forEach(btn => {
      btn.addEventListener("click", () => {
        if (confirm("确定删除此行？")) {
          const cb = row.querySelector("input[name$='-DELETE']");
          if (cb) {
            cb.checked = true;
            row.style.display = "none";
            updateRowNumbersAndIndexes();
            updateTotals();
          }
        }
      });
    });

    const checkbox = row.querySelector(".mark-checkbox");
    if (checkbox) {
      row.classList.toggle("has-note", checkbox.checked);
      checkbox.addEventListener("change", () => {
        row.classList.toggle("has-note", checkbox.checked);
      });
    }

    // 合计更新
    const amountInput = row.querySelector("input[name$='-meter_fee']");
    const methodSelect = row.querySelector("select[name$='-payment_method']");
    if (amountInput) amountInput.addEventListener("input", updateTotals);
    if (methodSelect) methodSelect.addEventListener("change", updateTotals);
  }

  // —— 5. 增加一行 ——
  document.getElementById("add-row-btn")?.addEventListener("click", () => {
    const totalEl = document.querySelector("input[name$='-TOTAL_FORMS']");
    const template = document.getElementById("empty-form-template");
    if (!template || !totalEl) return;

    const count = parseInt(totalEl.value, 10);
    const newHtml = template.innerHTML.replace(/__num__/g, count + 1).replace(/__prefix__/g, count);
    const row = document.createElement("tr");
    row.classList.add("report-item-row");
    row.innerHTML = newHtml;

    document.querySelector("table.report-table > tbody").appendChild(row);
    bindRowEvents(row);
    updateRowNumbersAndIndexes();
    updateTotals();
  });

  // —— 6. 向下插入一行 ——
  document.querySelector("table.report-table").addEventListener("click", (e) => {
    if (!e.target.classList.contains("insert-below")) return;
    const totalEl = document.querySelector("input[name$='-TOTAL_FORMS']");
    const template = document.querySelector("#empty-form-template");
    if (!template || !totalEl) return;

    const count = parseInt(totalEl.value, 10);
    const tempDiv = document.createElement("tbody");
    tempDiv.innerHTML = template.innerHTML.replace(/__prefix__/g, count).replace(/__num__/g, count + 1);
    const newRow = tempDiv.querySelector("tr");
    const currentRow = e.target.closest("tr");
    currentRow.parentNode.insertBefore(newRow, currentRow.nextSibling);
    bindRowEvents(newRow);
    updateRowNumbersAndIndexes();
    updateTotals();
  });

  // —— 7. ETC 差额、短收、高亮提示 ——
  function updateEtcDifference() {
    const cash = parseInt(document.getElementById('id_etc_collected_cash')?.value || 0);
    const uncollected = parseInt(document.getElementById('id_etc_uncollected')?.value || 0);
    const display = document.getElementById('etc-diff-display');
    const diff = cash + uncollected - cash;
    if (display) {
      display.className = diff > 0 ? 'alert alert-warning' : 'alert alert-info';
      display.innerText = `未收 ETC：${diff} 円${diff > 0 ? '（将从工资中扣除）' : '（无需扣除）'}`;
    }
  }

  function updateEtcShortage() {
    const cash = parseInt(document.getElementById('id_etc_collected_cash')?.value || 0);
    const uncollected = parseInt(document.getElementById('id_etc_uncollected')?.value || 0);
    const actualUsed = parseInt(document.getElementById('id_etc_collected')?.value || 0);
    const shortage = Math.max(0, actualUsed - (cash + uncollected));
    const input = document.getElementById('id_etc_shortage');
    if (input) {
      input.value = shortage;
      input.classList.toggle('text-danger', shortage > 0);
      input.classList.toggle('fw-bold', shortage > 0);
    }
  }

  function updateEtcInclusionWarning() {
    const deposit = parseInt(document.getElementById('id_deposit_amount')?.value || 0);
    const etcCollected = parseInt(document.getElementById('id_etc_collected')?.value || 0);
    const cash = parseInt(document.getElementById('total-cash-amount')?.innerText || 0);
    const diff = deposit - cash;
    const box = document.getElementById('etc-included-warning');
    if (!box) return;

    if (Math.abs(diff - etcCollected) <= 100) {
      box.className = 'alert alert-success';
      box.innerText = `✅ 入金額 ETC 取込む（${etcCollected}円）を含め`;
    } else if (Math.abs(diff) <= 100) {
      box.className = 'alert alert-warning';
      box.innerText = `⚠️ 入金額を含めないかも ETC，注意收款确认`;
    } else {
      box.className = 'alert alert-warning';
      box.innerText = `⚠️ 入金と現金の差額異常，確認ください`;
    }
  }

  // —— 8. 支付方式合计，包括ETC ——
  function updateTotals() {
    const totalMap = {
      cash: 0, uber: 0, didi: 0, credit: 0,
      kyokushin: 0, omron: 0, kyotoshi: 0, qr: 0,
    };

    document.querySelectorAll("tr.report-item-row").forEach(row => {
      const fee = parseInt(row.querySelector("input[name$='-meter_fee']")?.value || 0);
      const method = row.querySelector("select[name$='-payment_method']")?.value || "";
      if (fee > 0 && totalMap.hasOwnProperty(method)) {
        totalMap[method] += fee;
      }
    });

    const etcAmount = parseInt(document.getElementById("id_etc_collected")?.value || 0);
    const etcMethod = document.getElementById("id_etc_payment_method")?.value;
    if (etcAmount > 0 && totalMap.hasOwnProperty(etcMethod)) {
      totalMap[etcMethod] += etcAmount;
    }

    Object.entries(totalMap).forEach(([method, amount]) => {
      const el = document.getElementById(`total_${method}`);
      if (el) el.textContent = amount.toLocaleString();
    });

    const meterEl = document.getElementById("total_meter");
    if (meterEl) meterEl.textContent = Object.values(totalMap).reduce((a, b) => a + b, 0).toLocaleString();
  }

  // —— 9. 绑定监听 ——
  [
    ['id_etc_collected_cash', [updateEtcDifference, updateEtcShortage]],
    ['id_etc_uncollected', [updateEtcDifference, updateEtcShortage]],
    ['id_etc_collected', [updateEtcInclusionWarning, updateEtcShortage, updateTotals]],
    ['id_deposit_amount', [updateEtcDifference, updateEtcInclusionWarning]],
    ['clock_in', [updateDuration]],
    ['clock_out', [updateDuration]],
    ['break-time-input', [updateDuration]],
    ['id_etc_payment_method', [updateTotals]],
  ].forEach(([id, fns]) => {
    const el = document.getElementById(id);
    if (el) fns.forEach(fn => el.addEventListener("input", fn));
  });

  // —— 10. 初始加载执行 ——
  updateDuration();
  updateEtcDifference();
  updateEtcShortage();
  updateEtcInclusionWarning();
  updateRowNumbersAndIndexes();
  updateTotals();
});


// ✅ Flatpickr 时间控件初始化（24小时制，日语）
flatpickr(".time-input", {
  enableTime: true,
  noCalendar: true,
  dateFormat: "H:i",
  time_24hr: true,
  locale: "ja"
});

// ✅ 重新编号所有明细行的序号（第1列）
function renumberRows() {
  const rows = document.querySelectorAll('tr.report-item-row');
  rows.forEach((row, index) => {
    const cell = row.querySelector('.row-number');
    if (cell) {
      cell.textContent = index + 1;
    }
  });
}

// ✅ 更新工作时间显示（勤務時間、実働、残業、休憩）
function updateDuration() {
  const inVal = document.querySelector("input[name='clock_in']")?.value;
  const outVal = document.querySelector("input[name='clock_out']")?.value;
  const breakInput = document.querySelector("input[name='break_time_input']");
  const workDisplay = document.getElementById("work-duration");
  const actualDisplay = document.getElementById("actual-work-time");
  const overtimeDisplay = document.getElementById("overtime");

  if (!inVal || !outVal) {
    workDisplay.textContent = actualDisplay.textContent = overtimeDisplay.textContent = '--:--';
    return;
  }

  const [h1, m1] = inVal.split(":").map(Number);
  const [h2, m2] = outVal.split(":").map(Number);
  let d1 = new Date(2000, 0, 1, h1, m1);
  let d2 = new Date(2000, 0, 1, h2, m2);
  if (d2 <= d1) d2.setDate(d2.getDate() + 1);
  const workMin = Math.floor((d2 - d1) / 60000);
  workDisplay.textContent = `${String(Math.floor(workMin / 60)).padStart(2, '0')}:${String(workMin % 60).padStart(2, '0')}`;

  let breakMin = 0;
  if (breakInput && breakInput.value) {
    const [bh, bm] = breakInput.value.split(":").map(Number);
    breakMin = (bh || 0) * 60 + (bm || 0);
  }
  const realBreak = breakMin + 20;
  const actualMin = workMin - realBreak;
  actualDisplay.textContent = `${String(Math.floor(actualMin / 60)).padStart(2, '0')}:${String(actualMin % 60).padStart(2, '0')}`;

  const overtimeMin = actualMin - 480;
  const overH = String(Math.floor(Math.abs(overtimeMin) / 60)).padStart(2, '0');
  const overM = String(Math.abs(overtimeMin % 60)).padStart(2, '0');
  overtimeDisplay.textContent = `${(overtimeMin < 0 ? '-' : '')}${overH}:${overM}`;
  overtimeDisplay.style.color = (overtimeMin >= 0) ? 'red' : 'blue';
}

// ✅ 合计金额更新逻辑
function updateTotals() {
  const PAYMENT_METHODS = {
    meter: 'メーター(水揚)', cash: '現金(ながし)', uber: 'Uber', didi: 'Didi',
    credit: 'クレジ', kyokushin: '京交信', omron: 'オムロン',
    kyotoshi: '京都市他', qr: '扫码'
  };
  const METHOD_ALIAS = {
    '現金': 'cash', 'Uber': 'uber', 'Didi': 'didi', 'クレジットカード': 'credit',
    '京交信': 'kyokushin', 'オムロン': 'omron', '京都市他': 'kyotoshi',
    '扫码（PayPay等）': 'qr', 'barcode': 'qr', 'wechat': 'qr', 'qr': 'qr'
  };
  const sum = {}, count = {};
  Object.keys(PAYMENT_METHODS).forEach(k => { sum[k] = 0; count[k] = 0; });

  document.querySelectorAll('tr.report-item-row').forEach(row => {
    const feeInput = row.querySelector('.meter-fee-input');
    const methodSelect = row.querySelector('select[name$="-payment_method"]');
    if (!feeInput || !methodSelect) return;
    const fee = parseFloat(feeInput.value.replace(/[^\d.]/g, '')) || 0;
    const label = methodSelect.options[methodSelect.selectedIndex]?.text.trim();
    const method = METHOD_ALIAS[label] || Object.keys(PAYMENT_METHODS).find(k => PAYMENT_METHODS[k] === label);
    if (method && sum.hasOwnProperty(method)) {
      sum[method] += fee;
      count[method] += 1;
    }
  });

  Object.keys(PAYMENT_METHODS).forEach(key => {
    const total = document.getElementById(`total_${key}`);
    const bonus = document.getElementById(`bonus_${key}`);
    if (total) total.textContent = sum[key].toLocaleString();
    if (bonus) bonus.textContent = Math.floor(sum[key] * 0.05).toLocaleString();
  });
}

// ✅ 新增/克隆行时重新绑定行为（Flatpickr、标记复选框、删除按钮）
function bindRowEvents(row) {
  row.querySelectorAll('.time-input').forEach(input => flatpickr(input, {
    enableTime: true, noCalendar: true, dateFormat: "H:i", time_24hr: true, locale: "ja"
  }));
  const checkbox = row.querySelector('.mark-checkbox');
  if (checkbox) {
    row.classList.toggle('has-note', checkbox.checked);
    checkbox.addEventListener('change', () => row.classList.toggle('has-note', checkbox.checked));
  }
  const delBtn = row.querySelector('.confirm-delete, .remove-row');
  if (delBtn) {
    delBtn.addEventListener('click', () => {
      if (confirm('确定删除此行？')) {
        const checkbox = row.querySelector('input[name$="-DELETE"]');
        if (checkbox) checkbox.checked = true;
        row.style.display = 'none';
        updateTotals(); renumberRows();
      }
    });
  }
}

// ✅ 自动去小数点（blur时）
function removeDecimalOnBlur() {
  document.querySelectorAll('input[name$="-meter_fee"]').forEach(input => {
    input.addEventListener('blur', () => {
      const val = parseFloat(input.value);
      if (!isNaN(val)) input.value = Math.round(val);
    });
  });
}

// ✅ 强制只允许输入整数（限制最大值）
function enforceIntegerInput() {
  document.querySelectorAll('input[name$="-meter_fee"]').forEach(input => {
    input.addEventListener('input', () => {
      input.value = input.value.replace(/[^\d]/g, '');
      const max = 99999;
      const val = parseInt(input.value || '0');
      if (val > max) {
        alert("金额不能超过 99999！");
        input.value = max;
      }
    });
  });
}

// ✅ 插入新行时克隆逻辑（按按钮插入）
function insertBelow(btn) {
  const tbody = document.querySelector('table tbody');
  const totalFormsInput = document.querySelector('input[name$="-TOTAL_FORMS"]');
  const currentCount = parseInt(totalFormsInput.value);
  const currentRow = btn.closest('tr');
  const newRow = currentRow.cloneNode(true);
  newRow.querySelectorAll('input, select, textarea').forEach(el => {
    if (el.name) el.name = el.name.replace(/-(\d+)-/, `-${currentCount}-`);
    if (el.id) el.id = el.id.replace(/-(\d+)-/, `-${currentCount}-`);
    if (el.type === 'checkbox' || el.type === 'radio') {
      el.checked = false;
    } else {
      el.value = '';
    }
  });
  const idHidden = newRow.querySelector('input[name$="-id"]');
  if (idHidden) idHidden.value = '';
  const delBox = newRow.querySelector('input[name$="-DELETE"]');
  if (delBox) delBox.checked = false;
  currentRow.after(newRow);
  totalFormsInput.value = currentCount + 1;
  bindRowEvents(newRow);
  renumberRows();
}

// ✅ 页面初始绑定
window.addEventListener('DOMContentLoaded', () => {
  updateDuration();
  updateTotals();
  renumberRows();
  removeDecimalOnBlur();
  enforceIntegerInput();

  document.querySelector("input[name='clock_in']")?.addEventListener('input', updateDuration);
  document.querySelector("input[name='clock_out']")?.addEventListener('input', updateDuration);
  document.querySelector("input[name='break_time_input']")?.addEventListener('input', updateDuration);
  document.querySelector("input[name='break_time_input']")?.addEventListener('blur', updateDuration);

  document.querySelectorAll('input[name$="-meter_fee"]').forEach(input => {
    input.addEventListener('input', updateTotals);
    input.addEventListener('change', updateTotals);
    input.addEventListener('blur', updateTotals);
  });

  document.querySelectorAll('tr.report-item-row').forEach(bindRowEvents);
  document.querySelectorAll('.insert-below').forEach(btn => {
    btn.addEventListener('click', () => insertBelow(btn));
  });

  const addBtn = document.getElementById('add-form-row');
  if (addBtn) {
    addBtn.addEventListener('click', () => {
      const tbody = document.querySelector('table tbody');
      const totalFormsInput = document.querySelector('input[name$="-TOTAL_FORMS"]');
      const currentCount = parseInt(totalFormsInput.value);
      const lastRow = tbody.querySelector('tr.report-item-row:last-child');
      const newRow = lastRow.cloneNode(true);

      newRow.querySelectorAll('input, select, textarea').forEach(el => {
        if (el.name) el.name = el.name.replace(/-(\d+)-/, `-${currentCount}-`);
        if (el.id) el.id = el.id.replace(/-(\d+)-/, `-${currentCount}-`);
        if (el.type === 'checkbox' || el.type === 'radio') {
          el.checked = false;
        } else {
          el.value = '';
        }
      });
      const idHidden = newRow.querySelector('input[name$="-id"]');
      if (idHidden) idHidden.value = '';
      const delBox = newRow.querySelector('input[name$="-DELETE"]');
      if (delBox) delBox.checked = false;

      tbody.appendChild(newRow);
      totalFormsInput.value = currentCount + 1;
      bindRowEvents(newRow);
      renumberRows();
    });
  }
});

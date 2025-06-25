
// ✅ flatpickr 时间控件绑定（初始化）
flatpickr(".time-input", {
  enableTime: true,
  noCalendar: true,
  dateFormat: "H:i",
  time_24hr: true,
  locale: "ja"
});

let updateTimeout;
function debounceUpdateTotals() {
  clearTimeout(updateTimeout);
  updateTimeout = setTimeout(updateTotals, 300);
}

function updateDuration() {
  const inVal = document.querySelector("input[name='clock_in']")?.value;
  const outVal = document.querySelector("input[name='clock_out']")?.value;
  const breakInput = document.querySelector("input[name='break_time_input']");

  const workDisplay = document.getElementById("work-duration");
  const breakDisplay = document.getElementById("break-time");
  const actualDisplay = document.getElementById("actual-work-time");
  const overtimeDisplay = document.getElementById("overtime");

  if (!inVal || !outVal) {
    workDisplay.textContent = '--:--';
    breakDisplay.textContent = '--:--';
    actualDisplay.textContent = '--:--';
    overtimeDisplay.textContent = '--:--';
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
    if ((bh || 0) > 12) {
      alert("休憩時間不能超过12小时！");
      return;
    }
    breakMin = (bh || 0) * 60 + (bm || 0);
  }

  const realBreak = breakMin + 20;
  breakDisplay.textContent = `${String(Math.floor(realBreak / 60)).padStart(2, '0')}:${String(realBreak % 60).padStart(2, '0')}`;

  const actualMin = workMin - realBreak;
  actualDisplay.textContent = `${String(Math.floor(actualMin / 60)).padStart(2, '0')}:${String(actualMin % 60).padStart(2, '0')}`;

  const overtimeMin = actualMin - 480;
  const overH = String(Math.floor(Math.abs(overtimeMin) / 60)).padStart(2, '0');
  const overM = String(Math.abs(overtimeMin % 60)).padStart(2, '0');
  overtimeDisplay.textContent = `${(overtimeMin < 0 ? '-' : '')}${overH}:${overM}`;
  overtimeDisplay.style.color = (overtimeMin >= 0) ? 'red' : 'blue';
}

function updateTotals() {
  const PAYMENT_METHODS = {
    meter: 'メーター(水揚)',
    cash: '現金(ながし)',
    uber: 'Uber',
    didi: 'Didi',
    credit: 'クレジ',
    kyokushin: '京交信',
    omron: 'オムロン',
    kyotoshi: '京都市他',
    qr: '扫码'
  };

  const METHOD_ALIAS = {
    '現金': 'cash',
    'Uber': 'uber',
    'Didi': 'didi',
    'クレジットカード': 'credit',
    '京交信': 'kyokushin',
    'オムロン': 'omron',
    '京都市他': 'kyotoshi',
    '扫码（PayPay等）': 'qr',
    'barcode': 'qr',
    'wechat': 'qr',
    'qr': 'qr'
  };

  const sum = {}, count = {};
  Object.keys(PAYMENT_METHODS).forEach(k => {
    sum[k] = 0;
    count[k] = 0;
  });

  document.querySelectorAll('tr.report-item-row').forEach(row => {
    const feeInput = row.querySelector('.meter-fee-input');
    const methodSelect = row.querySelector('select[name$="-payment_method"]');
    if (!feeInput || !methodSelect) return;

    const fee = parseFloat(feeInput.value.replace(/[^\d.]/g, '')) || 0;
    const label = methodSelect.options[methodSelect.selectedIndex]?.text.trim();
    const method = METHOD_ALIAS[label] || Object.keys(PAYMENT_METHODS).find(k => PAYMENT_METHODS[k] === label);

    // ✅ 统计所有金额为 sum.meter（总额），再根据支付方式分类
    sum.meter += fee;
    if (method && sum.hasOwnProperty(method)) {
      sum[method] += fee;
      count[method] += 1;
    }
  });

  Object.keys(PAYMENT_METHODS).forEach(key => {
    const total = document.getElementById(`total_${key}`);
    const bonus = document.getElementById(`bonus_${key}`);
    if (total) total.textContent = sum[key];
    if (bonus) bonus.textContent = Math.floor(sum[key] * 0.05);  // 例如 5% 提成
  });
}


function bindRowEvents(row) {
  row.querySelectorAll('.time-input').forEach(input => flatpickr(input, {
    enableTime: true,
    noCalendar: true,
    dateFormat: "H:i",
    time_24hr: true,
    locale: "ja"
  }));

  const checkbox = row.querySelector('.mark-checkbox');
  if (checkbox) {
    if (checkbox.checked) row.classList.add('has-note');
    checkbox.addEventListener('change', () => {
      row.classList.toggle('has-note', checkbox.checked);
    });
  }

  // 删除按钮逻辑
  const delBtn = row.querySelector('.confirm-delete, .remove-row');
  if (delBtn) {
    delBtn.addEventListener('click', () => {
      if (confirm('确定删除此行？')) {
        const checkbox = row.querySelector('input[name$="-DELETE"]');
        if (checkbox) {
          checkbox.checked = true;  // ✅ 设置 JS 层
          checkbox.setAttribute('checked', 'checked');  // ✅ 设置 HTML 层（非必须，但安全）
        }
        row.style.display = 'none';  // ✅ 隐藏这行，不删除 DOM 结构
      }
    });
  }
}

function removeDecimalOnBlur() {
  document.querySelectorAll('input[name$="-meter_fee"]').forEach(input => {
    input.addEventListener('blur', () => {
      const val = parseFloat(input.value);
      if (!isNaN(val)) {
        input.value = Math.round(val);
      }
    });
  });
}

function enforceIntegerInput() {
  document.querySelectorAll('input[name$="-meter_fee"]').forEach(input => {
    input.addEventListener('input', () => {
      // 清除非数字
      input.value = input.value.replace(/[^\d]/g, '');

      // 限制最大值（可改为你需要的数字）
      const max = 99999;
      const val = parseInt(input.value || '0');
      if (val > max) {
        alert("金額不能超過 99999！");
        input.value = max;
      }
    });
  });
}

window.addEventListener('DOMContentLoaded', () => {
  removeDecimalOnBlur();     // ✅ 失焦后去掉小数
  enforceIntegerInput();     // ✅ 输入时强制为整数
});

function checkFormStructure() {
  const rows = document.querySelectorAll('tr.report-item-row');
  const errors = [];
  const seenIndexes = new Set();

  rows.forEach((row, index) => {
    const rideTime = row.querySelector(`input[name$="-ride_time"]`);
    const rideFrom = row.querySelector(`input[name$="-ride_from"]`);
    const fee = row.querySelector(`input[name$="-meter_fee"]`);
    const method = row.querySelector(`select[name$="-payment_method"]`);
    const deleteBox = row.querySelector(`input[name$="-DELETE"]`);

    const nameMatch = (rideTime?.name || '').match(/-(\d+)-ride_time/);
    const currentIndex = nameMatch ? parseInt(nameMatch[1]) : null;

    if (currentIndex === null || seenIndexes.has(currentIndex)) {
      errors.push(`❌ 第 ${index + 1} 行 index 错误或重复`);
    } else {
      seenIndexes.add(currentIndex);
    }

    if (!rideTime) errors.push(`❌ 第 ${index + 1} 行缺少 ride_time`);
    if (!rideFrom) errors.push(`❌ 第 ${index + 1} 行缺少 ride_from`);
    if (!fee) errors.push(`❌ 第 ${index + 1} 行缺少 meter_fee`);
    if (!method) errors.push(`❌ 第 ${index + 1} 行缺少 payment_method`);
    if (!deleteBox) errors.push(`❌ 第 ${index + 1} 行缺少 DELETE 隐藏框`);
  });

  if (errors.length > 0) {
    alert("🧪 表单结构异常：\n\n" + errors.join("\n"));
    console.warn("🧪 表单结构异常：", errors);
  } else {
    alert("✅ 表单结构无异常！");
    console.info("✅ 表单结构检查通过");
  }
}

window.addEventListener('DOMContentLoaded', () => {
  updateDuration();
  updateTotals();

  document.querySelector("input[name='clock_in']")?.addEventListener('input', updateDuration);
  document.querySelector("input[name='clock_out']")?.addEventListener('input', updateDuration);

  const breakInput = document.querySelector("input[name='break_time_input']");
  if (breakInput) {
    breakInput.addEventListener('input', updateDuration);
    breakInput.addEventListener('blur', updateDuration);
  }

  document.querySelectorAll('input[name$="-meter_fee"]').forEach(input => {
    input.addEventListener('input', debounceUpdateTotals);
    input.addEventListener('change', updateTotals);
    input.addEventListener('blur', updateTotals);
  });

  document.querySelectorAll('tr.report-item-row').forEach(bindRowEvents);

  document.getElementById('add-row-btn')?.addEventListener('click', () => {
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
  });

  document.querySelectorAll('.insert-below').forEach(btn => {
    btn.addEventListener('click', () => {
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
    });
  });

  const checkBtn = document.getElementById('check-structure-btn');
  if (checkBtn) {
    checkBtn.addEventListener('click', checkFormStructure);
  }
});

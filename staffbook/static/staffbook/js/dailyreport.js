document.addEventListener('DOMContentLoaded', () => {
  // ✅ flatpickr 初始化
  flatpickr(".time-input", {
    enableTime: true,
    noCalendar: true,
    dateFormat: "H:i",
    time_24hr: true,
    locale: "ja"
  });

  // ✅ 时长与休憩计算
  function updateDuration() {
    const inVal = document.querySelector("input[name='clock_in']")?.value;
    const outVal = document.querySelector("input[name='clock_out']")?.value;
    const breakInput = document.querySelector("input[name='break_time_input']");

    const workDisplay = document.getElementById("work-duration");
    const breakDisplay = document.getElementById("break-time");
    const actualDisplay = document.getElementById("actual-work-time");
    const overtimeDisplay = document.getElementById("overtime");

    if (!inVal || !outVal) {
      workDisplay.textContent = breakDisplay.textContent = actualDisplay.textContent = overtimeDisplay.textContent = '--:--';
      return;
    }

    const [h1, m1] = inVal.split(":").map(Number);
    const [h2, m2] = outVal.split(":").map(Number);
    let d1 = new Date(2000, 0, 1, h1, m1);
    let d2 = new Date(2000, 0, 1, h2, m2);
    if (d2 <= d1) d2.setDate(d2.getDate() + 1);
    const workMin = Math.floor((d2 - d1) / 60000);

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
    const actualMin = workMin - realBreak;
    const overtimeMin = actualMin - 480;

    function toHM(min) {
      return `${String(Math.floor(min / 60)).padStart(2, '0')}:${String(min % 60).padStart(2, '0')}`;
    }

    workDisplay.textContent = toHM(workMin);
    breakDisplay.textContent = toHM(realBreak);
    actualDisplay.textContent = toHM(actualMin);

    const overH = toHM(Math.abs(overtimeMin));
    overtimeDisplay.textContent = (overtimeMin < 0 ? '-' : '') + overH;
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
      if (bonus) bonus.textContent = Math.floor(sum[key] * 0.05);
    });
  }

  function bindRowEvents(row) {
    row.querySelectorAll('.time-input').forEach(input => flatpickr(input, {
      enableTime: true, noCalendar: true, dateFormat: "H:i", time_24hr: true, locale: "ja"
    }));

    const checkbox = row.querySelector('.mark-checkbox');
    if (checkbox) {
      if (checkbox.checked) row.classList.add('has-note');
      checkbox.addEventListener('change', () => {
        row.classList.toggle('has-note', checkbox.checked);
      });
    }

    const delBtn = row.querySelector('.confirm-delete, .remove-row');
    if (delBtn) {
      delBtn.addEventListener('click', () => {
        if (confirm('确定删除此行？')) {
          const checkbox = row.querySelector('input[name$="-DELETE"]');
          if (checkbox) checkbox.checked = true;
          row.style.display = 'none';
          updateRowNumbersAndIndexes();  // ✅ 删除后更新序号
        }
      });
    }
  }

  // ✅ 工具函数
  function enforceIntegerInput() {
    document.querySelectorAll('input[name$="-meter_fee"]').forEach(input => {
      input.addEventListener('input', () => {
        input.value = input.value.replace(/[^\d]/g, '');
        const max = 99999;
        const val = parseInt(input.value || '0');
        if (val > max) {
          alert("金額不能超過 99999！");
          input.value = max;
        }
      });
    });
  }

  function removeDecimalOnBlur() {
    document.querySelectorAll('input[name$="-meter_fee"]').forEach(input => {
      input.addEventListener('blur', () => {
        const val = parseFloat(input.value);
        if (!isNaN(val)) input.value = Math.round(val);
      });
    });
  }

  // ✅ 新增一行
  document.getElementById('add-row-btn')?.addEventListener('click', () => {
    const template = document.querySelector('#empty-form-template');
    const totalFormsInput = document.querySelector('input[name$="-TOTAL_FORMS"]');
    const tbody = document.querySelector('.report-table tbody');
    const currentCount = parseInt(totalFormsInput.value);

    const newHtml = template.innerHTML.replace(/__prefix__/g, currentCount).replace(/__num__/g, currentCount + 1);
    const tempRow = document.createElement('tr');
    tempRow.innerHTML = newHtml;
    tempRow.classList.add('report-item-row');

    tbody.appendChild(tempRow);
    bindRowEvents(tempRow);
    totalFormsInput.value = currentCount + 1;

    updateRowNumbersAndIndexes();
  });

  // ✅ 向下插入一行
  document.addEventListener('click', function (e) {
    if (e.target.classList.contains('insert-below')) {
      const template = document.querySelector('#empty-form-template');
      const totalFormsInput = document.querySelector('input[name$="-TOTAL_FORMS"]');
      const currentCount = parseInt(totalFormsInput.value);
      const currentRow = e.target.closest('tr');

      const newHtml = template.innerHTML.replace(/__prefix__/g, currentCount).replace(/__num__/g, currentCount + 1);
      const tempRow = document.createElement('tr');
      tempRow.innerHTML = newHtml;
      tempRow.classList.add('report-item-row');

      currentRow.after(tempRow);
      bindRowEvents(tempRow);
      totalFormsInput.value = currentCount + 1;

      updateRowNumbersAndIndexes();
    }
  });

  // ✅ 初始化监听
  updateDuration();
  updateTotals();
  removeDecimalOnBlur();
  enforceIntegerInput();

  document.querySelector("input[name='clock_in']")?.addEventListener('input', updateDuration);
  document.querySelector("input[name='clock_out']")?.addEventListener('input', updateDuration);
  const breakInput = document.querySelector("input[name='break_time_input']");
  breakInput?.addEventListener('input', updateDuration);
  breakInput?.addEventListener('blur', updateDuration);

  document.querySelectorAll('input[name$="-meter_fee"]').forEach(input => {
    input.addEventListener('input', updateTotals);
    input.addEventListener('change', updateTotals);
    input.addEventListener('blur', updateTotals);
  });

  document.querySelectorAll('tr.report-item-row').forEach(bindRowEvents);
});


function updateRowNumbersAndIndexes() {
  const rows = document.querySelectorAll('tr.report-item-row:not([style*="display: none"])');
  let visibleIndex = 0;

  rows.forEach((row, i) => {
    if (row.style.display === 'none') return;

    // 更新左侧序号显示
    const numCell = row.querySelector('.row-number');
    if (numCell) numCell.textContent = visibleIndex + 1;

    // 替换字段名中的索引
    row.querySelectorAll('input, select, textarea, label').forEach(el => {
      ['name', 'id', 'for'].forEach(attr => {
        if (el.hasAttribute(attr)) {
          el.setAttribute(attr, el.getAttribute(attr).replace(/-\d+-/, `-${visibleIndex}-`));
        }
      });
    });

    visibleIndex++;
  });

  const totalFormsInput = document.querySelector('input[name$="-TOTAL_FORMS"]');
  if (totalFormsInput) totalFormsInput.value = visibleIndex;
}
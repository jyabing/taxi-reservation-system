// staffbook/static/staffbook/js/dailyreport.js
document.addEventListener('DOMContentLoaded', () => {
  // —— 1. flatpickr 时间选择器 初始化 —— 
  flatpickr('.time-input', {
    enableTime: true,
    noCalendar: true,
    dateFormat: 'H:i',
    time_24hr: true,
    locale: 'ja'
  });

  // —— 2. 计算并更新 工作时长/休憩/实动/残业 —— 
  function updateDuration() {
    const inEl  = document.querySelector("input[name='clock_in']");
    const outEl = document.querySelector("input[name='clock_out']");
    const breakEl = document.getElementById('break-time-input');
    const workDisp   = document.getElementById('work-duration');
    const actualDisp = document.getElementById('actual-work-time');
    const overDisp   = document.getElementById('overtime');

    if (!inEl || !outEl || !workDisp || !actualDisp || !overDisp) return;
    const inVal  = inEl.value, outVal = outEl.value;
    if (!inVal || !outVal) {
      workDisp.textContent = actualDisp.textContent = overDisp.textContent = '--:--';
      return;
    }

    // 计算分钟差
    const [h1,m1] = inVal.split(':').map(Number);
    const [h2,m2] = outVal.split(':').map(Number);
    let d1 = new Date(2000,0,1,h1,m1),
        d2 = new Date(2000,0,1,h2,m2);
    if (d2 <= d1) d2.setDate(d2.getDate()+1);
    const workMin = Math.floor((d2 - d1)/60000);

    // 休憩（前端输入 + 20 分）
    let breakMin = 0;
    if (breakEl && breakEl.value) {
      const [bh,bm] = breakEl.value.split(':').map(Number);
      breakMin = (bh||0)*60 + (bm||0);
    }
    const realBreak = breakMin + 20;
    const actualMin = workMin - realBreak;
    const overtimeMin = actualMin - 480;

    const toHM = m => `${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`;
    workDisp.textContent   = toHM(workMin);
    actualDisp.textContent = toHM(actualMin);
    overDisp.textContent   = (overtimeMin<0?'-':'') + toHM(Math.abs(overtimeMin));
    overDisp.style.color   = (overtimeMin>=0?'red':'blue');
  }

  // —— 3. 统计各支付方式合计 —— 
  function updateTotals() {
    const sum = {};
    document.querySelectorAll('tr.report-item-row').forEach(row => {
      const fee = parseFloat((row.querySelector('.meter-fee-input')?.value||'').replace(/[^\d.]/g,''))||0;
      const sel = row.querySelector('select[name$="-payment_method"]');
      const key = sel?.value;
      sum[key] = (sum[key]||0) + fee;
    });
    // meter：总里程；cash/uber/didi/... 即对应字段
    Object.keys(sum).forEach(k => {
      const tot = document.getElementById(`total_${k}`);
      const bon = document.getElementById(`bonus_${k}`);
      if (tot) tot.textContent = sum[k].toLocaleString();
      if (bon) bon.textContent = Math.floor(sum[k]*0.05).toLocaleString();
    });
  }

  // —— 4. 更新行号 & name/id 索引 —— 
  function updateRowNumbersAndIndexes() {
    const rows = Array.from(document.querySelectorAll('tr.report-item-row'))
                      .filter(r => r.style.display!=='none');
    rows.forEach((row,i) => {
      row.querySelector('.row-number')?.textContent = String(i+1);
      row.querySelectorAll('input,select,textarea,label').forEach(el => {
        ['name','id','for'].forEach(attr => {
          if (!el.hasAttribute(attr)) return;
          el.setAttribute(attr,
            el.getAttribute(attr).replace(/-\d+-/, `-${i}-`)
          );
        });
      });
    });
    const totalEl = document.querySelector("input[name$='-TOTAL_FORMS']");
    if (totalEl) totalEl.value = String(rows.length);
  }

  // —— 5. 给单行绑定 flatpickr + 删除事件 —— 
  function bindRowEvents(row) {
    row.querySelectorAll('.time-input').forEach(el => {
      flatpickr(el, { enableTime:true,noCalendar:true,dateFormat:'H:i',time_24hr:true,locale:'ja'});
    });
    // 删除行按钮
    row.querySelectorAll('.delete-row').forEach(btn => {
      btn.addEventListener('click', () => {
        if (!confirm('确定删除此行？')) return;
        const cb = row.querySelector("input[name$='-DELETE']");
        if (cb) cb.checked = true;
        row.style.display = 'none';
        updateRowNumbersAndIndexes();
        updateTotals();
      });
    });
  }

  // —— 6. 绑定已有行 —— 
  document.querySelectorAll('tr.report-item-row').forEach(bindRowEvents);
  updateRowNumbersAndIndexes();
  updateTotals();
  updateDuration();

  // —— 7. 「增加一行」按钮 —— 
  document.getElementById('add-row-btn')?.addEventListener('click', () => {
    const template = document.getElementById('empty-form-template').innerHTML;
    const totalEl  = document.querySelector("input[name$='-TOTAL_FORMS']");
    const cnt      = parseInt(totalEl.value, 10);

    const html = template
      .replace(/__prefix__/g, cnt)
      .replace(/__num__/g, cnt+1);

    const tr = document.createElement('tr');
    tr.classList.add('report-item-row');
    tr.innerHTML = html;
    document.querySelector('table.report-table tbody').appendChild(tr);

    bindRowEvents(tr);
    totalEl.value = String(cnt+1);
    updateRowNumbersAndIndexes();
    updateTotals();
  });

  // —— 8. 「向下插入行」按钮 —— 
  document.querySelector('table.report-table')?.addEventListener('click', e => {
    if (!e.target.classList.contains('insert-below')) return;
    const template = document.getElementById('empty-form-template').innerHTML;
    const totalEl  = document.querySelector("input[name$='-TOTAL_FORMS']");
    const cnt      = parseInt(totalEl.value, 10);

    const html = template
      .replace(/__prefix__/g, cnt)
      .replace(/__num__/g, cnt+1);

    const trNew = document.createElement('tr');
    trNew.classList.add('report-item-row');
    trNew.innerHTML = html;

    e.target.closest('tr').after(trNew);
    bindRowEvents(trNew);
    totalEl.value = String(cnt+1);
    updateRowNumbersAndIndexes();
    updateTotals();
  });

  // —— 9. 绑定工作时长监听 —— 
  ['clock_in','clock_out'].forEach(nm => {
    document.querySelector(`input[name='${nm}']`)?.addEventListener('input', updateDuration);
  });
  document.getElementById('break-time-input')?.addEventListener('input', updateDuration);
});

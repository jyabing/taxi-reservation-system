<script>
(function () {
  function toLocalInputValue(d){
    const tz = d.getTimezoneOffset()*60000;
    const local = new Date(d.getTime() - tz);
    return local.toISOString().slice(0,16); // YYYY-MM-DDTHH:MM
  }

  // 出库
  const depModal = document.getElementById('departureModal');
  const depForm  = document.getElementById('departureForm');
  const depBaseAction = depForm ? depForm.getAttribute('action') : '';
  if (depModal && depForm) {
    depModal.addEventListener('show.bs.modal', function (ev) {
      const btn = ev.relatedTarget;   // 触发按钮
      const id  = btn && (btn.dataset.reservationId || btn.getAttribute('data-id'));
      const inputId  = document.getElementById('reservationIdInput');
      const inputTime= document.getElementById('actualDepartureInput');
      inputId.value   = id || '';
      inputTime.value = toLocalInputValue(new Date());
      if (id) depForm.setAttribute('action', depBaseAction + '?rid=' + encodeURIComponent(id));
    });
  }

  // 入库
  const retModal = document.getElementById('returnModal');
  const retForm  = document.getElementById('returnForm');
  const retBaseAction = retForm ? retForm.getAttribute('action') : '';
  if (retModal && retForm) {
    retModal.addEventListener('show.bs.modal', function (ev) {
      const btn = ev.relatedTarget;
      const id  = btn && (btn.dataset.reservationId || btn.getAttribute('data-id'));
      const inputId  = document.getElementById('returnReservationIdInput');
      const inputTime= document.getElementById('actualReturnInput');
      inputId.value   = id || '';
      inputTime.value = toLocalInputValue(new Date());
      if (id) retForm.setAttribute('action', retBaseAction + '?rid=' + encodeURIComponent(id));
    });
  }
})();
</script>

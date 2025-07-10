function showDepartureModal(button) {
  const id = button.getAttribute('data-id');
  const lastReturn = button.getAttribute('data-last-return');

  let suggestTime;
  if (lastReturn) {
    const baseTime = new Date(lastReturn);
    baseTime.setHours(baseTime.getHours() + 10);
    suggestTime = baseTime.toISOString().slice(0, 16);
  } else {
    const now = new Date();
    suggestTime = now.toISOString().slice(0, 16);
  }

  document.getElementById('reservationIdInput').value = id;
  document.getElementById('actualDepartureInput').value = suggestTime;
  new bootstrap.Modal(document.getElementById('departureModal')).show();
}

function showReturnModal(reservationId) {
  const modal = document.getElementById('returnModal');
  if (!modal) {
    console.error("入庫モーダルが見つかりません。");
    return;
  }

  const now = new Date();
  const suggestTime = now.toISOString().slice(0, 16);

  document.getElementById('returnReservationIdInput').value = reservationId;
  document.getElementById('actualReturnInput').value = suggestTime;

  new bootstrap.Modal(modal).show();
}

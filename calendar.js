// Delegated click handler: turns a calendar-day click into a Shiny input event.
document.addEventListener('click', function (e) {
  var cell = e.target.closest('.cal-day.has');
  if (cell && window.Shiny) {
    Shiny.setInputValue('cal_click', cell.getAttribute('data-date'), {priority: 'event'});
  }
});

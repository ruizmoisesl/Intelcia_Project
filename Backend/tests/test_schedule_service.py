"""Pruebas unitarias de la lógica de turnos (sin base de datos)."""
from datetime import date, time

from app.models.user import ShiftId
from app.services import schedule_service as sc
from app.services.schedule_service import Weekday


class TestGetScheduleForDay:
    # Turno 1
    def test_shift1_monday(self):
        day = sc.get_schedule_for_day(ShiftId.SHIFT_1, Weekday.MONDAY)
        assert (day.start, day.end) == (time(7, 0), time(17, 0))

    def test_shift1_tuesday_not_reduced(self):
        day = sc.get_schedule_for_day(ShiftId.SHIFT_1, Weekday.TUESDAY)
        assert day.end == time(17, 0)

    def test_shift1_wednesday_reduced(self):
        day = sc.get_schedule_for_day(ShiftId.SHIFT_1, Weekday.WEDNESDAY)
        assert (day.start, day.end) == (time(7, 0), time(16, 0))

    def test_shift1_friday_reduced(self):
        day = sc.get_schedule_for_day(ShiftId.SHIFT_1, Weekday.FRIDAY)
        assert day.end == time(16, 0)

    def test_shift1_weekend_none(self):
        assert sc.get_schedule_for_day(ShiftId.SHIFT_1, Weekday.SATURDAY) is None
        assert sc.get_schedule_for_day(ShiftId.SHIFT_1, Weekday.SUNDAY) is None

    # Turno 2
    def test_shift2_monday(self):
        day = sc.get_schedule_for_day(ShiftId.SHIFT_2, Weekday.MONDAY)
        assert (day.start, day.end) == (time(8, 0), time(15, 0))

    def test_shift2_wednesday_reduced(self):
        day = sc.get_schedule_for_day(ShiftId.SHIFT_2, Weekday.WEDNESDAY)
        assert (day.start, day.end) == (time(8, 0), time(14, 0))

    def test_shift2_saturday_special_not_reduced(self):
        day = sc.get_schedule_for_day(ShiftId.SHIFT_2, Weekday.SATURDAY)
        assert (day.start, day.end) == (time(7, 0), time(16, 0))

    def test_shift2_sunday_none(self):
        assert sc.get_schedule_for_day(ShiftId.SHIFT_2, Weekday.SUNDAY) is None

    # Turno 3
    def test_shift3_monday(self):
        day = sc.get_schedule_for_day(ShiftId.SHIFT_3, Weekday.MONDAY)
        assert (day.start, day.end) == (time(13, 0), time(22, 0))

    def test_shift3_thursday_reduced(self):
        day = sc.get_schedule_for_day(ShiftId.SHIFT_3, Weekday.THURSDAY)
        assert (day.start, day.end) == (time(13, 0), time(21, 0))

    # Turno 4 (medianoche como tipo horario real)
    def test_shift4_midnight_start(self):
        day = sc.get_schedule_for_day(ShiftId.SHIFT_4, Weekday.MONDAY)
        assert (day.start, day.end) == (time(0, 0), time(10, 0))

    def test_shift4_wednesday_reduced(self):
        day = sc.get_schedule_for_day(ShiftId.SHIFT_4, Weekday.WEDNESDAY)
        assert (day.start, day.end) == (time(0, 0), time(9, 0))

    def test_shift4_friday_end_is_nine(self):
        day = sc.get_schedule_for_day(ShiftId.SHIFT_4, Weekday.FRIDAY)
        assert day.end == time(9, 0)


class TestGetWeekSchedule:
    def test_week_has_seven_days_starting_monday(self):
        week = sc.get_week_schedule(ShiftId.SHIFT_1, date(2026, 8, 31))
        assert week.week_start == date(2026, 8, 31)
        assert len(week.days) == 7
        assert week.days[0].weekday is Weekday.MONDAY
        assert week.days[6].weekday is Weekday.SUNDAY

    def test_week_normalizes_to_monday(self):
        week = sc.get_week_schedule(ShiftId.SHIFT_1, date(2026, 9, 2))  # miércoles
        assert week.week_start == date(2026, 8, 31)

    def test_week_crosses_month(self):
        week = sc.get_week_schedule(ShiftId.SHIFT_1, date(2026, 9, 1))  # martes
        assert week.days[0].date == date(2026, 8, 31)
        assert week.days[1].date == date(2026, 9, 1)

    def test_week_crosses_year_end(self):
        week = sc.get_week_schedule(ShiftId.SHIFT_1, date(2027, 1, 1))  # viernes
        assert week.week_start == date(2026, 12, 28)
        assert week.days[6].date == date(2027, 1, 3)

    def test_week_leap_year_february(self):
        week = sc.get_week_schedule(ShiftId.SHIFT_1, date(2024, 3, 1))
        assert week.week_start == date(2024, 2, 26)
        assert week.days[3].date == date(2024, 2, 29)
        assert week.days[4].date == date(2024, 3, 1)

    def test_week_shift1_wednesday_reduced(self):
        week = sc.get_week_schedule(ShiftId.SHIFT_1, date(2026, 8, 31))
        assert week.days[2].end == time(16, 0)

    def test_week_shift2_includes_saturday(self):
        week = sc.get_week_schedule(ShiftId.SHIFT_2, date(2026, 8, 31))
        saturday = week.days[5]
        assert (saturday.start, saturday.end) == (time(7, 0), time(16, 0))
        assert week.days[6].start is None

    def test_week_shift2_holiday_is_rest(self):
        week = sc.get_week_schedule(ShiftId.SHIFT_2, date(2026, 7, 20))
        monday = week.days[0]
        assert monday.is_holiday is True
        assert monday.start is None and monday.end is None  # Turno 2 descansa festivos
        saturday = week.days[5]
        assert (saturday.start, saturday.end) == (time(7, 0), time(16, 0))  # sábado normal

class TestGetScheduleForDate:
    def test_holiday_replaces_weekday_schedule(self):
        # Lunes 20-jul-2026 festivo: Turno 1 trabaja la jornada festiva.
        day = sc.get_schedule_for_date(ShiftId.SHIFT_1, date(2026, 7, 20))
        assert (day.start, day.end) == (time(8, 0), time(14, 0))

    def test_shift2_holiday_is_rest_day(self):
        # Regla v0.3: el Turno 2 NO trabaja festivos (compensa con sábados).
        assert sc.get_schedule_for_date(ShiftId.SHIFT_2, date(2026, 7, 20)) is None  # lunes festivo

    def test_shift2_saturday_holiday_is_rest_day(self):
        # Decisión: el festivo prevalece aunque caiga en sábado.
        assert sc.get_schedule_for_date(ShiftId.SHIFT_2, date(2027, 12, 25)) is None

    def test_shift2_normal_monday_unchanged(self):
        day = sc.get_schedule_for_date(ShiftId.SHIFT_2, date(2026, 9, 7))
        assert (day.start, day.end) == (time(8, 0), time(15, 0))

    def test_holiday_does_not_create_rest_day(self):
        # Sábado 25-dic-2027 festivo: el Turno 1 no trabaja sábados → descanso.
        assert sc.get_schedule_for_date(ShiftId.SHIFT_1, date(2027, 12, 25)) is None

    def test_non_holiday_uses_weekday_rules(self):
        day = sc.get_schedule_for_date(ShiftId.SHIFT_1, date(2026, 9, 2))  # miércoles normal
        assert (day.start, day.end) == (time(7, 0), time(16, 0))
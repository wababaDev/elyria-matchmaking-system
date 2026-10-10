import calendar
from datetime import date


def add_months(day: date, months: int) -> date:
    """31 Jan + 1 month -> 28/29 Feb, not an error."""
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))
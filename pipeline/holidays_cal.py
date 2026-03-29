"""Holiday calendar engine — per-office, per-country holiday detection.

Used by:
- aggregate.py: exclude holidays from working day counts
- baselines.py: exclude holidays from rolling window
- query_person: don't count holidays as absent days
"""

import holidays
import pandas as pd
from datetime import date
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config

# Cache per-country holiday objects
_holiday_cache = {}


def get_holidays_for_office(office_name, year=None):
    """Get a holidays object for the given office's country."""
    country = config.OFFICE_COUNTRY.get(office_name)
    if not country:
        return {}

    if year is None:
        year = date.today().year

    key = (country, year)
    if key not in _holiday_cache:
        try:
            _holiday_cache[key] = holidays.country_holidays(country, years=[year, year - 1])
        except NotImplementedError:
            _holiday_cache[key] = {}
    return _holiday_cache[key]


def is_holiday(office_name, check_date):
    """Check if a date is a public holiday for the given office."""
    if isinstance(check_date, pd.Timestamp):
        check_date = check_date.date()
    hols = get_holidays_for_office(office_name, check_date.year)
    return check_date in hols


def get_holiday_name(office_name, check_date):
    """Get the holiday name, or None if not a holiday."""
    if isinstance(check_date, pd.Timestamp):
        check_date = check_date.date()
    hols = get_holidays_for_office(office_name, check_date.year)
    return hols.get(check_date)


def get_workdays(office_name, start_date, end_date):
    """Get business days excluding public holidays for the office's country."""
    all_business = pd.bdate_range(start=start_date, end=end_date)
    hols = get_holidays_for_office(office_name, start_date.year if hasattr(start_date, 'year') else pd.Timestamp(start_date).year)

    workdays = [d for d in all_business if d.date() not in hols]
    return workdays


def get_workday_count(office_name, start_date, end_date):
    """Count business days excluding holidays."""
    return len(get_workdays(office_name, start_date, end_date))


if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("Holidays by office (2026):")
    seen = set()
    for office, country in sorted(config.OFFICE_COUNTRY.items()):
        if country in seen:
            continue
        seen.add(country)
        hols = get_holidays_for_office(office, 2026)
        hol_2026 = {k: v for k, v in hols.items() if k.year == 2026}
        print(f"\n  {office} ({country}): {len(hol_2026)} holidays")
        for d, name in sorted(hol_2026.items())[:5]:
            print(f"    {d}: {name}")
        if len(hol_2026) > 5:
            print(f"    ... and {len(hol_2026) - 5} more")

    # Test specific case: Feb 16 2026 = Presidents' Day (US)
    print(f"\n  Feb 16 2026 is holiday for Atlanta? {is_holiday('Atlanta', date(2026, 2, 16))}")
    print(f"  Feb 16 2026 is holiday for Prague? {is_holiday('Prague Rustonka', date(2026, 2, 16))}")
    print(f"  Atlanta workdays Jan-Mar 2026: {get_workday_count('Atlanta', date(2026, 1, 1), date(2026, 3, 26))}")

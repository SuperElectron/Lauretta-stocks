from src.data.xbrl import annual_points, annual_series, mark_stale


def fact(start, end, val, form="10-K", filed="2026-07-29", fp="FY"):
    entry = {"end": end, "val": val, "form": form, "filed": filed, "fp": fp}
    if start:
        entry["start"] = start
    return entry


def test_annual_points_keeps_full_years_from_annual_filings_newest_first():
    facts = [
        fact("2025-07-01", "2026-06-30", 331, filed="2026-07-29"),
        fact("2024-07-01", "2025-06-30", 280, filed="2025-07-30"),
        fact("2025-07-01", "2026-03-31", 241, form="10-Q", fp="Q3"),  # nine months
        fact("2026-01-01", "2026-03-31", 82, form="10-Q", fp="Q3"),  # a quarter
    ]
    assert [p["value"] for p in annual_points(facts)] == [331, 280]


def test_restated_year_uses_the_latest_filing():
    facts = [
        fact("2024-07-01", "2025-06-30", 280, filed="2025-07-30"),
        fact("2024-07-01", "2025-06-30", 281, filed="2026-07-29"),
    ]
    assert annual_points(facts)[0]["value"] == 281


def test_balance_sheet_instants_count_at_fiscal_year_end_only():
    facts = [
        fact(None, "2026-06-30", 31, fp="FY"),
        fact(None, "2026-03-31", 32, form="10-Q", fp="Q3"),
    ]
    assert [p["value"] for p in annual_points(facts)] == [31]


def test_series_prefers_the_tag_with_the_most_recent_year():
    taxonomies = {
        "us-gaap": {
            "Revenues": {"units": {"USD": [fact("2017-07-01", "2018-06-30", 110)]}},
            "RevenueFromContractWithCustomerExcludingAssessedTax": {
                "units": {"USD": [fact("2025-07-01", "2026-06-30", 331)]}
            },
        }
    }
    tags = ("us-gaap:Revenues", "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax")
    series = annual_series(taxonomies, tags, 4)
    assert series["tag"] == "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
    assert series["years"][0]["value"] == 331


def test_foreign_filer_reads_ifrs_from_a_20f():
    taxonomies = {
        "ifrs-full": {
            "Revenue": {"units": {"USD": [fact("2025-01-01", "2025-12-31", 266, "20-F")]}}
        }
    }
    series = annual_series(taxonomies, ("us-gaap:Revenues", "ifrs-full:Revenue"), 4)
    assert series["years"][0]["value"] == 266


def test_series_not_found_is_explicit():
    assert annual_series({}, ("us-gaap:GrossProfit",), 4) == {"found": False}


def test_series_that_stopped_years_before_revenue_is_marked_stale():
    def series(end):
        return {"found": True, "years": [{"period_end": end, "value": 1, "filed": end}]}

    items = {
        "revenue": series("2026-06-30"),
        "cash": series("2018-06-30"),
        "debt": series("2026-06-30"),
        "capex": {"found": False},
    }
    marked = mark_stale(items)
    assert marked["cash"]["stale"] is True
    assert marked["debt"]["stale"] is False
    assert "stale" not in marked["capex"]

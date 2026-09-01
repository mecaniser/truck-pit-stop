"""Shop Work names the carrier, not the contact.

This is a heavy-duty shop: the work belongs to an LLC, and the person who
answers the phone is secondary. fleet_display_name only ever special-cased the
internal-fleet house account and otherwise returned "First Last", so an order
for ELIS LOGISTICS LLC showed as "Sergio Burca" — the company name was on the
record and simply never read.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.internal_fleet import fleet_display_name


def _customer(**kw):
    base = dict(first_name="Sergio", last_name="Burca", company_name=None, is_internal_fleet=False)
    base.update(kw)
    return SimpleNamespace(**base)


def test_the_company_is_the_name_shown():
    assert fleet_display_name(_customer(company_name="ELIS LOGISTICS LLC"), None) == "ELIS LOGISTICS LLC"


def test_the_person_is_shown_only_when_there_is_no_company():
    assert fleet_display_name(_customer(), None) == "Sergio Burca"
    assert fleet_display_name(_customer(company_name="   "), None) == "Sergio Burca"


def test_an_internal_fleet_order_still_shows_the_fleet_company():
    """The house account's placeholder name must never surface."""
    customer = _customer(first_name="Internal", last_name="Fleet", is_internal_fleet=True)
    assert fleet_display_name(customer, "77 Cargo LLC") == "77 Cargo LLC"


def test_the_fleet_name_wins_over_the_house_account_company():
    customer = _customer(company_name="House Account", is_internal_fleet=True)
    assert fleet_display_name(customer, "77 Cargo LLC") == "77 Cargo LLC"


def test_a_fleet_customer_without_a_configured_fleet_name_falls_back_to_its_company():
    customer = _customer(company_name="House Account", is_internal_fleet=True)
    assert fleet_display_name(customer, None) == "House Account"

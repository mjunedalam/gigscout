"""Google Ads lead form webhook → inbound leads."""

from datetime import UTC, datetime

from gigscout.inbound.google_ads import GoogleAdsLeadForm, key_matches, to_lead

KEY = "s3cret-webhook-key"


def form_payload(**overrides) -> dict:
    payload = {
        "lead_id": "TeSter-123",
        "api_version": "1.0",
        "form_id": 40000000,
        "campaign_id": 12345,
        "google_key": KEY,
        "is_test": False,
        "user_column_data": [
            {"column_id": "FULL_NAME", "column_name": "Full Name", "string_value": "Jane Doe"},
            {"column_id": "EMAIL", "column_name": "User Email", "string_value": "jane@clinic.example"},
            {"column_id": "COMPANY_NAME", "column_name": "Company", "string_value": "Bright Clinic"},
            {"column_id": "COUNTRY", "column_name": "Country", "string_value": "Canada"},
            {"column_id": "q1", "column_name": "What do you need built?",
             "string_value": "Patient booking app in React Native with a Django backend"},
            {"column_id": "q2", "column_name": "Project budget", "string_value": "$8,000 - $12,000"},
        ],
    }
    return {**payload, **overrides}


def test_form_becomes_inbound_lead_with_client_and_budget():
    received = datetime(2026, 11, 3, tzinfo=UTC)

    lead = to_lead(GoogleAdsLeadForm.model_validate(form_payload()), received_at=received)

    assert lead.id == "google_ads:TeSter-123"
    assert lead.kind == "inbound" and lead.source == "google_ads"
    assert lead.title == "Inbound enquiry from Bright Clinic"
    assert lead.client.email == "jane@clinic.example" and lead.client.country == "Canada"
    assert "Contact: Jane Doe" in lead.description
    assert "What do you need built?: Patient booking app" in lead.description
    assert "jane@clinic.example" not in lead.description  # contact details stay out of embedded text
    assert (lead.budget.minimum, lead.budget.maximum) == (8000, 12000)
    assert lead.posted_at == received
    assert "campaignId=12345" in lead.url


def test_minimal_form_still_yields_a_lead():
    lead = to_lead(GoogleAdsLeadForm(lead_id="x", google_key=KEY))
    assert lead.title == "Inbound enquiry from a prospect"
    assert lead.client is None and lead.budget is None and lead.url == ""


def test_key_comparison():
    form = GoogleAdsLeadForm(lead_id="x", google_key=KEY)
    assert key_matches(form, KEY)
    assert not key_matches(form, "other")

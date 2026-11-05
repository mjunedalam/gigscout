"""The knowledge base: the company's own documents, which pitches cite and are checked against."""

import io

from pypdf import PdfWriter

from gigscout.store.knowledge import KnowledgeBase, chunk_text, claim_sentences, format_evidence
from tests.conftest import FakeEmbedder
from tests.test_pitches import AUTOPILOT, desk, pending, scout  # noqa: F401  (desk is a fixture)

CASE_STUDY = ("SaaS MVP for a clinic group. We built a patient booking SaaS MVP for clinics with Django and React "
              "in 10 weeks. The clinics cut no-shows by 30 percent. Python django and react team.")
PRICING = "Our rates: fixed-price MVPs from 15000 USD. Retainers from 4000 USD a month."


def test_chunks_overlap_and_never_lose_text():
    text = " ".join(f"Sentence number {i} is here." for i in range(200))
    chunks = chunk_text(text, size=300, overlap=60)
    assert len(chunks) > 5 and all(len(c) <= 300 for c in chunks)
    assert "Sentence number 0 " in chunks[0] and "Sentence number 199" in chunks[-1]
    assert chunk_text("   ") == []


def test_only_sentences_that_state_facts_count_as_claims():
    body = ("Hi Anna,\n\nWe built a booking app for 12 clinics. I read your post about the portal. "
            "Our team has 8 years with Django. Would a call help?\n\n> quoted 99 lines")
    assert claim_sentences(body) == ["We built a booking app for 12 clinics.", "Our team has 8 years with Django."]


def test_search_finds_relevant_documents_and_claims_are_checked(tmp_path):
    import chromadb
    kb = KnowledgeBase(chromadb.PersistentClient(path=str(tmp_path)), "test_kb", FakeEmbedder())
    assert kb.search("clinic booking") == []
    kb.add(1, "Clinic booking MVP", "case_study", CASE_STUDY)
    kb.add(2, "Rates", "pricing", PRICING)
    found = kb.search("SaaS MVP for clinics with Django and React")
    assert found and found[0].title == "Clinic booking MVP"
    assert format_evidence(found).startswith("[1] Clinic booking MVP (case study):")
    assert "do not mention" in format_evidence(())

    claims = kb.check_claims("We built a patient booking SaaS MVP for clinics with Django and React in 10 weeks. "
                             "We have launched 40 rockets to Mars for NASA.", found)
    assert [c.supported for c in claims] == [True, False]
    assert claims[0].source == "Clinic booking MVP" and claims[1].source is None

    kb.remove(1)
    assert all(e.doc_id != 1 for e in kb.search("clinic booking MVP django"))


def test_pitches_cite_the_companys_own_work_and_flag_what_it_cannot_back(desk):  # noqa: F811
    client, _ = desk
    assert client.get("/api/knowledge").json() == {"docs": [], "kinds": client.get("/api/knowledge").json()["kinds"],
                                                   "chunks": 0}
    added = client.post("/api/knowledge", json={"title": "Clinic booking MVP", "kind": "case_study",
                                                "text": CASE_STUDY})
    assert added.status_code == 201 and added.json()["chunks"] >= 1
    client.put("/api/pitches/settings", json=AUTOPILOT)
    scout(client)

    clinic = next(i["outreach"] for i in pending(client) if "clinics" in i["lead"]["title"])
    assert clinic["evidence"] and clinic["evidence"][0]["title"] == "Clinic booking MVP"
    assert "patient booking" in clinic["body"]  # the drafter was given the evidence
    assert any(c["supported"] for c in clinic["claims"])

    edited = client.put(f"/api/outreach/{clinic['id']}", json={
        "channel": "bid", "to": None, "subject": "", "body": "We have shipped 500 apps for Fortune 500 banks."}).json()
    assert [c["supported"] for c in edited["claims"]] == [False]  # a person's edit is checked again

    hits = client.get("/api/knowledge/search", params={"q": "clinic booking django"}).json()["results"]
    assert hits[0]["title"] == "Clinic booking MVP" and hits[0]["excerpt"]
    checked = client.post("/api/knowledge/check", json={"text": "We built 3 moon bases."}).json()
    assert checked["claims"][0]["supported"] is False


def test_without_documents_pitches_work_as_before(desk):  # noqa: F811
    client, _ = desk
    client.put("/api/pitches/settings", json=AUTOPILOT)
    scout(client)
    first = pending(client)[0]["outreach"]
    assert first["evidence"] is None and first["claims"] is None
    assert client.post("/api/knowledge/check", json={"text": "We built 3 moon bases."}).json()["empty"] is True


def test_uploads_read_text_and_pdf_and_refuse_the_rest(desk):  # noqa: F811
    client, _ = desk
    md = client.post("/api/knowledge/upload", params={"filename": "fintech_case-study.md", "kind": "case_study"},
                     content=b"# Fintech app\n\nWe built a mobile banking app for a fintech startup in Berlin.")
    assert md.status_code == 201 and md.json()["title"] == "fintech case study"
    listed = client.get("/api/knowledge").json()["docs"][0]
    assert listed["created_at"].endswith("+00:00")  # never read as local time

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    blank = io.BytesIO()
    writer.write(blank)
    refused = client.post("/api/knowledge/upload", params={"filename": "scan.pdf"}, content=blank.getvalue())
    assert refused.status_code == 422 and "OCR" in refused.json()["detail"]
    assert client.post("/api/knowledge/upload", params={"filename": "x.pdf"}, content=b"not a pdf").status_code == 422
    assert client.post("/api/knowledge/upload", params={"filename": "x.exe"}, content=b"MZ" * 20).status_code == 415
    eleven_mb = b"a" * (10 * 1024 * 1024 + 1)
    too_big = client.post("/api/knowledge/upload", params={"filename": "big.txt"}, content=eleven_mb)
    assert too_big.status_code == 413

    doc_id = md.json()["id"]
    assert client.delete(f"/api/knowledge/{doc_id}").status_code == 204
    assert client.get("/api/knowledge").json()["docs"] == []
    assert client.delete(f"/api/knowledge/{doc_id}").status_code == 404


def test_documents_need_a_known_kind_and_real_text(desk):  # noqa: F811
    client, _ = desk
    assert client.post("/api/knowledge", json={"title": "x", "kind": "nonsense", "text": "a" * 30}).status_code == 422
    assert client.post("/api/knowledge", json={"title": "x", "text": "short"}).status_code == 422

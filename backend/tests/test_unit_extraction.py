from datetime import date

import pytest

from app.seed_data import CARDIOLOGY_LETTER, DISCHARGE, HMO_VISIT, NURSE_NOTE_HE, make_pdf
from app.services import extraction as ex

MAX = 10 * 1024 * 1024


class TestValidation:
    def test_accepts_generated_pdf(self):
        assert ex.validate_upload("letter.pdf", make_pdf("hello world"), MAX).kind == "pdf"

    def test_accepts_utf8_text_and_hebrew(self):
        assert ex.validate_upload("note.txt", NURSE_NOTE_HE.encode(), MAX).kind == "text"

    @pytest.mark.parametrize("name,data,code", [
        ("empty.txt", b"", "empty"),
        ("big.txt", b"a" * (MAX + 1), "too_large"),
        ("tool.exe", b"MZ\x90\x00", "unsupported_type"),
        ("page.html", b"<script>alert(1)</script>", "unsupported_type"),
        ("fake.pdf", b"MZ not a pdf", "signature_mismatch"),
        ("disguised.txt", b"MZ\x90\x00binary", "signature_mismatch"),
        ("zip.txt", b"PK\x03\x04....", "signature_mismatch"),
        ("latin1.txt", "caf\xe9".encode("latin-1"), "bad_encoding"),
        ("nul.txt", b"abc\x00def", "binary_content"),
        ("bad.json", b"{not json", "bad_json"),
        ("other.json", b'{"resourceType": "Medication"}', "unsupported_fhir"),
        ("a/../b.txt", b"x", "bad_filename"),
    ])
    def test_rejections(self, name, data, code):
        with pytest.raises(ex.UploadRejected) as e:
            ex.validate_upload(name, data, MAX)
        assert e.value.code == code

    def test_rejects_pdf_with_javascript(self):
        evil = make_pdf("hi").replace(b"<< /Type /Catalog", b"<< /OpenAction << /S /JavaScript /JS (app.alert(1)) >> /Type /Catalog")
        with pytest.raises(ex.UploadRejected) as e:
            ex.validate_upload("evil.pdf", evil, MAX)
        assert e.value.code == "active_content"

    def test_rejects_pdf_with_launch_action(self):
        evil = make_pdf("hi").replace(b"<< /Type /Catalog", b"<< /OpenAction << /S /Launch /F (cmd.exe) >> /Type /Catalog")
        with pytest.raises(ex.UploadRejected):
            ex.validate_upload("evil.pdf", evil, MAX)

    def test_rejects_malformed_pdf(self):
        with pytest.raises(ex.UploadRejected) as e:
            ex.validate_upload("broken.pdf", b"%PDF-1.4\ngarbage", MAX)
        assert e.value.code == "malformed_pdf"


class TestTextAndMetadata:
    def test_pdf_text_roundtrip(self):
        res = ex.extract_text("pdf", make_pdf(CARDIOLOGY_LETTER))
        assert res.status == "processed"
        assert "Transthoracic echocardiogram within 6 weeks" in res.text

    def test_empty_pdf_needs_review_not_fabricated(self):
        res = ex.extract_text("pdf", make_pdf(""))
        assert res.status == "needs_review"
        assert "OCR is not supported" in res.detail

    def test_metadata(self):
        md = ex.extract_metadata(CARDIOLOGY_LETTER, ["Cedar Ridge Cardiology Clinic", "Tamar Valley Health Fund"])
        assert md.document_date == date(2026, 7, 8)
        assert md.organization_name == "Cedar Ridge Cardiology Clinic"
        assert md.author == "Dr. Yael Ronen"
        assert md.category == "consultation_note"
        assert md.language == "en"

    def test_hebrew_metadata_day_first_date(self):
        md = ex.extract_metadata(NURSE_NOTE_HE, [])
        assert md.language == "he"
        assert md.document_date == date(2026, 8, 10)

    def test_discharge_category(self):
        assert ex.extract_metadata(DISCHARGE, []).category == "discharge_summary"

    @pytest.mark.parametrize("value,expected", [("2026-07-08", date(2026, 7, 8)), ("08/07/2026", date(2026, 7, 8)),
                                                ("31/02/2026", None), ("x", None)])
    def test_parse_date(self, value, expected):
        assert ex.parse_date(value) == expected


class TestRecommendations:
    def test_cardiology_letter(self):
        recs = ex.extract_recommendations(CARDIOLOGY_LETTER)
        by_text = {r.text: r for r in recs}
        assert len(recs) == 5
        echo = by_text["Transthoracic echocardiogram within 6 weeks."]
        assert echo.kind == "imaging" and echo.timeframe_text == "within 6 weeks" and echo.targets == ["echocardiogram"]
        assert echo.due_date is None  # never computed from a relative timeframe
        assert by_text["Exercise stress test after the echocardiogram."].targets == ["stress_test"]
        assert by_text["Repeat lipid panel in 3 months."].kind == "lab_test"
        assert by_text["Follow-up visit in our clinic after the echocardiogram."].kind == "follow_up_visit"
        assert by_text["Consider a second opinion from an international cardiology specialist."].kind == "referral"

    def test_passage_offsets_point_to_source(self):
        for r in ex.extract_recommendations(CARDIOLOGY_LETTER):
            assert CARDIOLOGY_LETTER[r.char_start:r.char_end] == r.passage

    def test_hmo_visit(self):
        recs = ex.extract_recommendations(HMO_VISIT)
        assert {r.kind for r in recs} == {"lab_test", "referral"}
        lab = next(r for r in recs if r.kind == "lab_test")
        assert lab.targets == ["cbc", "lipid_panel"]

    def test_hebrew(self):
        recs = ex.extract_recommendations(NURSE_NOTE_HE)
        assert len(recs) == 1 and recs[0].kind == "follow_up_visit" and recs[0].timeframe_text == "בעוד חודש"

    def test_negation_and_explicit_due_date(self):
        text = "Plan:\n- No follow-up needed for the rash.\n- Repeat CBC by 2026-11-30.\n"
        recs = ex.extract_recommendations(text)
        assert len(recs) == 1
        assert recs[0].due_date == date(2026, 11, 30) and recs[0].kind == "lab_test"

    def test_no_recommendations(self):
        assert ex.extract_recommendations("Blood pressure 120/80. Patient feels well.") == []

import sys
import os
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main_watcher import parse_invoice_text, calculate_confidence, detect_client
import validation_ui


class TestInvoiceParsing(unittest.TestCase):

    def test_parse_basic_invoice(self):
        sample_text = "Facture N° : TAU_2026-413\nSOCIETE ACME\nDate : 12/03/2026\nEchéance : 12/04/2026\nTotal TTC : 1 200,50 €"
        result = parse_invoice_text(sample_text)
        self.assertEqual(result["num_facture"], "TAU_2026-413")
        self.assertEqual(result["date_facture"], "12/03/2026")
        self.assertEqual(result["date_echeance"], "12/04/2026")
        self.assertEqual(result["montant_ttc"], "1200,50")

    def test_parse_missing_echeance_defaults_to_j30(self):
        sample_text = "TAU 2026 999 01/01/2026\nNet à payer 500.00 EUR"
        result = parse_invoice_text(sample_text)
        self.assertEqual(result["num_facture"], "TAU_2026-999")
        self.assertEqual(result["date_facture"], "01/01/2026")
        self.assertEqual(result["date_echeance"], "31/01/2026")
        self.assertTrue(result["_echeance_calculee"])
        self.assertEqual(result["montant_ttc"], "500.00")

    def test_parse_complex_table(self):
        sample_text = (
            "SOCIETE BETA\nDate de facturation : 14.05.2026\n"
            "Numéro de document : TAU_2026-102\n"
            "Total HT 1500,00\nTVA 20% 300,00\nTotal TTC 1 800,00 €\n"
        )
        result = parse_invoice_text(sample_text)
        self.assertEqual(result["client"], "BETA")
        self.assertEqual(result["num_facture"], "TAU_2026-102")
        self.assertEqual(result["date_facture"], "14.05.2026")
        self.assertEqual(result["montant_ttc"], "1800,00")

    def test_parse_missing_client(self):
        sample_text = "Facture : TAU_2026-001\nTotal : 150,00 EUR"
        result = parse_invoice_text(sample_text)
        self.assertEqual(result["client"], "")
        self.assertEqual(result["montant_ttc"], "150,00")

    def test_avoir_negates_amount(self):
        sample_text = "AVOIR\nTAU 2026 050 15/02/2026\nTotal TTC 200,00 €"
        result = parse_invoice_text(sample_text)
        self.assertTrue(result["is_avoir"])
        self.assertTrue(str(result["montant_ttc"]).startswith("-"))

    def test_session_dates_excluded_from_date_facture(self):
        sample_text = (
            "Session du 10/03/2026 au 12/03/2026\n"
            "TAU 2026 600 05/03/2026\nTotal TTC 800,00 €"
        )
        result = parse_invoice_text(sample_text)
        self.assertEqual(result["session"], "10/03/2026 au 12/03/2026")
        self.assertEqual(result["date_facture"], "05/03/2026")

    def test_thousands_separator_in_amount(self):
        sample_text = "TAU 2026 700 01/04/2026\nTotal TTC 1.234,56 €"
        result = parse_invoice_text(sample_text)
        self.assertEqual(result["montant_ttc"], "1234,56")


class TestConfidenceScore(unittest.TestCase):

    def test_full_data_scores_10(self):
        data = {
            "num_facture": "TAU_2026-001", "client": "ACME",
            "date_facture": "01/01/2026", "date_echeance": "31/01/2026",
            "montant_ttc": "500,00", "_echeance_calculee": False
        }
        self.assertEqual(calculate_confidence(data), 10)

    def test_calculated_echeance_penalizes_minus1(self):
        data = {
            "num_facture": "TAU_2026-001", "client": "ACME",
            "date_facture": "01/01/2026", "date_echeance": "31/01/2026",
            "montant_ttc": "500,00", "_echeance_calculee": True
        }
        self.assertEqual(calculate_confidence(data), 9)

    def test_missing_fields_reduce_score(self):
        data = {
            "num_facture": "", "client": "",
            "date_facture": "", "date_echeance": "",
            "montant_ttc": "", "_echeance_calculee": False
        }
        self.assertEqual(calculate_confidence(data), 0)


class TestValidationUiParsing(unittest.TestCase):
    """Couvre la logique de parsing de validation_ui (identique à main_watcher)."""

    def test_parse_basic_invoice(self):
        sample_text = "TAU 2026 413 12/03/2026\nSOCIETE ACME\nTotal TTC 1 200,50 €"
        result = validation_ui.parse_invoice_text(sample_text)
        self.assertEqual(result["num_facture"], "TAU_2026-413")
        self.assertIsInstance(result["montant_ttc"], str)

    def test_session_extraction(self):
        sample_text = "Session du 01/03/2026 au 03/03/2026\nTAU 2026 500 28/02/2026\nTotal TTC 300,00 €"
        result = validation_ui.parse_invoice_text(sample_text)
        self.assertIn("01/03/2026", result["session"])
        self.assertEqual(result["date_facture"], "28/02/2026")


if __name__ == '__main__':
    unittest.main()

import sys
import os
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main_watcher import parse_invoice_text, calculate_confidence
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


class TestTier0Regex(unittest.TestCase):
    """Couvre le Tier 0 : format littéral TAU_YYYY-NNN présent dans les PDFs natifs."""

    def test_tier0_num_only(self):
        sample_text = "Facture N° TAU_2026-557\nSociété EXAIL\nTotal TTC 465,00 €"
        result = parse_invoice_text(sample_text)
        self.assertEqual(result["num_facture"], "TAU_2026-557")

    def test_tier0_with_date(self):
        sample_text = "TAU_2026-557 25-02-2026\nTotal TTC 465,00 €"
        result = parse_invoice_text(sample_text)
        self.assertEqual(result["num_facture"], "TAU_2026-557")
        self.assertEqual(result["date_facture"], "25-02-2026")

    def test_tier0_with_both_dates(self):
        sample_text = "TAU_2026-487 01-02-2026 1 03-03-2026\nTotal TTC 1 200,00 €"
        result = parse_invoice_text(sample_text)
        self.assertEqual(result["num_facture"], "TAU_2026-487")
        self.assertEqual(result["date_facture"], "01-02-2026")
        self.assertEqual(result["date_echeance"], "03-03-2026")
        self.assertFalse(result["_echeance_calculee"])


class TestAmountPriority(unittest.TestCase):
    """Couvre la priorité des mots-clés montant (BUG-AMOUNT-ZERO / BUG-MONTANT-PERSIST)."""

    def test_total_ttc_takes_priority_over_montant(self):
        sample_text = (
            "TAU_2026-050 15/02/2026\n"
            "Montant 0,00 €\nEncaissement 0,00 €\n"
            "Total TTC 465,00 €"
        )
        result = parse_invoice_text(sample_text)
        self.assertEqual(result["montant_ttc"], "465,00")

    def test_restant_du_nonzero_used_when_no_total_ttc(self):
        sample_text = "TAU_2026-060 20/03/2026\nMontant 0,00 €\nRestant dû 320,00 €"
        result = parse_invoice_text(sample_text)
        self.assertEqual(result["montant_ttc"], "320,00")

    def test_restant_du_zero_falls_back_to_montant(self):
        sample_text = "TAU_2026-070 20/03/2026\nMontant 500,00 €\nRestant dû 0,00 €"
        result = parse_invoice_text(sample_text)
        self.assertEqual(result["montant_ttc"], "500,00")

    def test_amount_dot_decimal_260(self):
        # Cas réel CPF : montant avec point décimal 260.00€
        sample_text = "TAU_2026-484 04-02-2026\nMontant 260.00€\nEncaissement 0.00€\nRestant du 260.00€"
        result = parse_invoice_text(sample_text)
        self.assertNotEqual(result["montant_ttc"], "")
        self.assertNotIn(result["montant_ttc"], ["0.00", "0,00"])

    def test_amount_dot_decimal_465(self):
        # Cas réel EXAIL : 465.00€
        sample_text = "TAU_2026-558 25-02-2026\nMontant 465.00€\nEncaissement 0.00€\nRestant du 465.00€"
        result = parse_invoice_text(sample_text)
        self.assertNotEqual(result["montant_ttc"], "")
        self.assertNotIn(result["montant_ttc"], ["0.00", "0,00"])


class TestSessionDetection(unittest.TestCase):
    """Couvre la détection de session (BUG-SESSION-CONFUSION)."""

    def test_same_date_session_not_captured(self):
        # TAU_2026-559 : date facture = date échéance → ne doit PAS être une session
        sample_text = "TAU_2026-559\nSession du 25-02-2026 au 25-02-2026\nMontant 450.00€"
        result = parse_invoice_text(sample_text)
        self.assertEqual(result["session"], "")

    def test_different_dates_session_captured(self):
        sample_text = "Session du 23/02/2026 au 24/02/2026\nTAU_2026-558 25-02-2026\nMontant 465.00€"
        result = parse_invoice_text(sample_text)
        self.assertIn("23/02/2026", result["session"])
        self.assertIn("24/02/2026", result["session"])


class TestTier4YearFilter(unittest.TestCase):
    """Couvre le filtre année du Tier 4 (BUG-NUM-FAUX-POSITIF)."""

    def test_tier4_ignores_invalid_year(self):
        # MC30031699 → 0031 n'est pas une année valide, ne doit pas être capturé
        sample_text = "Numéro de commande : MC30031699\nMontant 465.00€"
        result = parse_invoice_text(sample_text)
        self.assertEqual(result["num_facture"], "")


class TestClientCPF(unittest.TestCase):
    """Couvre la séparation client / type pour les factures CPF."""

    def test_caisse_des_depots_client_not_cpf(self):
        sample_text = (
            "TAU_2026-100 01/01/2026\n"
            "CAISSE DES DEPOTS ET CONSIGNATIONS\n"
            "Total TTC 800,00 €"
        )
        result = parse_invoice_text(sample_text)
        self.assertEqual(result["client"], "CAISSE DES DEPOTS")
        self.assertEqual(result["type_facture"], "CPF")


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

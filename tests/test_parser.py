import sys
import os
import unittest
import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main_watcher import parse_invoice_text


class TestInvoiceParsing(unittest.TestCase):

    def test_parse_basic_invoice(self):
        """Test extraction des champs de base avec mots-clés explicites."""
        sample_text = "SOCIETE ACME\nFacture N° : TAU_2026-413\nDate : 12/03/2026\nTotal TTC : 1 200,50 €"
        result = parse_invoice_text(sample_text)

        self.assertEqual(result["num_facture"], "TAU_2026-413")
        # parse_invoice_text retourne datetime.date, pas une str
        self.assertEqual(result["date_facture"], datetime.date(2026, 3, 12))
        # L'échéance est date_facture + 30j
        self.assertEqual(result["date_echeance"], datetime.date(2026, 4, 11))
        # montant retourné en float
        self.assertEqual(result["montant_ttc"], 1200.5)

    def test_parse_missing_echeance(self):
        """Test calcul automatique de l'échéance (+30j) quand elle est absente."""
        sample_text = "GENAVIR\nFacture TAU_2026-999\nDate: 01/01/2026\nNet a payer 500.00 EUR"
        result = parse_invoice_text(sample_text)

        self.assertEqual(result["num_facture"], "TAU_2026-999")
        self.assertEqual(result["date_facture"], datetime.date(2026, 1, 1))
        # Echeance auto = +30j
        self.assertEqual(result["date_echeance"], datetime.date(2026, 1, 31))
        self.assertEqual(result["montant_ttc"], 500.0)

    def test_parse_complex_table(self):
        """Test extraction sur facture avec tableau (Total TTC en bas)."""
        sample_text = (
            "CORSICA LINEA\n"
            "Date de facturation : 14.05.2026\n"
            "Numéro de document : TAU_2026-102\n"
            "Description Quantité Prix Unitaire Montant\n"
            "Service A 1 1500,00 1500,00\n"
            "Total HT 1500,00\n"
            "TVA 20% 300,00\n"
            "Total TTC 1 800,00 €\n"
        )
        result = parse_invoice_text(sample_text)

        self.assertEqual(result["num_facture"], "TAU_2026-102")
        self.assertEqual(result["date_facture"], datetime.date(2026, 5, 14))
        self.assertEqual(result["montant_ttc"], 1800.0)

    def test_parse_missing_client(self):
        """Test quand aucun client n'est identifiable."""
        sample_text = "Facture : TAU_2026-001\nTotal TTC 150,00 EUR"
        result = parse_invoice_text(sample_text)

        self.assertEqual(result["client"], "")
        self.assertEqual(result["montant_ttc"], 150.0)

    def test_parse_cpf_type(self):
        """Test détection type CPF."""
        sample_text = "Compte Personnel de Formation\nTAU_2026-487\n01/03/2026\nTotal TTC 1500.00 EUR"
        result = parse_invoice_text(sample_text)

        self.assertEqual(result["type_facture"], "CPF")
        self.assertEqual(result["client"], "CPF")

    def test_parse_date_with_spaces(self):
        """Test tolérance aux dates OCR avec espaces : 05 / 03 / 2026."""
        sample_text = "NAVY SERVICE\nTAU_2026-100\n05 / 03 / 2026\nMontant TTC 465,00 EUR"
        result = parse_invoice_text(sample_text)

        self.assertEqual(result["date_facture"], datetime.date(2026, 3, 5))
        self.assertEqual(result["montant_ttc"], 465.0)

    def test_parse_footer_capital_ignored(self):
        """Test que 'SARL au capital de X EUR' ne pollue pas le montant."""
        sample_text = (
            "CORSICA LINEA\nTAU_2026-600\n10/03/2026\n"
            "SARL au capital de 7500 EUR\n"
            "Total TTC 5 000,00 EUR"
        )
        result = parse_invoice_text(sample_text)

        self.assertEqual(result["montant_ttc"], 5000.0)


if __name__ == '__main__':
    unittest.main()

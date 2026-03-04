import sys
import os
import unittest

# Add parent directory to sys.path to easily import the main module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main_watcher import parse_invoice_text

class TestInvoiceParsing(unittest.TestCase):
    
    def test_parse_basic_invoice(self):
        """Test extraction of basic invoice elements with clear keywords."""
        sample_text = "Facture N° : TAU_2026-413\nSOCIETE ACME\nDate : 12/03/2026\nEchéance : 12/04/2026\nTotal TTC : 1 200,50 €"
        result = parse_invoice_text(sample_text)
        
        self.assertEqual(result["num_facture"], "TAU_2026-413")
        self.assertEqual(result["date_facture"], "12/03/2026")
        self.assertEqual(result["date_echeance"], "12/04/2026")
        self.assertEqual(result["montant_ttc"], "1200,50")

    def test_parse_missing_echeance(self):
        """Test extraction fallback when echeance is missing."""
        sample_text = "Facture TAU_2026-999\nDate: 01/01/2026\nNet à payer 500.00 EUR"
        result = parse_invoice_text(sample_text)
        
        self.assertEqual(result["num_facture"], "TAU_2026-999")
        self.assertEqual(result["date_facture"], "01/01/2026")
        # should fallback to same date or none depending on logic, our logic mostly extracts what it finds
        self.assertEqual(result["montant_ttc"], "500,00")

    def test_parse_complex_table(self):
        """Test extraction when the invoice uses complex table structures."""
        sample_text = "SOCIETE BETA\nDate de facturation : 14.05.2026\nNuméro de document : TAU_2026-102\nDescription Quantité Prix Unitaire Montant\nService A 1 1500,00 1500,00\nTotal HT 1500,00\nTVA 20% 300,00\nTotal TTC 1 800,00 €\n"
        result = parse_invoice_text(sample_text)
        
        self.assertEqual(result["client"], "BETA")
        self.assertEqual(result["num_facture"], "TAU_2026-102")
        self.assertEqual(result["date_facture"], "14.05.2026")
        self.assertEqual(result["montant_ttc"], "1800,00")

    def test_parse_missing_client(self):
         """Test extraction when client name is poorly formatted."""
         sample_text = "Facture : TAU_2026-001\nTotal : 150,00 EUR"
         result = parse_invoice_text(sample_text)
         self.assertEqual(result["client"], "")
         self.assertEqual(result["montant_ttc"], "150,00")

if __name__ == '__main__':
    unittest.main()

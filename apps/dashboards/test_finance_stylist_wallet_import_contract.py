from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[2]


class FinanceStylistWalletImportContractTests(unittest.TestCase):
    def test_stylist_wallet_view_model_dependencies_are_imported(self):
        path = ROOT / "apps/dashboards/finance_cost_views.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        imported = set()
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    imported.add(alias.asname or alias.name.split(".")[0])

        required = {
            "Stylist",
            "StylistWalletTransaction",
            "StylistWalletWithdrawalRequest",
        }
        self.assertTrue(required.issubset(imported), required - imported)

        view_block = source.split("class SalonStylistWalletsView", 1)[1].split(
            "class ManagerFinalizeAppointmentFinanceView", 1
        )[0]
        for name in required:
            self.assertIn(name, view_block)


if __name__ == "__main__":
    unittest.main(verbosity=2)

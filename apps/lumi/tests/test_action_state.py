from __future__ import annotations

import unittest

from apps.lumi.schemas.actions import ActionProposal, ActionState


class ActionProposalTests(unittest.TestCase):
    def test_confirmation_state_machine(self):
        proposal = ActionProposal(
            tool_name="cancel_booking",
            target="ORD-1",
            effect="cancel",
            requires_confirmation=True,
        )
        self.assertEqual(proposal.state, ActionState.PROPOSED)
        with self.assertRaises(ValueError):
            proposal.mark_executed()
        proposal.confirm()
        self.assertEqual(proposal.state, ActionState.CONFIRMED)
        proposal.mark_executed()
        self.assertEqual(proposal.state, ActionState.EXECUTED)


    def test_explain_action_is_structured(self):
        proposal = ActionProposal(
            tool_name="prepare_booking",
            target="slot:1",
            effect="prepare checkout",
            requires_confirmation=True,
            preview={"price": 320000},
        )
        explanation = proposal.explain()
        self.assertEqual(explanation["action"], "prepare_booking")
        self.assertEqual(explanation["state"], "proposed")
        self.assertTrue(explanation["requires_confirmation"])
        self.assertEqual(explanation["preview"]["price"], 320000)

    def test_failure_state(self):
        proposal = ActionProposal(tool_name="prepare_booking")
        proposal.mark_failed("slot changed")
        self.assertEqual(proposal.state, ActionState.FAILED)
        self.assertEqual(proposal.error, "slot changed")


if __name__ == "__main__":
    unittest.main()

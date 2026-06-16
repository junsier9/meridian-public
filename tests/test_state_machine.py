from __future__ import annotations

import unittest

from tests.test_helpers import make_research_object

from enhengclaw.core.enums import ProcessingState
from enhengclaw.core.state_machine import StateMachine


class StateMachineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.machine = StateMachine()

    def test_valid_processing_transitions_across_cycles(self) -> None:
        research_object = make_research_object(processing_state=ProcessingState.CANDIDATE)

        self.machine.begin_cycle(research_object)
        self.machine.transition_processing(research_object, ProcessingState.SCREENED)
        self.assertEqual(research_object.processing_state, ProcessingState.SCREENED)

        self.machine.begin_cycle(research_object)
        self.machine.transition_processing(research_object, ProcessingState.ACTIVE_RESEARCH)
        self.assertEqual(research_object.processing_state, ProcessingState.ACTIVE_RESEARCH)

    def test_invalid_processing_jump_raises(self) -> None:
        research_object = make_research_object(processing_state=ProcessingState.CANDIDATE)
        self.machine.begin_cycle(research_object)

        with self.assertRaises(ValueError):
            self.machine.transition_processing(research_object, ProcessingState.EVIDENCE_COMPLETE)

    def test_multiple_forward_transitions_in_one_cycle_raise(self) -> None:
        research_object = make_research_object(processing_state=ProcessingState.CANDIDATE)
        self.machine.begin_cycle(research_object)
        self.machine.transition_processing(research_object, ProcessingState.SCREENED)

        with self.assertRaises(ValueError):
            self.machine.transition_processing(research_object, ProcessingState.ACTIVE_RESEARCH)

    def test_blocked_exception_path_is_allowed_in_same_cycle(self) -> None:
        research_object = make_research_object(processing_state=ProcessingState.CANDIDATE)
        self.machine.begin_cycle(research_object)
        self.machine.transition_processing(research_object, ProcessingState.SCREENED)
        self.machine.transition_processing(research_object, ProcessingState.BLOCKED)
        self.assertEqual(research_object.processing_state, ProcessingState.BLOCKED)

    def test_published_to_blocked_is_allowed(self) -> None:
        research_object = make_research_object(processing_state=ProcessingState.PUBLISHED)
        self.machine.begin_cycle(research_object)
        self.machine.transition_processing(research_object, ProcessingState.BLOCKED)
        self.assertEqual(research_object.processing_state, ProcessingState.BLOCKED)


if __name__ == "__main__":
    unittest.main()

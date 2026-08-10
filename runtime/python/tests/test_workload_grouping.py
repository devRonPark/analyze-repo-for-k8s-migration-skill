import unittest

from analysis_pipeline.validation import derive_runtime_process_id
from analysis_pipeline.workload_grouping import resolve_workload_grouping, validate_workload_grouping


class WorkloadGroupingTests(unittest.TestCase):
    @staticmethod
    def d03_web_process() -> dict:
        identity = {
            "candidate_ids": ["candidate-jpetstore-web"],
            "role": "web",
            "execution_pattern": "continuous",
            "semantic_fact_refs": [],
        }
        return {"id": derive_runtime_process_id(identity), **identity}

    def test_single_d03_process_deterministically_forms_one_group(self) -> None:
        process = self.d03_web_process()

        grouping = resolve_workload_grouping([process])

        self.assertEqual(grouping["input_process_ids"], [process["id"]])
        self.assertEqual(grouping["groups"], [{
            "unit_id": "unit_9686120c2844a96b71718eac",
            "process_ids": [process["id"]],
            "candidate_ids": ["candidate-jpetstore-web"],
        }])

    def test_grouping_is_stable_and_preserves_d03_process_semantics(self) -> None:
        process = self.d03_web_process()

        first = resolve_workload_grouping([process])
        second = resolve_workload_grouping([dict(process)])

        self.assertEqual(first, second)
        self.assertEqual(first["groups"][0]["candidate_ids"], process["candidate_ids"])

    def test_grouping_rejects_a_forged_d03_process_id(self) -> None:
        process = self.d03_web_process() | {"id": "process-client-supplied"}

        with self.assertRaisesRegex(ValueError, "forged runtime process id"):
            resolve_workload_grouping([process])

    def test_single_process_is_a_deterministic_group(self) -> None:
        deterministic = validate_workload_grouping(
            ["process-web"], [{"unit_id": "unit-web", "process_ids": ["process-web"]}]
        )

        self.assertEqual(deterministic, {"unit-web"})

    def test_rejects_a_missing_process(self) -> None:
        with self.assertRaises(ValueError):
            validate_workload_grouping(
                ["process-a", "process-b"],
                [{"unit_id": "unit-a", "process_ids": ["process-a"]}],
            )

    def test_rejects_a_duplicate_process_across_groups(self) -> None:
        with self.assertRaises(ValueError):
            validate_workload_grouping(
                ["process-a"],
                [
                    {"unit_id": "unit-a", "process_ids": ["process-a"]},
                    {"unit_id": "unit-a2", "process_ids": ["process-a"]},
                ],
            )

    def test_rejects_a_dangling_process_not_in_the_accepted_input(self) -> None:
        with self.assertRaises(ValueError):
            validate_workload_grouping(
                ["process-web"],
                [{"unit_id": "unit-web", "process_ids": ["process-web", "process-missing"]}],
            )

    def test_multi_process_split_is_not_deterministic(self) -> None:
        """Each leg of a split is alone in its own group, but the split itself
        still needs comparative lifecycle evidence -- being alone in a group
        is not the same as being the only accepted process."""
        deterministic = validate_workload_grouping(
            ["process-web", "process-worker"],
            [
                {"unit_id": "unit-web", "process_ids": ["process-web"]},
                {"unit_id": "unit-worker", "process_ids": ["process-worker"]},
            ],
        )

        self.assertEqual(deterministic, set())

    def test_multi_process_merge_into_one_group_is_not_deterministic(self) -> None:
        deterministic = validate_workload_grouping(
            ["process-web", "process-worker"],
            [{"unit_id": "unit-web", "process_ids": ["process-web", "process-worker"]}],
        )

        self.assertEqual(deterministic, set())


if __name__ == "__main__":
    unittest.main()

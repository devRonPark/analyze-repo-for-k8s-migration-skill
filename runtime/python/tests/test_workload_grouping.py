import unittest

from analysis_pipeline.workload_grouping import validate_workload_grouping


class WorkloadGroupingTests(unittest.TestCase):
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

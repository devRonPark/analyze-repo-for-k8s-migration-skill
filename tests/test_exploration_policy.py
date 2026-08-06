"""Lock the declarative Kubernetes migration exploration registry (Task 1).

The registry only ranks where to look and what to search for. It must never
carry resolved domain values (ports, images, commands), must degrade to an
empty rule set for any question or ecosystem it does not know about, and
must keep every language-specific hint in this one module.
"""

from __future__ import annotations

import dataclasses
import unittest

from migration_assistant.exploration_policy import (
    DEFAULT_MIGRATION_POLICY,
    ExplorationPolicy,
    ExplorationQuestion,
    QuestionImportance,
    SignalRule,
    match_rules,
)


def _field_names(obj: object) -> set[str]:
    return {field.name for field in dataclasses.fields(obj)}


class ExplorationPolicyTests(unittest.TestCase):
    def test_policy_prioritizes_startup_signals_without_creating_values(self):
        rules = DEFAULT_MIGRATION_POLICY.rules_for("production_startup")
        self.assertEqual(rules[0].priority, 10)
        self.assertIn("Dockerfile*", rules[0].file_globs)
        # SignalRule uses __slots__ (no __dict__); field names are the contract surface instead.
        self.assertNotIn("port_value", _field_names(rules[0]))

    def test_signal_rule_carries_no_resolved_value_fields(self):
        for rule in DEFAULT_MIGRATION_POLICY.rules:
            for forbidden in ("value", "port", "image", "workload", "environment_variable", "service"):
                self.assertNotIn(forbidden, _field_names(rule))

    def test_rules_are_ordered_by_descending_priority(self):
        rules = DEFAULT_MIGRATION_POLICY.rules_for("receiving_port")
        priorities = [rule.priority for rule in rules]
        self.assertEqual(priorities, sorted(priorities, reverse=True))

    def test_unknown_question_id_returns_empty_rules_not_an_error(self):
        self.assertEqual(DEFAULT_MIGRATION_POLICY.rules_for("no_such_question"), ())

    def test_removing_a_registry_entry_still_falls_back_to_empty_rules(self):
        trimmed = ExplorationPolicy(questions=DEFAULT_MIGRATION_POLICY.questions, rules=())
        self.assertEqual(trimmed.rules_for("production_startup"), ())

    def test_every_default_question_has_a_fixed_importance(self):
        for question in DEFAULT_MIGRATION_POLICY.questions:
            self.assertIn(question.importance, (QuestionImportance.REQUIRED, QuestionImportance.CONDITIONAL, QuestionImportance.OPTIONAL))

    def test_default_question_ids_match_the_task0_contract(self):
        self.assertEqual(
            DEFAULT_MIGRATION_POLICY.question_ids(),
            (
                "workload_deployment_unit",
                "production_startup",
                "build_stage",
                "receiving_port",
                "runtime_config_and_secret_names",
                "external_dependency",
                "writable_state_path",
            ),
        )

    def test_conditional_question_declares_its_precondition_question(self):
        question = DEFAULT_MIGRATION_POLICY.question("external_dependency")
        self.assertEqual(question.importance, QuestionImportance.CONDITIONAL)
        self.assertIsNotNone(question.depends_on_question_id)

    def test_question_lookup_returns_none_for_unknown_id(self):
        self.assertIsNone(DEFAULT_MIGRATION_POLICY.question("no_such_question"))

    def test_signal_rule_is_immutable(self):
        rule = DEFAULT_MIGRATION_POLICY.rules[0]
        with self.assertRaises(AttributeError):
            rule.priority = 999  # type: ignore[misc]

    def test_exploration_question_is_immutable(self):
        question = DEFAULT_MIGRATION_POLICY.questions[0]
        with self.assertRaises(AttributeError):
            question.importance = QuestionImportance.OPTIONAL  # type: ignore[misc]

    def test_match_rules_matches_observed_dockerfile_path(self):
        rules = match_rules(DEFAULT_MIGRATION_POLICY, path="Dockerfile")
        self.assertTrue(rules)
        self.assertIn("production_startup", rules[0].question_ids)

    def test_match_rules_matches_observed_text_pattern(self):
        rules = match_rules(DEFAULT_MIGRATION_POLICY, text="ENTRYPOINT [\"python\", \"app.py\"]")
        self.assertTrue(rules)
        self.assertIn("production_startup", rules[0].question_ids)

    def test_match_rules_returns_empty_for_unrelated_observation(self):
        self.assertEqual(match_rules(DEFAULT_MIGRATION_POLICY, path="README.md", text="hello world"), ())

    def test_match_rules_never_guesses_from_absent_input(self):
        self.assertEqual(match_rules(DEFAULT_MIGRATION_POLICY), ())

    def test_generic_main_substring_no_longer_false_positives_on_pom_xml(self):
        """A live jpetstore-6 smoke found this exact false positive: Maven's
        own repository URL for a GlassFish distribution contains the
        substring "main" (org/glassfish/main/...), which used to match
        build_or_package_manifest even though it has nothing to do with a
        Java main class or entrypoint."""

        # path is deliberately omitted: pom.xml is always a legitimate build
        # manifest via file_globs regardless of content, so this isolates
        # whether the *text* alone (unrelated to any specific file) still
        # false-positives on the bare "main" substring.
        text = (
            "<cargo.maven.containerUrl>https://repo.maven.apache.org/maven2/"
            "org/glassfish/main/distributions/glassfish/1.0/glassfish-1.0.zip</cargo.maven.containerUrl>"
        )
        rules = match_rules(DEFAULT_MIGRATION_POLICY, text=text)
        matched_keys = {rule.key for rule in rules}
        self.assertNotIn("build_or_package_manifest", matched_keys)

    def test_maven_packaging_and_plugin_signals_are_recognized(self):
        for text in (
            "<packaging>war</packaging>",
            "<artifactId>maven-war-plugin</artifactId>",
            "<artifactId>spring-boot-maven-plugin</artifactId>",
            "<mainClass>com.example.Application</mainClass>",
            "<parent><groupId>org.springframework.boot</groupId></parent>",
        ):
            with self.subTest(text=text):
                rules = match_rules(DEFAULT_MIGRATION_POLICY, text=text)
                matched_keys = {rule.key for rule in rules}
                self.assertIn("build_or_package_manifest", matched_keys)

    def test_spring_xml_context_files_match_config_descriptor_rule(self):
        for path in ("src/main/webapp/WEB-INF/applicationContext.xml", "web.xml", "service-context.xml"):
            with self.subTest(path=path):
                rules = match_rules(DEFAULT_MIGRATION_POLICY, path=path)
                matched_keys = {rule.key for rule in rules}
                self.assertIn("config_and_deployment_descriptor", matched_keys)

    def test_spring_datasource_signals_are_recognized(self):
        for text in ("<jdbc:embedded-database>", "class=\"org.springframework.jdbc.datasource.DriverManagerDataSource\""):
            with self.subTest(text=text):
                rules = match_rules(DEFAULT_MIGRATION_POLICY, text=text)
                matched_keys = {rule.key for rule in rules}
                self.assertIn("config_and_deployment_descriptor", matched_keys)


if __name__ == "__main__":
    unittest.main()

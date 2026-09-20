"""Keep runner selection live while preserving existing companion callers."""
import copy
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ("companion-canary.yml", "companion-core-bump.yml")


def runner_errors(workflow):
    # PyYAML's YAML 1.1 loader reads the GitHub `on` key as True.
    trigger = workflow.get("on", workflow.get(True, {}))
    runner = trigger.get("workflow_call", {}).get("inputs", {}).get("runner", {})
    errors = []
    if runner.get("type") != "string" or runner.get("default") != "macos-15":
        errors.append("runner must preserve the existing macos-15 string default")
    if runner.get("required") is not False:
        errors.append("runner must remain optional for existing callers")
    jobs = workflow.get("jobs", {})
    if not jobs:
        errors.append("workflow has no executable jobs")
    for name, job in jobs.items():
        if job.get("runs-on") != "${{ inputs.runner }}":
            errors.append(f"{name} does not execute on the requested runner")
    return errors


class CompanionRunnerInputsTests(unittest.TestCase):
    def workflows(self):
        for name in WORKFLOWS:
            with (ROOT / ".github" / "workflows" / name).open() as source:
                yield name, yaml.safe_load(source)

    def test_runner_input_drives_every_job(self):
        for name, workflow in self.workflows():
            with self.subTest(workflow=name):
                self.assertEqual(runner_errors(workflow), [])

    def test_sabotage_hardcoded_runner_is_rejected(self):
        for name, workflow in self.workflows():
            broken = copy.deepcopy(workflow)
            next(iter(broken["jobs"].values()))["runs-on"] = "macos-15"
            with self.subTest(workflow=name):
                self.assertTrue(runner_errors(broken))

    def test_sabotage_missing_input_is_rejected(self):
        for name, workflow in self.workflows():
            broken = copy.deepcopy(workflow)
            trigger = broken.get("on", broken.get(True))
            del trigger["workflow_call"]["inputs"]["runner"]
            with self.subTest(workflow=name):
                self.assertTrue(runner_errors(broken))

    def test_empty_workflow_is_rejected(self):
        self.assertTrue(runner_errors({}))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hermes_jobapps import cli, plugin
from hermes_jobapps.workspace import Workspace


REPO = Path(__file__).resolve().parents[1]


class FakeContext:
    def __init__(self) -> None:
        self.tools: dict[str, dict] = {}
        self.commands: dict[str, dict] = {}
        self.skills: dict[str, dict] = {}
        self.sections: dict[str, object] = {}
        self.blueprints: list[dict] = []
        self.settings: dict[str, str] = {}

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_tool(self, name, toolset, schema, handler, **extra):
        self.tools[name] = {"toolset": toolset, "schema": schema, "handler": handler, **extra}

    def register_command(self, name, handler, description="", args_hint=""):
        self.commands[name] = {"handler": handler, "description": description, "args_hint": args_hint}

    def register_skill(self, name, path, description="", frontmatter=None):
        self.skills[name] = {"path": Path(path), "description": description}

    def register_system_prompt_section(self, section_id, content, **extra):
        self.sections[section_id] = content

    def register_automation_blueprint(self, key, **fields):
        self.blueprints.append({"key": key, **fields})


class PluginCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "ws"
        self.ws = Workspace(self.root)
        self.ws.init(name="Jordan Example")
        self.env = patch.dict(os.environ, {"JOBAPPS_HOME": str(self.root)})
        self.env.start()
        plugin._workspaces.clear()
        plugin._configured_root = lambda: ""

    def tearDown(self) -> None:
        self.env.stop()
        plugin._workspaces.clear()
        plugin._configured_root = lambda: ""
        self.tmp.cleanup()

    def call(self, tool: str, **args):
        return json.loads(plugin.run_tool(tool, args))


class RegistrationTests(PluginCase):
    def test_manifest_declares_exactly_the_registered_tools(self) -> None:
        ctx = FakeContext()
        plugin.register(ctx)
        manifest = (REPO / "plugin.yaml").read_text(encoding="utf-8")
        declared = [
            line.strip()[2:]
            for line in manifest.split("provides_tools:")[1].split("provides_hooks:")[0].splitlines()
            if line.strip().startswith("- ")
        ]
        self.assertEqual(sorted(declared), sorted(ctx.tools))
        self.assertEqual({tool["toolset"] for tool in ctx.tools.values()}, {"jobapps"})

    def test_schemas_are_small_closed_json_schema_objects(self) -> None:
        total = 0
        for tool in plugin.TOOLS:
            schema = plugin.tool_schema(tool)
            total += len(json.dumps(schema))
            parameters = schema["parameters"]
            self.assertEqual(parameters["type"], "object")
            self.assertIs(parameters["additionalProperties"], False)
            self.assertTrue(set(parameters["required"]) <= set(parameters["properties"]))
            self.assertLessEqual(len(schema["description"]), 420, schema["name"])
            for name, spec in parameters["properties"].items():
                self.assertIn("type", spec, f"{schema['name']}.{name}")
        self.assertLess(total, 9000)

    def test_skills_register_with_index_ready_descriptions(self) -> None:
        ctx = FakeContext()
        plugin.register(ctx)
        self.assertIn("jobapps", ctx.skills)
        self.assertGreaterEqual(len(ctx.skills), 6)
        for name, skill in ctx.skills.items():
            self.assertTrue(skill["path"].is_file(), name)
            self.assertTrue(skill["description"], name)
            self.assertGreaterEqual(len(skill["description"]), 20, name)

    def test_prompt_section_names_the_workspace_and_the_entry_skill(self) -> None:
        ctx = FakeContext()
        plugin.register(ctx)
        text = ctx.sections["jobapps.workspace"]({})
        self.assertIn(str(self.root), text)
        self.assertIn("jobapps:jobapps", text)
        self.assertLess(len(text), 400)

    def test_configured_workspace_wins_over_the_environment(self) -> None:
        other = Path(self.tmp.name) / "other"
        ctx = FakeContext()
        ctx.settings["workspace"] = str(other)
        plugin.register(ctx)
        self.assertEqual(plugin.workspace().root, other)

    def test_blueprints_recommend_and_never_act(self) -> None:
        ctx = FakeContext()
        plugin.register(ctx)
        self.assertEqual({item["key"] for item in ctx.blueprints}, {"daily-brief", "lead-scan", "weekly-review"})
        for item in ctx.blueprints:
            self.assertRegex(item["prompt_template"], "send nothing|Apply to nothing")
            self.assertTrue(item["schedule_template"].count(" ") == 4)

    def test_older_hermes_without_optional_registrars_still_loads(self) -> None:
        class OldContext:
            def __init__(self) -> None:
                self.tools: list[str] = []
                self.skills: list[str] = []

            def register_tool(self, name, toolset, schema, handler, **extra):
                self.tools.append(name)

            def register_command(self, name, handler, description="", args_hint=""):
                pass

            def register_skill(self, name, path):
                self.skills.append(name)

        ctx = OldContext()
        plugin.register(ctx)
        self.assertEqual(len(ctx.tools), len(plugin.TOOLS))
        self.assertIn("jobapps", ctx.skills)


class ToolTests(PluginCase):
    def test_handlers_return_compact_json_strings(self) -> None:
        ctx = FakeContext()
        plugin.register(ctx)
        self.ws.create_job(company="Northstar", title="AI Engineer")
        raw = ctx.tools["jobapps_overview"]["handler"]({"view": "jobs"}, task_id="t1", session_id="s1")
        self.assertIsInstance(raw, str)
        self.assertNotIn("\n", raw)
        self.assertEqual(json.loads(raw)["jobs"][0]["company"], "Northstar")

    def test_errors_are_answers_not_exceptions(self) -> None:
        self.ws.create_job(company="Northstar", title="AI Engineer")
        self.ws.create_job(company="Northstar", title="Data Engineer")
        self.assertIn("Missing required argument: job", self.call("jobapps_brief")["error"])
        self.assertIn("matches", self.call("jobapps_track", job="northstar", note="x"))
        self.assertIn("error", self.call("jobapps_brief", job="nobody-here"))
        self.assertIn("must be one of", self.call("jobapps_overview", view="jobs", stage="bogus")["error"])
        self.assertIn("Unknown tool", json.loads(plugin.run_tool("jobapps_nope", {}))["error"])
        self.assertIn("error", json.loads(plugin.run_tool("jobapps_overview", None)) | {"error": ""})

    def test_track_and_person_round_trip(self) -> None:
        job = self.ws.create_job(company="Fieldwork", title="Data Engineer")
        done = self.call("jobapps_track", job=job["id"], status="applied", note="Sent on the site.")
        self.assertTrue(done["ok"])
        self.assertEqual(done["job"]["stage"], "applied")
        saved = self.call("jobapps_person", name="Jamie Chen", why="Hiring manager for the role.", job=job["id"])
        self.assertTrue(saved["created"])
        self.assertEqual(self.ws.people()[0]["jobs"], [job["id"]])

    def test_slash_command_is_plain_text(self) -> None:
        self.ws.create_job(company="Northstar", title="AI Engineer", status="applied")
        text = plugin.slash_command("jobs north", session_id="s1", platform="cli")
        self.assertIn("Northstar: AI Engineer", text)
        self.assertNotIn("{", text)
        self.assertIn("applied 1", plugin.slash_command(""))
        self.assertIn("Sent 1", plugin.slash_command("stats"))


class CliTests(PluginCase):
    def run_cli(self, *argv: str) -> tuple[int, str]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            code = cli.main(["--workspace", str(self.root), *argv])
        return code, buffer.getvalue()

    def test_init_status_and_doctor(self) -> None:
        fresh = Path(self.tmp.name) / "fresh"
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(cli.main(["--workspace", str(fresh), "init", "--name", "Jordan Example"]), 0)
        self.assertTrue((fresh / "profile" / "profile.md").is_file())

        self.ws.create_job(company="Northstar", title="AI Engineer")
        code, output = self.run_cli("status", "jobs")
        self.assertEqual(code, 0)
        self.assertIn("Northstar", output)
        code, output = self.run_cli("status", "--json")
        self.assertEqual(json.loads(output)["counts"]["new"], 1)
        code, output = self.run_cli("doctor", "--json")
        report = json.loads(output)
        self.assertEqual(report["workspace"]["jobs"], 1)
        self.assertIn("typst", report["tools"])

    def test_bad_input_exits_with_a_message(self) -> None:
        code, output = self.run_cli("migrate", str(Path(self.tmp.name) / "missing.sqlite3"))
        self.assertEqual(code, 2)
        self.assertIn("error:", output)


if __name__ == "__main__":
    unittest.main()

import runpy
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


LAUNCHER = Path(__file__).parents[1] / "src" / "insightclass" / "web" / "launcher.pyw"


class LauncherTests(unittest.TestCase):
    def test_brand_assets_are_resolvable_from_source_layout(self):
        namespace = runpy.run_path(str(LAUNCHER))
        resource_path = namespace["_resource_path"]
        self.assertTrue(resource_path("assets", "insightclass.ico").is_file())
        self.assertTrue(resource_path("assets", "insightclass-tray.png").is_file())
        self.assertIn('class="logo"', namespace["_LOADING_HTML"])

    def test_activation_server_wakes_existing_instance(self):
        namespace = runpy.run_path(str(LAUNCHER))
        ActivationServer = namespace["ActivationServer"]
        send_activation = namespace["_send_activation"]
        launcher_globals = ActivationServer.__init__.__globals__
        events = []
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir)
            with patch.dict(launcher_globals, {"_config_dir": lambda: config_dir}):
                server = ActivationServer(lambda: events.append("show"))
                port = server.start()
                try:
                    self.assertTrue(send_activation(port))
                    self.assertEqual(events, ["show"])
                finally:
                    server.stop()
            self.assertFalse((config_dir / ".control").exists())

    def test_background_services_start_after_webview_gui_loop(self):
        namespace = runpy.run_path(str(LAUNCHER))
        launcher_globals = namespace["main"].__globals__
        events = []

        class EventHook:
            def __iadd__(self, callback):
                self.callback = callback
                return self

        class FakeWindow:
            def __init__(self):
                self.events = types.SimpleNamespace(closing=EventHook())

            def destroy(self):
                events.append("destroy")

        fake_window = FakeWindow()

        class FakeWebview:
            @staticmethod
            def create_window(*_args, **_kwargs):
                events.append("create-window")
                return fake_window

            @staticmethod
            def start(func=None, **_kwargs):
                events.append("webview-start")
                func()

        class FakeActivation:
            def __init__(self, _on_show):
                pass

            def start(self):
                events.append("activation-start")

            def stop(self):
                events.append("activation-stop")

        class FakeTray:
            def __init__(self, _on_show, _on_exit):
                pass

            def start(self):
                events.append("tray-start")

            def stop(self):
                events.append("tray-stop")

        class FakeThread:
            def __init__(self, **kwargs):
                self.name = kwargs["name"]

            def start(self):
                events.append(self.name)

        replacements = {
            "_read_port": lambda _name: None,
            "_write_port": lambda _name, _port: None,
            "_remove_port": lambda _name, _port: None,
            "_find_available_port": lambda _preferred: 8123,
            "_resource_path": lambda *_parts: Path("icon.ico"),
            "_config_dir": lambda: Path("configs"),
            "ActivationServer": FakeActivation,
            "TrayController": FakeTray,
            "threading": types.SimpleNamespace(Thread=FakeThread),
        }
        with (
            patch.dict(launcher_globals, replacements),
            patch.dict(sys.modules, {"webview": FakeWebview}),
        ):
            namespace["main"]()

        self.assertLess(events.index("webview-start"), events.index("tray-start"))
        self.assertLess(
            events.index("webview-start"), events.index("insightclass-server-start")
        )


if __name__ == "__main__":
    unittest.main()

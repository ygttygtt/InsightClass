import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


LAUNCHER = Path(__file__).parents[1] / "src" / "insightclass" / "web" / "launcher.pyw"


class LauncherTests(unittest.TestCase):
    def test_activation_server_wakes_existing_instance(self):
        namespace = runpy.run_path(str(LAUNCHER))
        ActivationServer = namespace["ActivationServer"]
        send_activation = namespace["_send_activation"]
        events = []
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir)
            with patch.dict(namespace, {"_config_dir": lambda: config_dir}):
                server = ActivationServer(lambda: events.append("show"))
                port = server.start()
                try:
                    self.assertTrue(send_activation(port))
                    self.assertEqual(events, ["show"])
                finally:
                    server.stop()
            self.assertFalse((config_dir / ".control").exists())


if __name__ == "__main__":
    unittest.main()

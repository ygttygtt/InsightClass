import unittest

from insightclass.cli import build_parser


class CliTests(unittest.TestCase):
    def test_build_parser_without_optional_dependencies(self):
        parser = build_parser()
        self.assertIsNotNone(parser)


if __name__ == "__main__":
    unittest.main()

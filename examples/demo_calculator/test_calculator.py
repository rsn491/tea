#!/usr/bin/env python3
"""
Test suite for the calculator module.
"""

import unittest
from unittest.mock import patch
from io import StringIO

from calculator import sum_numbers, help, main


class TestCalculator(unittest.TestCase):

    def test_sum_numbers_basic(self):
        result = sum_numbers("1", "2", "3")
        self.assertEqual(result, 6.0)

    def test_sum_numbers_single_number(self):
        result = sum_numbers("42")
        self.assertEqual(result, 42.0)

    def test_sum_numbers_decimals(self):
        result = sum_numbers("3.5", "2.7", "1.8")
        self.assertEqual(result, 8.0)

    def test_sum_numbers_mixed_types(self):
        result = sum_numbers("10", "20.5", "5")
        self.assertEqual(result, 35.5)

    def test_sum_numbers_large_numbers(self):
        result = sum_numbers("1000000", "2000000", "3000000")
        self.assertEqual(result, 6000000.0)

    def test_sum_numbers_negative_numbers(self):
        result = sum_numbers("-5", "10", "-3")
        self.assertEqual(result, 2.0)

    def test_sum_numbers_zero(self):
        result = sum_numbers("0", "5", "0")
        self.assertEqual(result, 5.0)

    def test_sum_numbers_no_arguments(self):
        with self.assertRaises(ValueError) as context:
            sum_numbers()
        self.assertEqual(str(context.exception), "At least one number is required for sum operation")

    def test_sum_numbers_invalid_input(self):
        with self.assertRaises(ValueError) as context:
            sum_numbers("1", "2", "invalid")
        self.assertEqual(str(context.exception), "Invalid number: invalid")

    def test_sum_numbers_scientific_notation(self):
        result = sum_numbers("1e3", "2e2")
        self.assertEqual(result, 1200.0)

    @patch('sys.stdout', new_callable=StringIO)
    def test_help_function(self, mock_stdout):
        help()
        output = mock_stdout.getvalue()
        self.assertIn("Calculator - A simple command-line calculator", output)
        self.assertIn("USAGE:", output)
        self.assertIn("EXAMPLES:", output)

    def test_main_help_command(self):
        with patch('sys.argv', ['calculator.py', 'help']):
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                main()
                output = mock_stdout.getvalue()
                self.assertIn("Calculator - A simple command-line calculator", output)

    def test_main_sum_command(self):
        with patch('sys.argv', ['calculator.py', 'sum', '1', '2', '3']):
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                main()
                output = mock_stdout.getvalue()
                self.assertEqual(output.strip(), "Result: 6.0")

    def test_main_no_arguments(self):
        with patch('sys.argv', ['calculator.py']):
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                with self.assertRaises(SystemExit):
                    main()
                output = mock_stdout.getvalue()
                self.assertIn("Error: No operation specified.", output)

    def test_main_sum_no_numbers(self):
        with patch('sys.argv', ['calculator.py', 'sum']):
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                with self.assertRaises(SystemExit):
                    main()
                output = mock_stdout.getvalue()
                self.assertIn("Error: At least one number is required", output)

    def test_main_unknown_operation(self):
        with patch('sys.argv', ['calculator.py', 'unknown']):
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                with self.assertRaises(SystemExit):
                    main()
                output = mock_stdout.getvalue()
                self.assertIn("Error: Unknown operation 'unknown'", output)


if __name__ == '__main__':
    unittest.main()

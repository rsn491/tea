#!/usr/bin/env python3
"""
Calculator main script that supports sums with infinite space-separated parameters.
"""

import sys


def help():
    """Display help information about how to use the calculator."""
    help_text = """
Calculator - A simple command-line calculator for summing numbers

USAGE:
    python calculator.py sum <number1> <number2> <number3> ...

DESCRIPTION:
    This calculator supports summing an infinite number of parameters.
    Parameters should be separated by spaces, not commas.

EXAMPLES:
    python calculator.py sum 1 2 3
    Result: 6

    python calculator.py sum 10 20 30 40 50
    Result: 150

    python calculator.py sum 3.5 2.7 1.8
    Result: 8.0

    python calculator.py help
    Show this help message

SUPPORTED OPERATIONS:
    sum - Add all provided numbers together

NOTES:
    - Numbers can be integers or decimals
    - At least one number is required for the sum operation
    - Invalid numbers will cause an error
"""
    print(help_text)


def sum_numbers(*args):
    """
    Sum an infinite number of parameters.

    Args:
        *args: Variable number of numeric arguments to sum

    Returns:
        float: The sum of all numbers
    """
    if not args:
        raise ValueError("At least one number is required for sum operation")

    total = 0
    for num_str in args:
        try:
            num = float(num_str)
            total += num
        except ValueError:
            raise ValueError(f"Invalid number: {num_str}")

    return total


def main():
    """Main function to handle command line arguments."""
    if len(sys.argv) < 2:
        print("Error: No operation specified.")
        help()
        sys.exit(1)

    operation = sys.argv[1].lower()

    if operation == "help":
        help()
    elif operation == "sum":
        if len(sys.argv) < 3:
            print("Error: At least one number is required for sum operation.")
            help()
            sys.exit(1)

        numbers = sys.argv[2:]
        try:
            result = sum_numbers(*numbers)
            print(f"Result: {result}")
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
    else:
        print(f"Error: Unknown operation '{operation}'")
        help()
        sys.exit(1)


if __name__ == "__main__":
    main()

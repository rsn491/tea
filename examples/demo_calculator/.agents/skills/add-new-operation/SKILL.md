---
description: How to add a new mathematical operation to the calculator application
---

# Add New Operation to Calculator

Guide for adding new mathematical operations to the calculator with consistent error handling, testing, and documentation.

## Files to Modify

- `calculator.py` - Main application logic
- `test_calculator.py` - Unit tests  
- `README.md` - Documentation

## Implementation Steps

### 1. Add Operation Function

- [ ] Add function in `calculator.py` following the `sum_numbers()` pattern:

```python
def multiply_numbers(*args):
    """Multiply an infinite number of parameters."""
    if not args:
        raise ValueError("At least one number is required for multiply operation")
    
    result = 1
    for num_str in args:
        try:
            num = float(num_str)
            result *= num
        except ValueError:
            raise ValueError(f"Invalid number: {num_str}")
    
    return result
```

- [ ] Validate input parameters (check for empty args)
- [ ] Convert all inputs to float for consistency
- [ ] Raise descriptive ValueError for invalid inputs
- [ ] Return float result

### 2. Update Help Documentation

- [ ] Update `help()` function in `calculator.py`:

```python
def help():
    help_text = """
SUPPORTED OPERATIONS:
    sum - Add all provided numbers together
    multiply - Multiply all provided numbers together
"""
```

- [ ] Add usage example for the new operation
- [ ] Update supported operations list

### 3. Update Main Function

- [ ] Add operation handling in `main()`:

```python
elif operation == "multiply":
    if len(sys.argv) < 3:
        print("Error: At least one number is required for multiply operation.")
        help()
        sys.exit(1)
    
    numbers = sys.argv[2:]
    try:
        result = multiply_numbers(*numbers)
        print(f"Result: {result}")
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
```

- [ ] Use `.lower()` for case-insensitive matching
- [ ] Handle missing numbers error
- [ ] Wrap function call in try/except

### 4. Add Unit Tests

- [ ] Update import in `test_calculator.py`:
  `from calculator import sum_numbers, multiply_numbers, help, main`

- [ ] Add function tests:
  - `test_multiply_numbers_basic()` - Test with integers
  - `test_multiply_numbers_single_number()` - Single value
  - `test_multiply_numbers_decimals()` - Decimal support
  - `test_multiply_numbers_zero()` - Zero handling
  - `test_multiply_numbers_negative_numbers()` - Negative numbers
  - `test_multiply_numbers_no_arguments()` - Empty args error
  - `test_multiply_numbers_invalid_input()` - Invalid number error

- [ ] Add CLI tests:
  - `test_main_multiply_command()` - Basic CLI usage
  - `test_main_multiply_command_decimals()` - Decimal CLI usage
  - `test_main_multiply_no_numbers()` - Missing numbers error
  - `test_main_multiply_invalid_number()` - Invalid input error

### 5. Update README.md

- [ ] Add operation section under Available Operations:

```markdown
#### Multiply Operation
Multiply multiple numbers together:

```bash
python3 calculator.py multiply 2 3 4
# Result: 24.0
```
```

- [ ] Update Test Coverage checklist with new operation
- [ ] Update Contributing section if needed

## Verification Checklist

- [ ] Run all tests: `python3 test_calculator.py`
- [ ] Test operation manually: `python3 calculator.py <operation> 1 2 3`
- [ ] Test help: `python3 calculator.py help`
- [ ] Test error - no numbers: `python3 calculator.py <operation>`
- [ ] Test error - invalid input: `python3 calculator.py <operation> 1 invalid`

## Pattern Reference: Division Example

```python
def divide_numbers(*args):
    """Divide numbers from left to right."""
    if not args:
        raise ValueError("At least one number is required for divide operation")
    
    result = float(args[0])
    for num_str in args[1:]:
        num = float(num_str)
        if num == 0:
            raise ValueError("Division by zero is not allowed")
        result /= num
    return result
```

## Common Mistakes

- Forgetting to update help text
- Inconsistent error message format
- Missing edge case tests (zero, negatives)
- Not updating README test coverage section
- Case-sensitive operation matching
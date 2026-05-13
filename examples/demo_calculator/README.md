# Calculator

A simple command-line calculator that supports summing an infinite number of space-separated parameters.

## Features

- **Sum Operation**: Add unlimited numbers separated by spaces
- **Help System**: Built-in help documentation
- **Error Handling**: Comprehensive error checking and user-friendly messages
- **Flexible Input**: Supports integers, decimals, and negative numbers

## Usage

```bash
python3 calculator.py <operation> <numbers...>
```

### Sum

```bash
python3 calculator.py sum 1 2 3
# Result: 6.0

python3 calculator.py sum 3.5 2.7 1.8
# Result: 8.0
```

### Help

```bash
python3 calculator.py help
```

## Testing

```bash
python3 test_calculator.py
```

## File Structure

```
.
├── calculator.py          # Main calculator script
├── test_calculator.py     # Unit tests
└── README.md              # This documentation
```

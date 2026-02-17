# Contributing to MarsCONE

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Code of Conduct

Please be respectful and constructive in all interactions. Follow the principles of scientific integrity.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/VolMorphNet/MarsCONE`
3. Create a branch: `git checkout -b feature/my-feature`
4. Install development dependencies: `pip install -e ".[dev]"`

## Development Workflow

### Code Style

We follow:
- PEP 8 style guide
- Black for code formatting (88 chars)
- isort for import organization
- Type hints where applicable

### Pre-commit Setup

```bash
pip install pre-commit
pre-commit install
```

### Running Checks Locally

```bash
# Format code
black .
isort .

# Check style
pylint **.py
flake8 .

# Run tests
pytest tests/ -v
```

## Submitting Changes

1. Ensure all tests pass: `pytest tests/`
2. Update documentation if needed
3. Add a docstring if adding functions
4. Commit with clear message: `git commit -m "Add feature X"`
5. Push to your fork: `git push origin feature/my-feature`
6. Open a Pull Request with description

## Testing

- Write tests for new functionality
- Aim for >80% code coverage
- Use pytest for testing framework

Example test:

```python
import pytest
from analyzer.measure import get_distance

def test_get_distance():
    profile = pd.DataFrame({
        'x_geo': [0.0, 1.0],
        'y_geo': [0.0, 0.0]
    })
    distance = get_distance(profile, 0, 1)
    assert distance == 1.0
```

## Documentation

- Use NumPy docstring format
- Include parameters and return types
- Add examples for key functions
- Update README for user-facing changes

Example docstring:

```python
def calculate_volume(height, base_area):
    """
    Calculate cone volume.
    
    Parameters
    ----------
    height : float
        Cone height in meters.
    base_area : float
        Base area in square meters.
    
    Returns
    -------
    float
        Volume in cubic meters.
    """
```

## Reporting Issues

When reporting bugs:
1. Describe the issue clearly
2. Include minimal reproduction code
3. Provide Python and dependency versions
4. Show error messages/tracebacks

## Questions?

Feel free to open a discussion or issue. We're here to help!

---

Thank you for contributing to MarsCONE!

#!/bin/bash
# Quick test script for MarsCONE pipeline

echo "╔════════════════════════════════════════════════════════════╗"
echo "║         MarsCONE Quick Validation Test                     ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Check if conda environment is activated
if [[ "$CONDA_DEFAULT_ENV" != "marscone" ]]; then
    echo "⚠ Warning: marscone environment not activated"
    echo "  Run: conda activate marscone"
    echo ""
fi

# 1. Check demo data
echo "▶ Checking demo data..."
if [ -d "data/test_set" ]; then
    echo "  ✔ Demo data found"
else
    echo "  ✘ Demo data not found"
    echo "    Run: python examples/example_download_demo_data.py"
    exit 1
fi

# 2. Run unit tests
echo ""
echo "▶ Running unit tests..."
python -m pytest tests/ -q --tb=line

if [ $? -ne 0 ]; then
    echo "  ✘ Tests failed"
    exit 1
fi

# 3. Run integration tests
echo ""
echo "▶ Running integration tests..."
python -m pytest tests/test_pipeline_integration.py -v

if [ $? -ne 0 ]; then
    echo "  ✘ Integration tests failed"
    exit 1
fi

# 4. Test pipeline runner
echo ""
echo "▶ Testing pipeline runner..."
python run_pipeline.py --help > /dev/null 2>&1

if [ $? -ne 0 ]; then
    echo "  ✘ Pipeline runner failed"
    exit 1
else
    echo "  ✔ Pipeline runner OK"
fi

# 5. Check code quality
echo ""
echo "▶ Checking code quality (pylint)..."
python -m pylint download_demo_data.py --disable=all --enable=E,F 2>&1 | grep -E "(rated|Your code)"

# Summary
echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                   ✔ All checks passed!                     ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "  1. Run full pipeline:    python run_pipeline.py"
echo "  2. Run with viz:         python run_pipeline.py --with-viz"
echo "  3. Run tests:            python -m pytest tests/ -v"
echo ""

# Contributing to Blinkit Price Tracker

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

1. Fork and clone the repo
2. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/Mac
   .venv\Scripts\activate     # Windows
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and add your Zyte API key

## Making Changes

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Make your changes
3. Test with a small CSV (2-3 products, 1 pincode) before submitting
4. Commit with clear messages following [Conventional Commits](https://www.conventionalcommits.org/)
5. Push and open a Pull Request

## Code Style

- Type hints for all function signatures
- Docstrings for all public functions
- Keep parsing logic in separate functions for testability
- Never hardcode API keys or secrets — use `.env`

## Reporting Issues

- Include your Python version and OS
- Paste the full traceback
- Mention which pincode/product failed
- Check if Blinkit has changed their CSS classes (common cause of failures)

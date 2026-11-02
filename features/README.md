# Features Module

This folder contains all bot features as separate modules.
Each feature should be a self-contained module with its own handlers, logic, and data.

## Structure

```
features/
├── __init__.py          # Package init - auto-registers features
├── eligibility/         # Existing eligibility system (example)
│   ├── __init__.py
│   ├── handlers.py      # Message & callback handlers
│   ├── logic.py         # Business logic
│   └── models.py        # Data models
├── schedule/            # Existing schedule system (example)
│   ├── __init__.py
│   ├── jobs.py          # Scheduled jobs
│   └── permissions.py   # Permission management
└── your_new_feature/    # New features go here
    ├── __init__.py
    ├── handlers.py
    ├── logic.py
    └── config.py        # Feature-specific config
```

## Adding a New Feature

1. Create a new folder under `features/`
2. Add your module files
3. In `__init__.py`, export a `get_handlers()` function that returns a list of handlers
4. Register in `bot.py` by importing and adding handlers

## Example Feature Template

```python
# features/my_feature/__init__.py
from .handlers import get_handlers

__all__ = ["get_handlers"]
```

```python
# features/my_feature/handlers.py
from telegram.ext import CommandHandler, MessageHandler, filters

async def my_command(update, context):
    await update.message.reply_text("Feature works!")

def get_handlers():
    return [
        CommandHandler("mycommand", my_command),
        # Add more handlers here
    ]
```

```python
# In bot.py - register the feature
from features.my_feature import get_handlers as get_my_feature_handlers

for handler in get_my_feature_handlers():
    application.add_handler(handler)
```

---

## Current Features (To Be Migrated)

- **eligibility** - User verification system (`eligibility.py`)
- **schedule** - Daily unlock/lock (`schedule.py`)

These will be migrated to this structure in future refactoring.
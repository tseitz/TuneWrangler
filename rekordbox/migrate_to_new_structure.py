#!/usr/bin/env python3
"""
Migration script to help users transition from old structure to new refactored structure.

This script provides backward compatibility and helps migrate existing usage to the new API.
"""

import sys
import warnings
from pathlib import Path

# Add the new package to path
sys.path.insert(0, str(Path(__file__).parent))

# Import the refactored modules
try:
    from rekordbox_smart_playlists.core.config import Config, load_config
    from rekordbox_smart_playlists.core.database import RekordboxDatabase
    from rekordbox_smart_playlists.core.playlist_manager import PlaylistManager
    from rekordbox_smart_playlists.core.backup_manager import (
        BackupManager,
        create_backup,
        restore_backup,
        list_backups,
    )
    from rekordbox_smart_playlists.core.metadata_fixer import MetadataFixer
    from rekordbox_smart_playlists.utils.logging import setup_logging
    from rekordbox_smart_playlists.cli.main import main as cli_main
except ImportError as e:
    print(f"Error importing refactored modules: {e}")
    print("Make sure you're running this from the project root directory.")
    sys.exit(1)


def show_migration_notice():
    """Show migration notice to users."""
    print("=" * 80)
    print("REKORDBOX SMART PLAYLISTS - MIGRATION NOTICE")
    print("=" * 80)
    print()
    print("This project has been refactored with a new structure!")
    print()
    print("NEW FEATURES:")
    print("• Unified CLI interface with subcommands")
    print("• Better error handling and logging")
    print("• Configuration file support (JSON/TOML)")
    print("• Improved backup and restore functionality")
    print("• Enhanced metadata synchronization")
    print("• Proper Python package structure")
    print()
    print("MIGRATION GUIDE:")
    print()
    print("1. OLD: python smart_playlists.py")
    print("   NEW: rekordbox-smart-playlists playlist create --all")
    print()
    print("2. OLD: python create_recent_playlists.py")
    print(
        "   NEW: rekordbox-smart-playlists playlist create --file recent-additions.json"
    )
    print()
    print("3. OLD: python fix_rekordbox_metadata.py")
    print("   NEW: rekordbox-smart-playlists metadata fix --interactive")
    print()
    print("4. OLD: from rekordbox_backup import backup_rekordbox_db")
    print("   NEW: rekordbox-smart-playlists backup create")
    print()
    print("5. Configuration is now centralized in config.json or config.toml")
    print("   See example configurations in the documentation.")
    print()
    print("=" * 80)


def create_example_config():
    """Create an example configuration file."""
    config = Config()

    # Save example configuration
    config_path = Path("config.example.json")
    if config.save_to_file(config_path):
        print(f"✓ Created example configuration: {config_path}")
        print("  Copy this to config.json and customize as needed.")
    else:
        print("✗ Failed to create example configuration")


def provide_backward_compatibility():
    """Provide backward compatibility for old imports."""

    # Create compatibility shims for old modules
    compatibility_code = {
        "smart_playlists.py": '''#!/usr/bin/env python3
"""
DEPRECATED: This file is deprecated. Use the new CLI interface instead.

OLD: python smart_playlists.py
NEW: rekordbox-smart-playlists playlist create --all

For more information, run: python migrate_to_new_structure.py
"""

import sys
import warnings
from pathlib import Path

# Show deprecation warning
warnings.warn(
    "smart_playlists.py is deprecated. Use 'rekordbox-smart-playlists playlist create --all' instead.",
    DeprecationWarning,
    stacklevel=2
)

# Import new modules
sys.path.insert(0, str(Path(__file__).parent))
from rekordbox_smart_playlists.core.config import Config
from rekordbox_smart_playlists.core.database import RekordboxDatabase
from rekordbox_smart_playlists.core.playlist_manager import PlaylistManager
from rekordbox_smart_playlists.core.backup_manager import BackupManager

def main():
    """Backward compatible main function."""
    print("⚠️  WARNING: This script is deprecated!")
    print("   Use: rekordbox-smart-playlists playlist create --all")
    print()
    
    response = input("Continue with deprecated script? (y/N): ")
    if response.lower() not in ['y', 'yes']:
        return
    
    # Load configuration and create playlists
    config = Config()
    
    try:
        with RekordboxDatabase(config) as db:
            # Create backup
            if config.backup_before_changes:
                backup_manager = BackupManager(config)
                backup_path = backup_manager.create_backup()
                if backup_path:
                    print(f"✓ Backup created: {backup_path}")
            
            # Create playlists
            playlist_manager = PlaylistManager(db, config)
            results = playlist_manager.create_playlists_from_directory(config.playlist_data_path)
            
            # Commit changes
            db.commit()
            
            # Print results
            successful = [r for r in results if r.success]
            print(f"\\nCreated {len(successful)} playlists successfully!")
            
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
''',
        "create_recent_playlists.py": '''#!/usr/bin/env python3
"""
DEPRECATED: This file is deprecated. Use the new CLI interface instead.

OLD: python create_recent_playlists.py
NEW: rekordbox-smart-playlists playlist create --file recent-additions.json

For more information, run: python migrate_to_new_structure.py
"""

import sys
import warnings
from pathlib import Path

warnings.warn(
    "create_recent_playlists.py is deprecated. Use 'rekordbox-smart-playlists playlist create --file recent-additions.json' instead.",
    DeprecationWarning,
    stacklevel=2
)

sys.path.insert(0, str(Path(__file__).parent))
from rekordbox_smart_playlists.core.config import Config
from rekordbox_smart_playlists.core.database import RekordboxDatabase
from rekordbox_smart_playlists.core.playlist_manager import PlaylistManager
from rekordbox_smart_playlists.core.backup_manager import BackupManager

def main():
    """Backward compatible main function."""
    print("⚠️  WARNING: This script is deprecated!")
    print("   Use: rekordbox-smart-playlists playlist create --file recent-additions.json")
    print()
    
    response = input("Continue with deprecated script? (y/N): ")
    if response.lower() not in ['y', 'yes']:
        return
    
    config = Config()
    
    try:
        with RekordboxDatabase(config) as db:
            # Create backup
            if config.backup_before_changes:
                backup_manager = BackupManager(config)
                backup_path = backup_manager.create_backup()
                if backup_path:
                    print(f"✓ Backup created: {backup_path}")
            
            # Create recent playlists
            playlist_manager = PlaylistManager(db, config)
            recent_config = Path(config.playlist_data_path) / "recent-additions.json"
            
            if recent_config.exists():
                results = playlist_manager.create_playlists_from_file(recent_config)
                db.commit()
                
                successful = [r for r in results if r.success]
                print(f"\\nCreated {len(successful)} recent playlists successfully!")
            else:
                print(f"Recent additions config not found: {recent_config}")
                return 1
                
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
''',
        "app.py": '''#!/usr/bin/env python3
"""
DEPRECATED: This file is deprecated. Use the new CLI interface instead.

For playlist management: rekordbox-smart-playlists playlist --help
For backup operations: rekordbox-smart-playlists backup --help

For more information, run: python migrate_to_new_structure.py
"""

import warnings

warnings.warn(
    "app.py is deprecated. Use the new rekordbox-smart-playlists CLI instead.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export commonly used functions for backward compatibility
from rekordbox_smart_playlists.core.backup_manager import create_backup, restore_backup, list_backups
from rekordbox_smart_playlists.core.database import RekordboxDatabase as db

# Show migration message when imported
print("⚠️  app.py is deprecated. Use 'rekordbox-smart-playlists --help' for the new CLI interface.")
''',
    }

    print("Creating backward compatibility shims...")

    for filename, code in compatibility_code.items():
        file_path = Path(filename)

        # Only create if old file doesn't exist or is different
        if not file_path.exists():
            with open(file_path, "w") as f:
                f.write(code)
            print(f"✓ Created compatibility shim: {filename}")
        else:
            print(f"• Skipped (exists): {filename}")


def main():
    """Main migration function."""
    show_migration_notice()

    print("MIGRATION ACTIONS:")
    print()

    # Create example configuration
    create_example_config()

    # Create backward compatibility shims
    provide_backward_compatibility()

    print()
    print("NEXT STEPS:")
    print("1. Install the package in development mode:")
    print("   pip install -e .")
    print()
    print("2. Try the new CLI:")
    print("   rekordbox-smart-playlists --help")
    print()
    print("3. Create your configuration file:")
    print("   cp config.example.json config.json")
    print("   # Edit config.json with your settings")
    print()
    print("4. Test with dry run:")
    print("   rekordbox-smart-playlists --dry-run playlist create --all")
    print()
    print("5. Create playlists:")
    print("   rekordbox-smart-playlists playlist create --all")
    print()
    print("For detailed help on any command, use --help:")
    print("  rekordbox-smart-playlists playlist --help")
    print("  rekordbox-smart-playlists backup --help")
    print("  rekordbox-smart-playlists metadata --help")
    print()
    print("=" * 80)


if __name__ == "__main__":
    main()

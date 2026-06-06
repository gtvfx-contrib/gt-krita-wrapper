"""PYTHONPATH Initialization Extension for Krita

This extension runs at Krita startup and adds paths from KRITA_PYTHONPATH
(or PYTHONPATH as fallback) environment variable to sys.path, enabling
access to Python tools.

"""
import os
import sys

from krita import Krita  # type: ignore
from krita import Extension # type: ignore


class PythonPathInitExtension(Extension):
    """Extension that initializes PYTHONPATH at Krita startup."""
    
    # Class variable to store which paths we added
    added_paths = []

    def __init__(self, parent):
        super().__init__(parent)
        # Run the initialization immediately when the extension is loaded
        self._initialize_pythonpath()

    def _initialize_pythonpath(self):
        """Add PYTHONPATH directories to sys.path."""
        try:
            # Try multiple sources for Python paths
            paths_to_process = []
            
            # 1. Try ENVOY_KRITA_PYTHONPATH environment variable (preferred)
            krita_pythonpath = os.getenv("ENVOY_KRITA_PYTHONPATH", "")
            if krita_pythonpath:
                print(f"PYTHONPATH Init: Found ENVOY_KRITA_PYTHONPATH environment variable")
                paths_to_process.extend(krita_pythonpath.split(os.pathsep))
            
            # 2. Try PYTHONPATH environment variable (fallback)
            pythonpath = os.getenv("PYTHONPATH", "")
            if pythonpath:
                print(f"PYTHONPATH Init: Found PYTHONPATH environment variable")
                paths_to_process.extend(pythonpath.split(os.pathsep))
            
            # 3. Try reading from a config file in user's Krita config directory
            config_file = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "krita", "pythonpath.txt")
            if os.path.exists(config_file):
                print(f"PYTHONPATH Init: Found config file: {config_file}")
                try:
                    with open(config_file, 'r') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#'):
                                paths_to_process.append(line)
                except Exception as e:
                    print(f"PYTHONPATH Init: Error reading config file: {e}")
            
            if not paths_to_process:
                print("PYTHONPATH Init: No Python paths found from any source")
                return
            
            print(f"PYTHONPATH Init: Found {len(paths_to_process)} total path entries")
            print("First 5 paths:")
            for i, entry in enumerate(paths_to_process[:5]):
                print(f"  [{i}] {entry}")
            if len(paths_to_process) > 5:
                print(f"  ... and {len(paths_to_process) - 5} more")
            
            # Normalize sys.path for comparison (convert to forward slashes)
            sys_path_normalized = {os.path.normpath(p).replace('\\', '/').lower() 
                                   for p in sys.path}
            
            print(f"Current sys.path has {len(sys.path)} entries")
            
            # Process paths in reverse order to maintain priority
            paths_to_add = []
            for path in reversed(paths_to_process):
                path = path.strip()
                if not path:
                    continue
                
                # Normalize the path for comparison
                normalized = os.path.normpath(path).replace('\\', '/').lower()
                if normalized not in sys_path_normalized:
                    # Keep original path format for adding
                    paths_to_add.append(path)
                    sys_path_normalized.add(normalized)
            
            # Add paths at index 1 (after script directory, before site-packages)
            for path in paths_to_add:
                sys.path.insert(1, path)
                PythonPathInitExtension.added_paths.append(path)
            
            if paths_to_add:
                print(f"PYTHONPATH Init: Added {len(paths_to_add)} path(s) to sys.path")
                print("First 3 paths added:")
                for path in list(paths_to_add)[:3]:
                    print(f"  {path}")
            else:
                print("PYTHONPATH Init: No new paths to add (all already in sys.path)")
                
        except Exception as e:
            print(f"PYTHONPATH Init ERROR: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

    def setup(self):
        """Called during extension setup - no additional setup needed."""
        pass

    def createActions(self, window):
        """No menu actions needed for this extension."""
        pass


# Register the extension with Krita
Krita.instance().addExtension(PythonPathInitExtension(Krita.instance()))

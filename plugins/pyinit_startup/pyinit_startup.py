
"""Python Initialization Startup Scripts Extension for Krita

This extension runs at Krita startup and executes Python initialization scripts
from directories specified in the PYINIT_STARTUP environment variable.

Scripts are discovered and executed in alphabetical order to provide predictable
initialization sequencing. Each script is executed in isolation with error
handling to prevent one failing script from breaking the entire startup process.

"""
import os
import sys
from pathlib import Path

# DEBUG: Print immediately when module is imported
print("="*80)
print("PYINIT_STARTUP PLUGIN: Module is being imported!")
print(f"PYINIT_STARTUP PLUGIN: Python version: {sys.version}")
print(f"PYINIT_STARTUP PLUGIN: PYINIT_STARTUP env var: {os.getenv('PYINIT_STARTUP', 'NOT SET')}")
print(f"PYINIT_STARTUP PLUGIN: ENVOY_KRITA_PYINIT_STARTUP env var: {os.getenv('ENVOY_KRITA_PYINIT_STARTUP', 'NOT SET')}")
print("="*80)
sys.stdout.flush()

from krita import Krita  # type: ignore
from krita import Extension  # type: ignore


class PyInitStartupExtension(Extension):
    """Extension that executes Python initialization scripts at Krita startup."""
    
    # Class variable to track executed scripts
    executed_scripts = []

    def __init__(self, parent):
        super().__init__(parent)
        # Run the initialization immediately when the extension is loaded
        self._execute_startup_scripts()

    def _execute_startup_scripts(self):
        """Discover and execute Python initialization scripts."""
        try:
            # Ensure PYTHONPATH is initialized before running startup scripts
            # Check if pythonpath_init has already run
            try:
                from pythonpath_init.pythonpath_init import PythonPathInitExtension
                if not PythonPathInitExtension.added_paths:
                    print("PYINIT Startup: pythonpath_init hasn't run yet, initializing now...")
                    # Manually trigger pythonpath initialization
                    temp_ext = PythonPathInitExtension(Krita.instance())
                    print(f"PYINIT Startup: Added {len(PythonPathInitExtension.added_paths)} paths to sys.path")
                else:
                    print(f"PYINIT Startup: pythonpath_init already initialized ({len(PythonPathInitExtension.added_paths)} paths)")
            except ImportError:
                print("PYINIT Startup: Warning - pythonpath_init plugin not available")
            
            sys.stdout.flush()
            
            # Get ENVOY_KRITA_PYINIT_STARTUP environment variable (preferred)
            # Fall back to PYINIT_STARTUP if not set
            pyinit_startup = os.getenv("ENVOY_KRITA_PYINIT_STARTUP", "")
            if pyinit_startup:
                print(f"PYINIT Startup: Processing ENVOY_KRITA_PYINIT_STARTUP paths")
            else:
                pyinit_startup = os.getenv("PYINIT_STARTUP", "")
                if pyinit_startup:
                    print(f"PYINIT Startup: Processing PYINIT_STARTUP paths")
            
            if not pyinit_startup:
                print("PYINIT Startup: Neither ENVOY_KRITA_PYINIT_STARTUP nor PYINIT_STARTUP environment variable is set")
                return
            
            # Collect all Python scripts from all directories
            script_paths = []
            for directory in pyinit_startup.split(os.pathsep):
                directory = directory.strip()
                if not directory:
                    continue
                
                dir_path = Path(directory)
                if not dir_path.exists():
                    print(f"PYINIT Startup: Path does not exist: {directory}")
                    continue
                
                if not dir_path.is_dir():
                    print(f"PYINIT Startup: Path is not a directory: {directory}")
                    continue
                
                # Find all .py files in the directory (not recursive)
                try:
                    py_files = sorted(dir_path.glob("*.py"))
                    if py_files:
                        print(f"PYINIT Startup: Found {len(py_files)} script(s) in {directory}")
                        script_paths.extend(py_files)
                    else:
                        print(f"PYINIT Startup: No .py files found in {directory}")
                except Exception as e:
                    print(f"PYINIT Startup: Error scanning {directory}: {e}")
            
            if not script_paths:
                print("PYINIT Startup: No Python scripts found to execute")
                return
            
            # Sort all scripts alphabetically for predictable execution order
            script_paths.sort()
            
            print(f"PYINIT Startup: Executing {len(script_paths)} script(s)")
            
            # Execute each script
            executed_count = 0
            failed_count = 0
            
            for script_path in script_paths:
                script_name = script_path.name
                print(f"PYINIT Startup: Executing {script_name} from {script_path.parent}")
                
                try:
                    # Create a namespace for the script with __file__ and __name__
                    script_namespace = {
                        '__file__': str(script_path),
                        '__name__': f'pyinit_startup.{script_path.stem}',
                        '__builtins__': __builtins__
                    }
                    
                    # Read and execute the script
                    with open(script_path, 'r', encoding='utf-8') as f:
                        script_code = f.read()
                    
                    exec(compile(script_code, str(script_path), 'exec'), script_namespace)
                    
                    # Flush output after each script
                    sys.stdout.flush()
                    sys.stderr.flush()
                    
                    # Track successful execution
                    PyInitStartupExtension.executed_scripts.append(str(script_path))
                    executed_count += 1
                    print(f"PYINIT Startup: Successfully executed {script_name}")
                    sys.stdout.flush()
                    
                except Exception as e:
                    failed_count += 1
                    print(f"PYINIT Startup ERROR in {script_name}: {type(e).__name__}: {e}")
                    import traceback
                    traceback.print_exc()
            
            # Summary
            print(f"PYINIT Startup: Completed - {executed_count} succeeded, {failed_count} failed")
            sys.stdout.flush()
            
        except Exception as e:
            print(f"PYINIT Startup FATAL ERROR: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            sys.stdout.flush()

    def setup(self):
        """Called during extension setup - no additional setup needed."""
        pass

    def createActions(self, window):
        """No menu actions needed for this extension."""
        pass


# Register the extension with Krita
Krita.instance().addExtension(PyInitStartupExtension(Krita.instance()))

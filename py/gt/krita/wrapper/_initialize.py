"""Krita wrapper initialization module.

This module provides functions for setting up the Krita environment, managing
plugins, and configuring Python paths before launching Krita. It handles:

- Python environment setup (KRITA_PYTHONPATH configuration)
- Plugin deployment from KRITA_PLUGINPATH to pykrita directory
- Plugin enablement in Krita's configuration file (kritarc)
- PYINIT_STARTUP path preservation for initialization scripts

The functions in this module are called by __main__.py during the wrapper's
initialization sequence before spawning the Krita process.

"""

__all__ = [
    "appendKritaPythonPath",
    "appendKritaPyinitStartup",
    "preservePyinitStartup",
    "manageKritaPlugins",
    "ensurePluginsEnabled",
]

import json
import logging
import os
from pathlib import Path

import envoy as envoy

from gt.pycore import robocopy, rmdir, getTimecodeVersion

log = logging.getLogger(__name__)

KRITA_ENV = envoy.get_environment("krita")
PYKRITA_DIR = Path(os.getenv("APPDATA", "")) / "krita" / "pykrita"
KRITARC_PATH = Path(os.getenv("LOCALAPPDATA", "")) / "kritarc"
MANAGED_PLUGINS_MANIFEST = PYKRITA_DIR / ".envoy_managed_plugins.json"


def _appendToEnvPath(env_var_name: str, path: str) -> None:
    """Append a path to an environment variable using os.pathsep as separator.
    
    If the environment variable doesn't exist, it will be created with the path.
    If it exists, the path will be appended with the appropriate path separator.
    
    Args:
        env_var_name: Name of the environment variable to modify.
        path: Path string to append to the environment variable.
        
    Example:
        >>> _appendToEnvPath("MY_PATHS", "C:\\tools")
        >>> os.getenv("MY_PATHS")
        'C:\\tools'
        >>> _appendToEnvPath("MY_PATHS", "C:\\utils")
        >>> os.getenv("MY_PATHS")
        'C:\\tools;C:\\utils'
        
    """
    current_value = os.environ.get(env_var_name, "")
    new_value = f"{current_value}{os.pathsep}{path}" if current_value else path
    os.environ[env_var_name] = new_value


def appendKritaPythonPath(py_path: str) -> None:
    """Append a path to the KRITA_PYTHONPATH environment variable.
    
    KRITA_PYTHONPATH is used by the pythonpath_init plugin to add paths to
    sys.path when Krita starts. This allows Krita's Python environment to
    import modules from custom locations.
    
    Args:
        py_path: Path to add to KRITA_PYTHONPATH. Should be an absolute path
                 to a directory containing Python modules.
        
    """
    _appendToEnvPath("ENVOY_KRITA_PYTHONPATH", py_path)


def appendKritaPyinitStartup(startup_path: str) -> None:
    """Append a path to the ENVOY_KRITA_PYINIT_STARTUP environment variable.
    
    ENVOY_KRITA_PYINIT_STARTUP is used by the pyinit_startup plugin to discover
    and execute Python initialization scripts at Krita startup.
    
    Args:
        startup_path: Path to add to ENVOY_KRITA_PYINIT_STARTUP. Should be an
                      absolute path to a directory containing .py files.
    
    See Also:
        preservePyinitStartup: Function that populates ENVOY_KRITA_PYINIT_STARTUP.
        
    """
    _appendToEnvPath("ENVOY_KRITA_PYINIT_STARTUP", startup_path)


def preservePyinitStartup() -> None:
    """Preserve original PYINIT_STARTUP paths before bl resolution changes them.
    
    The bl package system resolves workspace paths (e.g., Z:/repo/...) to
    installed package paths (e.g., C:/bl/pkgs/...). This causes PYINIT_STARTUP
    to point to package directories instead of the workspace, which breaks
    development workflows where startup scripts need to run from workspace.
    
    This function captures the original PYINIT_STARTUP value and stores it in
    ENVOY_KRITA_PYINIT_STARTUP for use by Krita plugins.
    
    Note:
        This function must be called early in __main__.py before bl package
        resolution occurs.
    
    Environment Variables:
        Reads: PYINIT_STARTUP
        Writes: ENVOY_KRITA_PYINIT_STARTUP
        
    """
    original_pyinit = os.getenv("PYINIT_STARTUP", "")
    if original_pyinit:
        os.environ["ENVOY_KRITA_PYINIT_STARTUP"] = original_pyinit
        log.info(
            "Preserved original PYINIT_STARTUP paths in ENVOY_KRITA_PYINIT_STARTUP"
        )
    else:
        log.info("No PYINIT_STARTUP set; skipping preservation")


def _loadPreviouslyManagedPlugins():
    """Load set of previously managed plugins from manifest.
    
    Returns:
        set[str]: Set of previously managed plugin names.
    
    """
    if not MANAGED_PLUGINS_MANIFEST.exists():
        return set()
    
    try:
        with open(MANAGED_PLUGINS_MANIFEST, 'r') as f:
            manifest_data = json.load(f)
            previously_managed = set(manifest_data.get("managed_plugins", []))
        log.info(
            "Loaded manifest with %d previously managed plugins",
            len(previously_managed),
        )
        return previously_managed
    except (OSError, json.JSONDecodeError) as e:
        log.warning("Failed to load plugin manifest: %s. Starting fresh.", e)
        return set()


def _collectCurrentPlugins(krita_pluginpath):
    """Collect all plugins from KRITA_PLUGINPATH directories.
    
    Args:
        krita_pluginpath: Semicolon-separated string of plugin paths.
    
    Returns:
        set[str]: Set of current plugin names.
    
    """
    currently_managed = set()
    for plugin_path in krita_pluginpath.split(os.pathsep):
        plugin_path = Path(plugin_path)
        
        if not plugin_path.exists():
            log.warning("Plugin path does not exist: %s", plugin_path)
            continue
        
        if not plugin_path.is_dir():
            log.warning("Plugin path is not a directory: %s", plugin_path)
            continue
        
        # Collect all items in this plugin path
        for item in plugin_path.iterdir():
            currently_managed.add(item.name)
    
    return currently_managed


def _removeStalePlugins(plugins_to_remove):
    """Remove plugins that are no longer in source paths.
    
    Args:
        plugins_to_remove: Set of plugin names to remove.
    
    """
    if not plugins_to_remove:
        return
    
    log.info("Removing %d stale managed plugins", len(plugins_to_remove))
    for plugin_name in plugins_to_remove:
        plugin_dest = PYKRITA_DIR / plugin_name
        if not plugin_dest.exists():
            continue
        
        try:
            if plugin_dest.is_dir():
                rmdir(str(plugin_dest))
                log.info("Removed managed plugin directory: %s", plugin_name)
            else:
                plugin_dest.unlink()
                log.info("Removed managed plugin file: %s", plugin_name)
        except (OSError, RuntimeError) as e:
            log.error("Failed to remove %s: %s", plugin_name, e)


def _copyPluginsFromPaths(krita_pluginpath):
    """Copy plugins from source paths to pykrita directory.
    
    Args:
        krita_pluginpath: Semicolon-separated string of plugin paths.
    
    """
    for plugin_path in krita_pluginpath.split(os.pathsep):
        plugin_path = Path(plugin_path)
        
        if not plugin_path.exists() or not plugin_path.is_dir():
            continue
        
        log.info("Copying plugins from %s to %s", plugin_path, PYKRITA_DIR)
        
        # Copy all contents using robocopy
        # Default behavior copies files when timestamps or sizes differ
        copy_result = robocopy(
            str(plugin_path), str(PYKRITA_DIR), params=["/E", "/R:3", "/W:5"]
        )
        if copy_result != 0:
            log.error(
                "Robocopy encountered errors copying from %s: exit code %d",
                plugin_path,
                copy_result,
            )
        else:
            log.info("Successfully copied all contents from %s", plugin_path)


def _savePluginManifest(currently_managed):
    """Save updated manifest of currently managed plugins.
    
    Args:
        currently_managed: Set of current plugin names.
    
    """
    try:
        manifest_data = {
            "managed_plugins": sorted(list(currently_managed)),
            "last_updated": getTimecodeVersion()
        }
        with open(MANAGED_PLUGINS_MANIFEST, 'w') as f:
            json.dump(manifest_data, f, indent=2)
        log.info(
            "Updated manifest with %d managed plugins", len(currently_managed)
        )
    except (OSError, TypeError) as e:
        log.warning("Failed to save plugin manifest: %s", e)
        
        
def manageKritaPlugins() -> None:
    """Manage Krita plugins with manifest-based tracking.
    
    This function implements a sophisticated plugin management system that:
    
    1. Reads ENVOY_KRITA_PLUGINPATH environment variable for plugin sources
    2. Loads manifest (.envoy_managed_plugins.json) of previously managed plugins
    3. Identifies and removes stale managed plugins no longer in sources
    4. Copies current plugins from all source directories to pykrita
    5. Updates manifest with currently managed plugin list
    
    The manifest tracking ensures that user-installed plugins are never removed,
    while managed plugins are kept in sync with their source directories.
    
    Plugin Deployment:
        Plugins are copied to: %APPDATA%/krita/pykrita/
        Manifest is stored at: %APPDATA%/krita/pykrita/.envoy_managed_plugins.json
    
    Note:
        Uses robocopy for efficient copying with timestamp/size comparison.
        Only files that have changed will be copied on subsequent runs.
    
    Environment Variables:
        Reads: ENVOY_KRITA_PLUGINPATH (from KRITA_ENV)
    
    Raises:
        Does not raise exceptions. Errors are logged and processing continues.
        
    """
    krita_pluginpath = KRITA_ENV.get("ENVOY_KRITA_PLUGINPATH", "")
    
    if not krita_pluginpath:
        log.info(
            "No ENVOY_KRITA_PLUGINPATH set in environment; skipping plugin management."
        )
        return
    
    if not PYKRITA_DIR.exists():
        log.info("Creating PYKRITA directory at: %s", PYKRITA_DIR)
        PYKRITA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load previously managed plugins and collect current ones
    previously_managed = _loadPreviouslyManagedPlugins()
    currently_managed = _collectCurrentPlugins(krita_pluginpath)
    
    # Remove stale plugins and copy current ones
    plugins_to_remove = previously_managed - currently_managed
    _removeStalePlugins(plugins_to_remove)
    _copyPluginsFromPaths(krita_pluginpath)
    
    # Save the updated manifest
    _savePluginManifest(currently_managed)


def _loadManagedPlugins():
    """Load list of managed plugins from manifest file.
    
    Returns:
        list[str]: List of managed plugin names, or empty list if unavailable.
    
    """
    if not MANAGED_PLUGINS_MANIFEST.exists():
        log.info("No managed plugins manifest found; skipping enablement")
        return []
    
    try:
        with open(MANAGED_PLUGINS_MANIFEST, 'r') as f:
            manifest_data = json.load(f)
            required_plugins = manifest_data.get("managed_plugins", [])
        log.info("Loaded %d managed plugin(s) from manifest", len(required_plugins))
        return required_plugins
    except (OSError, json.JSONDecodeError) as e:
        log.warning("Failed to load plugin manifest: %s", e)
        return []


def _findPythonSection(lines):
    """Find the [python] section in kritarc file lines.
    
    Args:
        lines: List of file lines.
    
    Returns:
        tuple[bool, int, int]: (section_found, start_index, end_index)
    
    """
    python_section_found = False
    python_section_start = -1
    python_section_end = -1
    
    for i, line in enumerate(lines):
        if line.strip() == "[python]":
            python_section_found = True
            python_section_start = i
        elif python_section_found and line.strip().startswith("["):
            python_section_end = i
            break
    
    if python_section_found and python_section_end == -1:
        python_section_end = len(lines)
    
    return python_section_found, python_section_start, python_section_end


def _updatePythonSection(lines, section_start, section_end, plugin_entries):
    """Update existing [python] section with plugin entries.
    
    Args:
        lines: List of file lines.
        section_start: Index where [python] section starts.
        section_end: Index where [python] section ends.
        plugin_entries: Dict of plugin entries to add/update.
    
    Returns:
        tuple[list[str], bool]: (updated_lines, was_modified)
    
    """
    new_python_lines = [lines[section_start]]  # Keep [python] header
    existing_keys = set()
    modified = False
    
    for i in range(section_start + 1, section_end):
        line = lines[i].strip()
        if '=' in line:
            key = line.split('=', 1)[0]
            existing_keys.add(key)
            # Update if it's one of our plugins
            if key in plugin_entries:
                new_line = f"{key}={plugin_entries[key]}\n"
                if new_line != lines[i]:
                    modified = True
                    log.info("Enabling plugin: %s", key.replace("enable_", ""))
                new_python_lines.append(new_line)
            else:
                new_python_lines.append(lines[i])
        else:
            new_python_lines.append(lines[i])
    
    # Add any missing plugins
    for key, value in plugin_entries.items():
        if key not in existing_keys:
            new_python_lines.append(f"{key}={value}\n")
            modified = True
            log.info("Adding plugin: %s", key.replace("enable_", ""))
    
    # Reconstruct the file
    updated_lines = (
        lines[:section_start] + new_python_lines + lines[section_end:]
    )
    return updated_lines, modified


def _createPythonSection(lines, plugin_entries):
    """Create new [python] section at end of file with plugin entries.
    
    Args:
        lines: List of file lines.
        plugin_entries: Dict of plugin entries to add.
    
    Returns:
        list[str]: Updated lines with new [python] section.
    
    """
    if lines and not lines[-1].endswith('\n'):
        lines.append('\n')
    lines.append('\n[python]\n')
    for key, value in plugin_entries.items():
        lines.append(f"{key}={value}\n")
        log.info("Adding plugin: %s", key.replace("enable_", ""))
    return lines


def ensurePluginsEnabled() -> None:
    """Ensure managed plugins are enabled in Krita's configuration.
    
    This function modifies the kritarc configuration file to automatically enable
    all managed plugins, eliminating the need for manual UI interaction.
    
    Process:
        1. Reads managed plugin list from manifest (.t2_managed_plugins.json)
        2. Parses existing kritarc file (if present) to find [python] section
        3. Updates or creates entries in format: enable_<plugin_name>=true
        4. Preserves all other configuration settings and user plugins
        5. Writes updated kritarc back to disk
    
    The [python] section format is specific to Krita's Python plugin system.
    Both plugin directories and .desktop files are tracked and enabled.
    
    Configuration File:
        Location: %LOCALAPPDATA%/kritarc (Windows)
        Format: INI-style with [python] section
        Entry format: enable_<plugin_name>=true
    
    Note:
        The function handles kritarc files that start with properties before
        any section headers by reading/writing as plain text rather than using
        ConfigParser.
    
    Raises:
        Does not raise exceptions. Errors are logged and processing continues.
    
    See Also:
        manageKritaPlugins: Function that creates the manifest this reads from.
        
    """
    try:
        # Always ensure Krita's built-in Python scripting engine is enabled.
        # Without scriptingmanager no Python plugins run at all.
        core_plugins = ["scriptingmanager"]

        # Load the list of managed plugins from manifest
        managed_plugins = _loadManagedPlugins()

        # Merge: core plugins first, then manifest plugins (deduped, order preserved)
        seen: set[str] = set()
        required_plugins: list[str] = []
        for p in core_plugins + managed_plugins:
            if p not in seen:
                seen.add(p)
                required_plugins.append(p)

        if not required_plugins:
            log.info("No plugins to enable")
            return
        
        # Read the existing file as text
        # (kritarc has properties without section headers)
        lines = []
        if KRITARC_PATH.exists():
            with open(KRITARC_PATH, 'r') as f:
                lines = f.readlines()
            log.info("Found existing kritarc at: %s", KRITARC_PATH)
        else:
            log.info("Creating new kritarc at: %s", KRITARC_PATH)
        
        # Build the plugin entries we need
        plugin_entries = {f"enable_{plugin}": "true" for plugin in required_plugins}
        
        # Find and update the [python] section
        section_found, section_start, section_end = _findPythonSection(lines)
        
        if section_found:
            lines, modified = _updatePythonSection(
                lines, section_start, section_end, plugin_entries
            )
        else:
            lines = _createPythonSection(lines, plugin_entries)
            modified = True
        
        if modified:
            with open(KRITARC_PATH, 'w') as f:
                f.writelines(lines)
            log.info("Updated kritarc with plugin enablement")
        else:
            log.info("All plugins already enabled in kritarc")
            
    except (OSError, IOError) as e:
        log.warning("Failed to update kritarc configuration: %s", e)

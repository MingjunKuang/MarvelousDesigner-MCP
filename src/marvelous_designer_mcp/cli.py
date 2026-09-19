"""Installed command line entry point. stdout is reserved for MCP in serve mode."""
import argparse
import json
import os
import platform
from pathlib import Path
import sys
from . import __version__
from .paths import DATA_DIR


def doctor(registry_path=None):
    from . import bridge, enhanced, config
    from .docs import DocsIndex
    from .plugin_install import settings_path, load_settings, ASSETS
    checks = {'OS': platform.platform(), 'Python': platform.python_version(), 'MCP version': __version__,
              'data directory': str(DATA_DIR), 'TCP': f'{config.MD_HOST}:{config.MD_PORT}'}
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        import tempfile
        with tempfile.TemporaryFile(dir=DATA_DIR): pass
        checks['data writable'] = 'OK'
    except OSError as exc:
        checks['data writable'] = str(exc)
    launcher = (DATA_DIR / 'plugin' / ASSETS[0]).as_posix()
    try:
        registry_path = Path(registry_path or settings_path())
        registry = load_settings(registry_path)
        checks['MD installation'] = 'Plugin registry detected (not proof of executable installation): ' + str(registry_path)
        registered = any(p.get('m_SourcePath', '').replace('\\', '/').lower() == launcher.lower() for p in registry['plugins'])
    except (OSError, ValueError):
        registered = False
        checks['MD installation'] = 'Registry not detected; launch MD once or use install-plugin --config.'
    checks['MD Plugin'] = 'OK' if registered and all((DATA_DIR / 'plugin' / a).is_file() for a in ASSETS) else 'Run md-mcp install-plugin'
    try:
        checks['docs index'] = DocsIndex().metadata()
    except Exception as exc:
        checks['docs index'] = str(exc) + ' Run md-mcp update-docs.'
    try:
        checks['listener ping'] = bridge.call('ping', timeout=3)
        # Keep doctor bounded even when a modal dialog blocks the GUI thread.
        previous = bridge.MD_TIMEOUT
        bridge.MD_TIMEOUT = 3
        try:
            env = enhanced.environment_info()
            api = enhanced.inspect_md_api('utility_api', 'GetMajorVersion')
        finally:
            bridge.MD_TIMEOUT = previous
        checks['environment_info'] = env
        scene = env['scene']
        version = scene.get('result', {}).get('md_version')
        checks['MD version'] = version
        checks['runtime API'] = 'OK' if scene.get('ok') and api.get('ok') else 'Unavailable'
        checks['Compatibility'] = 'VERIFIED version (Windows MD 2026.0.315)' if sys.platform == 'win32' and version == [2026, 0, 315] and api.get('ok') else 'UNVERIFIED'
        ready = scene.get('ok', False)
    except bridge.BridgeError as exc:
        checks['listener'] = exc.as_dict()
        checks['Compatibility'] = 'UNKNOWN: start MD and run Plugins > Plug-in > md_start_listener (插件 > 插件).'
        ready = False
    print('Marvelous Designer MCP Doctor')
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    return 0 if ready else 1


def main(argv=None):
    parser = argparse.ArgumentParser(prog='md-mcp', description='Local Marvelous Designer MCP and Windows Python bridge')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('serve', help='Run MCP over stdio; requires a running MD listener for scene tools')
    diagnostic = commands.add_parser('doctor', help='Diagnose installation, listener, runtime and documentation')
    diagnostic.add_argument('--config', type=Path, help='Explicit MD pluginSettings.json to inspect')
    commands.add_parser('version', help='Print package version')
    install = commands.add_parser('install-plugin', help='Copy bridge to user data and safely register when possible')
    install.add_argument('--config', type=Path, help='Explicit MD pluginSettings.json')
    install.add_argument('--menu', help='Localized menu tree, e.g. "Plugins / Plug-in" or "插件 / 插件"')
    commands.add_parser('uninstall-plugin', help='Remove only an owned registration; retain user files')
    docs = commands.add_parser('update-docs', help='Fetch official docs into user cache and build search index')
    docs.add_argument('--offline', action='store_true', help='Rebuild from previously fetched HTML')
    args = parser.parse_args(argv)
    try:
        if args.command == 'serve':
            from .__main__ import main as serve
            serve()
        elif args.command == 'version':
            print(__version__)
        elif args.command == 'doctor':
            return doctor(args.config)
        elif args.command == 'update-docs':
            from .docs_update import update
            print(json.dumps(update(args.offline), indent=2))
        else:
            from . import plugin_install
            result = plugin_install.install(args.config, menu=args.menu) if args.command == 'install-plugin' else plugin_install.uninstall()
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(f'{args.command}: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

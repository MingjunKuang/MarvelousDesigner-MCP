"""Deploy self-contained bridge files and conservatively edit MD's registry."""
from importlib.resources import files
import json
import os
from pathlib import Path
import shutil
import sys
import uuid
from .paths import DATA_DIR

ASSETS = ('scripts/md_start_listener.py', 'md_addon/md_listener.py', 'md_addon/md_event_listener.py')


def settings_path():
    return Path(os.environ.get('PUBLIC', r'C:\Users\Public')) / 'Documents/MarvelousDesigner/Plugins/pluginSettings.json'


def load_settings(path):
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict) or data.get('version') != 2 or not isinstance(data.get('plugins'), list) or not all(isinstance(p, dict) for p in data['plugins']):
        raise ValueError('Unsupported plugin settings schema; register manually in Plug-in Manager.')
    return data


def write_settings(path, before, data):
    # Refuse concurrent changes; preserve every unrelated field and entry.
    if path.read_bytes() != before:
        raise ValueError('Plugin settings changed during installation; close Plug-in Manager and retry.')
    backup = path.with_name(path.name + '.' + uuid.uuid4().hex + '.bak')
    shutil.copy2(path, backup)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    return str(backup)


def install(config=None, destination=None, menu=None):
    if sys.platform != 'win32':
        raise ValueError('The GUI timer bridge supports Windows only.')
    dest = Path(destination or DATA_DIR / 'plugin').resolve()
    for relative in ASSETS:
        source = files('marvelous_designer_mcp').joinpath('plugin', relative)
        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        # Packaged resources are authoritative. Source checkouts use the same assets.
        if source.is_file():
            content = source.read_bytes()
        else:
            development = Path(__file__).resolve().parents[2] / relative
            content = development.read_bytes()
        target.write_bytes(content)
    launcher = (dest / ASSETS[0]).as_posix()
    (dest / 'data-dir.txt').write_text(str(dest.parent), encoding='utf-8')
    config = Path(config or settings_path())
    result = {'launcher': launcher, 'settings': str(config), 'registered': False,
              'next': 'Start MD (or refresh Plug-in Manager), then Plugins > Plug-in > md_start_listener. Chinese UI: 插件 > 插件 > md_start_listener.',
              'manual': 'Plugins > Plug-in Manager > +ADD: select ' + launcher + '; choose the Plugins / Plug-in menu in your UI language, confirm, then run it.'}
    try:
        before = config.read_bytes()
        data = load_settings(config)
        existing = next((p for p in data['plugins'] if p.get('m_SourcePath', '').replace('\\', '/').lower() == launcher.lower()), None)
        manifest = dest / 'registration.json'
        if existing:
            result.update(registered=True, already_registered=True)
            # Never claim ownership of a registration created by somebody else.
            return result
        menus = [p.get('m_BaseMenuTreeByObjectName') for p in data['plugins'] if p.get('m_SourceType') == 'script']
        chosen = menu or (menus[0] if menus else None)
        if not chosen:
            result['warning'] = 'Menu language cannot be inferred. Register manually, or rerun with --menu "Plugins / Plug-in" (localized as needed).'
            return result
        entry = dict(m_AddingPositionIndex=max([p.get('m_AddingPositionIndex', 0) for p in data['plugins']] + [0]) + 1,
                     m_BaseMenuTreeByObjectName=chosen, m_PlugInFileName=launcher,
                     m_PlugInIconFileName='', m_PlugInTitle='md_start_listener', m_SourcePath=launcher, m_SourceType='script')
        data['plugins'].append(entry)
        # Write ownership before registry mutation so interrupted installs remain removable.
        manifest.write_text(json.dumps({'settings': str(config.resolve()), 'entry': entry}), encoding='utf-8')
        result.update(backup=write_settings(config, before, data), registered=True)
    except (OSError, ValueError, TypeError) as exc:
        result['warning'] = str(exc)
    return result


def uninstall(destination=None):
    dest = Path(destination or DATA_DIR / 'plugin').resolve()
    manifest = dest / 'registration.json'
    if not manifest.is_file():
        return {'removed': 0, 'message': 'No owned registration. If registered manually, remove this launcher in MD Plug-in Manager: ' + str(dest / ASSETS[0])}
    owned = json.loads(manifest.read_text(encoding='utf-8'))
    config = Path(owned['settings'])
    before = config.read_bytes()
    data = load_settings(config)
    matches = [p for p in data['plugins'] if p == owned['entry']]
    result = {'removed': len(matches), 'message': 'Bridge files, logs, checkpoints and user projects retained. Stop listener or close MD to unload it.'}
    if matches:
        data['plugins'] = [p for p in data['plugins'] if p != owned['entry']]
        result['backup'] = write_settings(config, before, data)
    elif any(p.get('m_SourcePath') == owned['entry']['m_SourcePath'] for p in data['plugins']):
        result['message'] = 'Registration was edited externally; preserved. Remove manually in MD Plug-in Manager.'
        return result
    manifest.unlink()
    return result

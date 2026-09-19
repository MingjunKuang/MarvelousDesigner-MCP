import asyncio
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from marvelous_designer_mcp import __version__, enhanced, plugin_install
from marvelous_designer_mcp.cli import main
from marvelous_designer_mcp.paths import data_dir


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = self.root / 'pluginSettings.json'
        self.other = {'m_SourcePath': 'other.py', 'm_SourceType': 'script', 'm_BaseMenuTreeByObjectName': '插件 / 插件', 'm_AddingPositionIndex': 3}
        self.initial = {'plugins': [self.other], 'version': 2, 'unrelated': True}
        self.config.write_text(json.dumps(self.initial), encoding='utf-8')
        self.dest = self.root / 'plugin'

    def install(self):
        with patch.object(plugin_install.sys, 'platform', 'win32'):
            return plugin_install.install(self.config, self.dest)

    def test_install_uninstall_preserves_other_plugins_and_projects(self):
        project = self.root / 'mine.zprj'
        project.write_bytes(b'user project')
        result = self.install()
        self.assertTrue(result['registered'])
        self.assertTrue(Path(result['backup']).is_file())
        for asset in plugin_install.ASSETS:
            self.assertTrue((self.dest / asset).is_file())
        self.assertEqual(self.install()['already_registered'], True)
        self.assertEqual(plugin_install.uninstall(self.dest)['removed'], 1)
        self.assertEqual(json.loads(self.config.read_text(encoding='utf-8')), self.initial)
        self.assertEqual(project.read_bytes(), b'user project')

    def test_unknown_schema_not_modified(self):
        self.config.write_text('{"plugins":{},"version":99}')
        before = self.config.read_bytes()
        self.assertFalse(self.install()['registered'])
        self.assertEqual(self.config.read_bytes(), before)

    def test_external_edit_not_removed(self):
        self.install()
        data = json.loads(self.config.read_text(encoding='utf-8'))
        data['plugins'][-1]['m_PlugInTitle'] = 'user title'
        self.config.write_text(json.dumps(data))
        self.assertEqual(plugin_install.uninstall(self.dest)['removed'], 0)
        self.assertEqual(json.loads(self.config.read_text(encoding='utf-8')), data)

    def test_unknown_menu_requires_manual_registration(self):
        self.config.write_text('{"plugins":[],"version":2}')
        result = self.install()
        self.assertFalse(result['registered'])
        self.assertIn('+ADD', result['manual'])

    def test_data_override_is_absolute(self):
        with patch.dict(os.environ, {'MD_MCP_DATA_DIR': str(self.root)}):
            self.assertEqual(data_dir(), self.root.resolve())

    def test_raw_disabled_without_disabling_semantic_tools(self):
        with patch.dict(os.environ, {'MD_MCP_ALLOW_RAW_PYTHON': '0'}), patch.object(enhanced.operations, 'execute') as execute:
            self.assertEqual(enhanced.execute_python('result=1')['error']['code'], 'raw_python_disabled')
            execute.assert_not_called()
            enhanced.create_pattern([[0, 0, 0], [100, 0, 0], [0, 100, 0]])
            execute.assert_called_once()

    def test_version_cli(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            self.assertEqual(main(['version']), 0)
        self.assertEqual(stream.getvalue().strip(), __version__)

    def test_mcp_instructions_and_all_descriptions(self):
        from mcp.server.fastmcp import FastMCP
        from marvelous_designer_mcp.tool_help import INSTRUCTIONS, MUTATIONS
        mcp = FastMCP('test', instructions=INSTRUCTIONS)
        for name in ['execute_python','scene_info','md_api','list_patterns','list_fabrics','assign_fabric','simulate','export_project','import_project']:
            mcp.add_tool(lambda: None, name=name)
        enhanced.register(mcp)
        tools = asyncio.run(mcp.list_tools())
        names = {t.name for t in tools}
        self.assertIn('pattern_arrangement', names)
        self.assertNotIn('pattern_placement', names)
        for tool in tools:
            self.assertTrue(tool.description)
            if tool.name in MUTATIONS:
                self.assertIn('UNKNOWN', tool.description)
        self.assertIn('project path', mcp.instructions)


if __name__ == '__main__':
    unittest.main()

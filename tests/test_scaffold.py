"""Offline contract tests: 新專案腳手架要示範資料畫面四態（核心規則 30）。

python -m unittest discover -s tests
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import aigo_auth
from aigo_scaffold import scaffold_new_project


class ScaffoldDataStateTest(unittest.TestCase):
    def scaffold(self, project_type):
        tmp = tempfile.mkdtemp(prefix='aigo_scaffold_test_')
        with patch.object(aigo_auth, 'init_config', lambda path: None):
            created = scaffold_new_project(tmp, project_type)
        return Path(tmp), created

    def test_both_types_ship_data_state_component(self):
        for project_type in ('single', 'multi'):
            root, created = self.scaffold(project_type)
            self.assertIn('src/components/DataState.tsx', created)
            component = (root / 'src/components/DataState.tsx').read_text(encoding='utf-8')
            for needle in ('loading', 'error', 'empty', 'onRetry', 'className="skeleton"'):
                self.assertIn(needle, component)

    def test_dashboard_separates_loading_from_empty(self):
        root, _ = self.scaffold('single')
        page = (root / 'src/pages/DashboardPage.tsx').read_text(encoding='utf-8')
        self.assertIn('useState<Load<Item[]>>({ status: "loading" })', page)
        self.assertIn('state.data.length === 0', page)
        self.assertIn('.catch(', page)
        self.assertIn('stale', page)

    def test_css_has_state_styles(self):
        root, _ = self.scaffold('single')
        css = (root / 'src/App.css').read_text(encoding='utf-8')
        for selector in ('.skeleton', '.state-box', '.state-error', '.btn:disabled', '.sr-only'):
            self.assertIn(selector, css)


if __name__ == '__main__':
    unittest.main()

"""UI catalog and Windows display-language checks; no GUI or game access."""
import ast
import os
from pathlib import Path
import re
from string import Formatter
import types
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import i18n as m
import update_check

ROOT = Path(__file__).resolve().parent
HANGUL = re.compile('[가-힣]')


def canonical(template):
    result, number = '', 0
    for literal, field, _, _ in Formatter().parse(template):
        result += literal
        if field is not None:
            result += '{' + str(number) + '}'
            number += 1
    return result


def application_strings():
    constants, templates = [], []
    for path in ROOT.glob('*.py'):
        if path.name.startswith('test_') or path.name == 'i18n.py':continue
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        parents = {id(child):node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                text, index = '', 0
                for item in node.values:
                    if isinstance(item, ast.Constant):text += str(item.value)
                    else:
                        text += '{' + str(index) + '}'
                        index += 1
                if HANGUL.search(text):templates.append((path.name, node.lineno, text))
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and HANGUL.search(node.value):
                if not isinstance(parents.get(id(node)), ast.JoinedStr):
                    constants.append((path.name, node.lineno, node.value))
    return constants, templates


class LanguageTests(unittest.TestCase):
    def test_primary_korean_ui_language_only_and_other_display_languages(self):
        for langid, expected in ((0x0412, 'ko'), (0x0812, 'ko'), (0x0409, 'en'), (0x0809, 'en'),
                                 (0x0411, 'en'), (0x0804, 'en'), (0x0404, 'en')):
            with self.subTest(langid=hex(langid)):
                self.assertEqual(m.language_from_langid(langid), expected)
                self.assertEqual(m.detect_language(lambda:langid), expected)

    def test_invalid_or_unavailable_display_language_falls_back_to_english(self):
        for value in (None, 0, -1, 0x10000, 'ko_KR', '0x0412', True, False):
            with self.subTest(value=value):self.assertEqual(m.detect_language(lambda:value), 'en')
        for error in (OSError('unavailable'), AttributeError('unsupported'), RuntimeError('failed')):
            with self.subTest(error=type(error).__name__):
                with patch.object(m.ctypes, 'windll', create=True, new=types.SimpleNamespace(kernel32=types.SimpleNamespace(
                        GetUserDefaultUILanguage=types.SimpleNamespace()))):
                    self.assertEqual(m.detect_language(), 'en')
                def getter():raise error
                self.assertEqual(m.detect_language(getter), 'en')

    def test_windows_ui_api_is_used_independently_of_us_region_or_locale(self):
        class UiLanguage:
            calls = 0
            def __call__(self):
                self.calls += 1
                return 0x0412
        getter = UiLanguage()
        windows = types.SimpleNamespace(kernel32=types.SimpleNamespace(GetUserDefaultUILanguage=getter))
        with patch.object(m.ctypes, 'windll', windows, create=True), patch.dict(os.environ, {'LANG':'en_US.UTF-8', 'LC_ALL':'en_US.UTF-8'}):
            self.assertEqual(m.detect_language(), 'ko')
        self.assertEqual(getter.calls, 1)
        self.assertEqual(getter.argtypes, [])
        self.assertIs(getter.restype, m.ctypes.c_ushort)

    def test_default_language_is_fixed_and_explicit_overrides_are_supported(self):
        with patch.object(m, 'LANGUAGE', 'en'), patch.object(m, 'detect_language', side_effect=AssertionError('must not query again')):
            self.assertEqual(m.tr('전체 ON'), 'All ON')
            self.assertEqual(m.tr('전체 ON', 'ko'), '전체 ON')
            self.assertEqual(m.tr('전체 ON', 'invalid'), 'All ON')
        with patch.object(m, 'LANGUAGE', 'ko'):
            self.assertEqual(m.tr('전체 ON'), '전체 ON')
            self.assertEqual(m.tr('All ON'), '전체 ON')


class CatalogTests(unittest.TestCase):
    def test_labels_status_counts_colors_versions_and_hotkey_templates(self):
        samples = {
            '살아 있는 사냥감: 10마리': 'Live animals: 10',
            '전체 ON · 6/6': 'All ON · 6/6',
            '일부 ON · 3/6': 'Some ON · 3/6',
            '현재 0.4.0 / 최신 0.5.0': 'Current 0.4.0 / Latest 0.5.0',
            '현재 0.4.0 / 최신 확인 중': 'Current 0.4.0 / Checking latest',
            '현재 0.4.0 / 최신 확인 불가': 'Current 0.4.0 / Latest Unavailable',
            '사체 ON · 대상 3마리': 'Carcasses ON · 3 targets',
            '사체 OFF · 대상 0마리': 'Carcasses OFF · 0 targets',
            '사체 색상: #12AB34 · 변경': 'Carcass color: #12AB34 · Change',
            '파랑을 선택했습니다. 모드 ON을 누르면 적용됩니다.': 'Blue selected. Press Mode ON to apply it.',
            '살아 있는 사냥감의 흰색 윤곽을 갱신하고 있습니다.': 'Updating White outlines for live animals.',
            '게임을 실행하고 사냥터에 들어가세요. 감지된 게임: 2개': 'Start the game and enter a reserve. Game processes found: 2',
            'Ctrl+Shift+F10 · 단축키 등록 중': 'Ctrl+Shift+F10 · Registering hotkey',
            'Ctrl+Shift+F10 · 전체 ON/OFF': 'Ctrl+Shift+F10 · All ON/OFF',
            '소음기 ON · 롱보우': 'Silencer ON · Longbow',
        }
        for source, expected in samples.items():
            with self.subTest(source=source):
                translated = m.tr(source, 'en')
                self.assertEqual(translated, expected)
                self.assertFalse(HANGUL.search(translated))
                self.assertEqual(m.tr(source, 'ko'), source)
                self.assertEqual(m.tr(translated, 'ko'), source)

    def test_known_backend_and_single_instance_errors_translate_both_ways(self):
        for source in ('게임 스레드가 변경 위치를 실행 중이어서 설치하지 않았습니다',
                       '중복 실행 상태를 확인하지 못해 모드를 시작하지 않았습니다',
                       '지원하지 않는 게임 버전입니다. 업데이트 확인 후 모드를 다시 실행하세요.',
                       '사냥감 윤곽 모드가 이미 열려 있습니다.\n기존 창에서 ON/OFF를 조작하세요.'):
            with self.subTest(source=source):
                english = m.tr(source, 'en')
                self.assertNotEqual(english, source)
                self.assertFalse(HANGUL.search(english))
                self.assertEqual(m.tr(english, 'ko'), source)
        for source, korean in m.KO_NATIVE.items():
            with self.subTest(native=source):
                self.assertEqual(m.tr(source, 'ko'), korean)
                self.assertEqual(m.tr(korean, 'en'), source)

    def test_real_update_result_messages_are_english_for_every_outcome(self):
        def release(tag='v0.5.0', **overrides):
            data = dict(id=1, draft=False, prerelease=False, tag_name=tag, published_at='2026-10-29T00:00:00Z',
                        html_url='https://github.com' + update_check.RELEASE_PATH + tag)
            data.update(overrides)
            return data
        results = [update_check.UpdateResult('not_checked'),
                   update_check.check_update(lambda:release(), current='0.4.0'),
                   update_check.check_update(lambda:release('v0.4.0'), current='0.4.0'),
                   update_check.check_update(lambda:release(prerelease=True), current='0.4.0'),
                   update_check.check_update(lambda:{}, current='0.4.0')]
        for error in (TimeoutError(), URLError(TimeoutError()), OSError('offline'),
                      HTTPError('https://api.github.com', 429, 'limited', {}, None),
                      HTTPError('https://api.github.com', 404, 'missing', {}, None)):
            def fetcher():raise error
            results.append(update_check.check_update(fetcher, current='0.4.0'))
        for result in results:
            with self.subTest(status=result.status):
                self.assertFalse(HANGUL.search(m.tr(result.message, 'en')))
                self.assertNotEqual(m.tr(result.message, 'en'), result.message)
                self.assertEqual(m.tr(result.message, 'ko'), result.message)

    def test_application_ast_korean_constants_and_fstring_templates_are_complete(self):
        constants, templates = application_strings()
        self.assertGreater(len(constants), 100)
        self.assertGreater(len(templates), 5)
        failures = [(file, line, text) for file, line, text in constants if HANGUL.search(m.tr(text, 'en'))]
        self.assertEqual(failures, [], 'Untranslated Korean application constants')
        known_templates = {canonical(template) for template in m.TEMPLATES}
        missing = [(file, line, text) for file, line, text in templates if canonical(text) not in known_templates]
        self.assertEqual(missing, [], 'Untranslated application f-string templates')
        self.assertTrue(all(not HANGUL.search(value) for value in m.EN.values()))

    def test_new_native_silencer_error_catalog_is_complete(self):
        missing = []
        for path in ROOT.glob('silencer*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8-sig'))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call) or not node.exc.args:continue
                first = node.exc.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str) and not HANGUL.search(first.value):
                    if first.value not in m.KO_NATIVE:missing.append((path.name, node.lineno, first.value))
        self.assertEqual(missing, [])

    def test_unknown_diagnostics_types_and_literal_format_characters_are_preserved(self):
        for source in ('Unknown diagnostic: 0xABCDEF', '진단 원문: 알 수 없는 외부 오류', '{x} [1] \\ file.bin', ''):
            self.assertEqual(m.tr(source, 'en'), source)
        self.assertIsNone(m.tr(None, 'en'))
        self.assertEqual(m.tr(123, 'en'), 123)


if __name__ == '__main__':unittest.main(verbosity=2)

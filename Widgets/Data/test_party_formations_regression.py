"""
Offline regression checks for Party Formations pure data logic.

This script intentionally avoids Guild Wars runtime state, PyImGui drawing,
injected clients, shared memory, and live party resolution. It exercises the
backend helpers in HeroAI.party_formations that are safe to import offline.

Run:
    python "Widgets/Data/test_party_formations_regression.py"
"""

from __future__ import annotations

import json
import math
import shutil
import sys
import traceback
from pathlib import Path


def _find_repo_root(start_path: Path) -> Path:
    current = start_path.resolve()
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        if (candidate / 'HeroAI' / 'party_formations.py').is_file():
            return candidate

    raise RuntimeError(f'Could not locate the Py4GW repo root from {start_path}.')


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = _find_repo_root(SCRIPT_DIR)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from HeroAI import party_formations as pf  # noqa: E402


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _expect_close(actual: float, expected: float, message: str, tolerance: float = 1e-6) -> None:
    if abs(actual - expected) > tolerance:
        raise AssertionError(f'{message}: expected {expected!r}, got {actual!r}.')


def _expect_offsets(actual: tuple[float, float], expected: tuple[float, float], message: str) -> None:
    _expect_close(actual[0], expected[0], f'{message} X')
    _expect_close(actual[1], expected[1], f'{message} Y')


def _shape_payload(**overrides) -> str:
    payload = {
        'type': pf.SHAPE_EXPORT_TYPE,
        'version': pf.SHAPE_EXPORT_VERSION,
        'name': 'Shape',
        'coordinate_space': pf.SHAPE_COORDINATE_SPACE,
        'spots': [{'label': 'Spot 1', 'offset_x': 1.0, 'offset_y': 2.0}],
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_rotation_round_trip() -> None:
    for offset_x, offset_y, angle in (
        (100.0, -50.0, 0.0),
        (10.0, 0.0, math.pi / 2.0),
        (-125.5, 450.25, -0.75),
        (0.0, 0.0, math.pi),
    ):
        rotated = pf.rotate_offset(offset_x, offset_y, angle)
        restored = pf.inverse_rotate_offset(rotated[0], rotated[1], angle)
        _expect_offsets(restored, (offset_x, offset_y), f'round trip {offset_x}, {offset_y}, {angle}')

    _expect_offsets(pf.rotate_offset(10.0, 0.0, math.pi / 2.0), (0.0, 10.0), '90 degree rotate')
    _expect_offsets(pf.inverse_rotate_offset(0.0, 10.0, math.pi / 2.0), (10.0, 0.0), '90 degree inverse')


def test_clear_assignment_preserves_geometry_and_spot_label() -> None:
    assignment = pf.FormationAssignment(
        kind=pf.ASSIGNMENT_ACCOUNT,
        offset_x=123.0,
        offset_y=-456.0,
        enabled=False,
        account_email='tester@example.com',
        account_name='Tester',
        character_name='Tester Character',
        account_party_position=3,
    )

    pf.clear_assignment_target(assignment, 'Backline')

    _expect(assignment.kind == pf.ASSIGNMENT_UNASSIGNED, 'clear should make assignment unassigned.')
    _expect(assignment.spot_label == 'Backline', 'clear should preserve fallback spot label.')
    _expect(assignment.offset_x == 123.0 and assignment.offset_y == -456.0, 'clear should preserve offsets.')
    _expect(assignment.enabled is False, 'clear should preserve enabled/off state.')
    _expect(not pf.assignment_has_target(assignment), 'cleared assignment should not have a target.')
    _expect(assignment.display_name() == 'Backline', 'unassigned display name should use spot label.')
    _expect(assignment.account_email == '', 'clear should remove account identity.')
    _expect(assignment.account_party_position == -1, 'clear should reset account party position.')


def test_shape_export_preserves_enabled_geometry_and_skips_invalid_spots() -> None:
    formation = pf.PartyFormation(
        name='Wedge',
        assignments=[
            pf.FormationAssignment(
                kind=pf.ASSIGNMENT_HERO,
                spot_label='Front',
                offset_x=100.5,
                offset_y=-25.25,
                hero_id=12,
                hero_name='Hero A',
            ),
            pf.FormationAssignment(
                kind=pf.ASSIGNMENT_UNASSIGNED,
                spot_label='Open',
                offset_x=0.0,
                offset_y=75.0,
            ),
            pf.FormationAssignment(
                kind=pf.ASSIGNMENT_ACCOUNT,
                enabled=False,
                spot_label='Disabled',
                offset_x=1.0,
                offset_y=2.0,
            ),
            pf.FormationAssignment(
                kind=pf.ASSIGNMENT_HERO,
                spot_label='Bool Offset',
                offset_x=True,
                offset_y=0.0,
            ),
            pf.FormationAssignment(
                kind=pf.ASSIGNMENT_HERO,
                spot_label='Huge Offset',
                offset_x=pf.MAX_SHAPE_OFFSET_ABS + 1.0,
                offset_y=0.0,
            ),
        ],
    )

    result = pf.export_formation_shape(formation)
    _expect(result.ok, 'shape export should succeed with valid enabled spots.')
    _expect(result.exported == 2, 'shape export should include two valid enabled spots.')
    _expect(result.skipped_disabled == 1, 'shape export should count disabled spots.')
    _expect(result.skipped_invalid == 2, 'shape export should count invalid offsets.')

    payload = json.loads(result.payload)
    _expect(payload['type'] == pf.SHAPE_EXPORT_TYPE, 'shape export type should be stable.')
    _expect(payload['version'] == pf.SHAPE_EXPORT_VERSION, 'shape export version should be stable.')
    _expect(payload['coordinate_space'] == pf.SHAPE_COORDINATE_SPACE, 'coordinate space should be stable.')
    _expect(payload['name'] == 'Wedge', 'shape export should preserve formation name.')
    _expect(
        payload['spots'][0] == {'label': 'Front', 'offset_x': 100.5, 'offset_y': -25.25},
        'first spot shape mismatch.',
    )
    _expect(
        payload['spots'][1] == {'label': 'Open', 'offset_x': 0.0, 'offset_y': 75.0},
        'unassigned spot shape mismatch.',
    )


def test_shape_export_respects_max_spot_limit() -> None:
    formation = pf.PartyFormation(
        name='Too Many',
        assignments=[
            pf.FormationAssignment(
                kind=pf.ASSIGNMENT_UNASSIGNED,
                spot_label=f'Spot {index + 1}',
                offset_x=float(index),
                offset_y=float(-index),
            )
            for index in range(pf.MAX_FORMATION_SPOTS + 2)
        ],
    )

    result = pf.export_formation_shape(formation)
    _expect(result.ok, 'shape export should succeed up to the max spot limit.')
    _expect(result.exported == pf.MAX_FORMATION_SPOTS, 'shape export should cap exported spots.')
    _expect(result.skipped_extra == 2, 'shape export should count extra spots over the limit.')


def test_shape_import_creates_unassigned_party_slot_formation() -> None:
    payload = _shape_payload(
        name='Wedge',
        spots=[
            {'label': 'Front', 'offset_x': 100.5, 'offset_y': -25.25},
            {'label': 'Open', 'offset_x': 0.0, 'offset_y': 75.0},
        ],
    )

    result = pf.import_formation_shape(payload, [pf.PartyFormation(name='Wedge')])
    _expect(result.ok and result.formation is not None, 'shape import should succeed.')
    formation = result.formation
    _expect(formation.name == 'Wedge (Imported 2)', 'shape import should make duplicate names unique.')
    _expect(formation.hotkey_key == pf.UNMAPPED_KEY_NAME, 'imported shape should not map a hotkey.')
    _expect(formation.hotkey_modifiers == pf.NO_MODIFIER_VALUE, 'imported shape should not map modifiers.')
    _expect(formation.target_mode == pf.TARGET_MODE_PARTY_SLOT, 'imported shape should use party-slot target mode.')
    _expect(len(formation.assignments) == 2, 'imported shape should create two assignments.')
    _expect(
        all(item.kind == pf.ASSIGNMENT_UNASSIGNED for item in formation.assignments),
        'imported spots should be unassigned.',
    )
    _expect(formation.assignments[0].spot_label == 'Front', 'first imported label mismatch.')
    _expect(formation.assignments[1].spot_label == 'Open', 'second imported label mismatch.')
    _expect(formation.assignments[0].offset_x == 100.5, 'first imported X mismatch.')
    _expect(formation.assignments[1].offset_y == 75.0, 'second imported Y mismatch.')


def test_shape_import_deduplicates_labels_and_defaults_blank_labels() -> None:
    payload = _shape_payload(
        name='Labels',
        spots=[
            {'label': 'Same', 'offset_x': 1.0, 'offset_y': 2.0},
            {'label': 'Same', 'offset_x': 3.0, 'offset_y': 4.0},
            {'label': '', 'offset_x': 5.0, 'offset_y': 6.0},
            {'offset_x': 7.0, 'offset_y': 8.0},
        ],
    )

    result = pf.import_formation_shape(payload, [])
    _expect(result.ok and result.formation is not None, 'duplicate-label shape import should succeed.')
    labels = [assignment.spot_label for assignment in result.formation.assignments]
    _expect(labels == ['Same', 'Same 2', 'Spot 3', 'Spot 4'], f'unexpected imported labels: {labels!r}.')
    _expect(result.details, 'duplicate-label import should include a detail message.')


def test_shape_import_rejects_invalid_payloads() -> None:
    invalid_cases = [
        ('', 'empty clipboard'),
        ('not json', 'invalid JSON'),
        (json.dumps([]), 'non-object payload'),
        (_shape_payload(type='wrong'), 'unsupported type'),
        (_shape_payload(version=True), 'boolean version'),
        (_shape_payload(version=pf.SHAPE_EXPORT_VERSION + 1), 'unsupported version'),
        (_shape_payload(coordinate_space='screen'), 'unsupported coordinate_space'),
        (_shape_payload(spots=[]), 'empty spots'),
        (
            _shape_payload(
                spots=[
                    {'label': f'Spot {index + 1}', 'offset_x': float(index), 'offset_y': 0.0}
                    for index in range(pf.MAX_FORMATION_SPOTS + 1)
                ]
            ),
            'too many spots',
        ),
        (_shape_payload(spots=[{'label': 'Bad', 'offset_x': True, 'offset_y': 0.0}]), 'boolean offset'),
        (
            _shape_payload(
                spots=[
                    {
                        'label': 'Huge',
                        'offset_x': pf.MAX_SHAPE_OFFSET_ABS + 1.0,
                        'offset_y': 0.0,
                    }
                ]
            ),
            'offset over limit',
        ),
    ]

    for payload, name in invalid_cases:
        result = pf.import_formation_shape(payload, [])
        _expect(not result.ok and result.formation is None, f'{name} should fail shape import.')
        _expect(result.message, f'{name} should provide a failure message.')


def test_config_save_load_and_legacy_load_paths() -> None:
    temp_root = SCRIPT_DIR / '_party_formations_regression_tmp'
    if temp_root.exists():
        shutil.rmtree(temp_root)
    temp_root.mkdir(parents=True)

    try:
        config_path = temp_root / 'nested' / 'party_formations.json'
        original = pf.PartyFormation(
            name='Saved',
            formation_id='saved-id',
            target_mode=pf.TARGET_MODE_PARTY_SLOT,
            assignments=[
                pf.FormationAssignment(
                    kind=pf.ASSIGNMENT_UNASSIGNED,
                    spot_label='Open',
                    offset_x=10.0,
                    offset_y=20.0,
                )
            ],
        )

        pf.save_formations([original], str(config_path))
        raw = json.loads(config_path.read_text(encoding='utf-8'))
        _expect(set(raw.keys()) == {'version', 'formations'}, 'saved config should keep the expected top-level shape.')
        _expect(raw['version'] == pf.CONFIG_VERSION, 'saved config version should be stable.')
        _expect(len(raw['formations']) == 1, 'saved config should contain one formation.')
        saved_formation = raw['formations'][0]
        _expect(
            set(saved_formation.keys())
            == {'formation_id', 'name', 'target_mode', 'hotkey_key', 'hotkey_modifiers', 'assignments'},
            'saved formation should keep the expected fields.',
        )
        _expect(saved_formation['assignments'][0]['offset_x'] == 10.0, 'saved assignment X should match.')
        _expect(not list(config_path.parent.glob('*.tmp')), 'atomic save should not leave temp files behind.')

        loaded = pf.load_formations(str(config_path))
        _expect(len(loaded) == 1, 'saved config should load one formation.')
        _expect(loaded[0].formation_id == 'saved-id', 'formation id should round trip.')
        _expect(loaded[0].target_mode == pf.TARGET_MODE_PARTY_SLOT, 'target mode should round trip.')
        _expect(loaded[0].assignments[0].spot_label == 'Open', 'spot label should round trip.')

        legacy_path = temp_root / 'legacy_list.json'
        legacy_path.write_text(
            json.dumps(
                [
                    {
                        'id': 'legacy-id',
                        'name': 'Legacy',
                        'assignments': [{'spot_label': 'Legacy Spot', 'offset_x': 7.5, 'offset_y': -2.5}],
                    }
                ]
            ),
            encoding='utf-8',
        )
        legacy = pf.load_formations(str(legacy_path))
        _expect(len(legacy) == 1, 'legacy list config should load one formation.')
        _expect(legacy[0].formation_id == 'legacy-id', 'legacy id alias should load as formation_id.')
        _expect(
            legacy[0].target_mode == pf.TARGET_MODE_IDENTITY,
            'missing legacy target mode should default to identity.',
        )
        _expect(legacy[0].assignments[0].kind == pf.ASSIGNMENT_HERO, 'missing assignment kind should default to hero.')

        corrupt_path = temp_root / 'corrupt.json'
        corrupt_path.write_text('{', encoding='utf-8')
        _expect(pf.load_formations(str(corrupt_path)) == [], 'corrupt config should load as empty.')
        _expect(pf.load_formations(str(temp_root / 'missing.json')) == [], 'missing config should load as empty.')
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_config_backups_create_prune_and_restore() -> None:
    temp_root = SCRIPT_DIR / '_party_formations_backup_tmp'
    if temp_root.exists():
        shutil.rmtree(temp_root)
    temp_root.mkdir(parents=True)

    try:
        config_path = temp_root / 'party_formations.json'
        first = pf.PartyFormation(name='First', formation_id='first')
        second = pf.PartyFormation(name='Second', formation_id='second')
        third = pf.PartyFormation(name='Third', formation_id='third')

        first_result = pf.save_formations([first], str(config_path))
        _expect(first_result.skipped, 'first save should skip backup because no prior config exists.')
        _expect(pf.list_config_backups(str(config_path)) == [], 'first save should not create a backup.')

        second_result = pf.save_formations([second], str(config_path))
        _expect(second_result.ok, 'second save should back up the first config before overwrite.')
        backups = pf.list_config_backups(str(config_path))
        _expect(len(backups) == 1, 'second save should create exactly one backup.')
        backup_formations = pf.load_formations(backups[0].path)
        _expect(backup_formations[0].formation_id == 'first', 'backup should contain the previous config.')

        config_path.write_text('{', encoding='utf-8')
        corrupt_result = pf.save_formations([third], str(config_path))
        _expect(corrupt_result.skipped, 'save should not back up a malformed current config.')
        backups_after_corrupt = pf.list_config_backups(str(config_path))
        _expect(len(backups_after_corrupt) == 1, 'malformed current config should not add a bad backup.')
        _expect(pf.config_load_warning(str(config_path)) == '', 'rewritten valid config should not warn.')

        for index in range(8):
            pf.save_formations(
                [pf.PartyFormation(name=f'Version {index}', formation_id=f'version-{index}')],
                str(config_path),
            )

        backups = pf.list_config_backups(str(config_path))
        _expect(len(backups) == pf.CONFIG_BACKUP_LIMIT, 'backup retention should keep only the latest backups.')
        latest_backup_formations = pf.load_formations(backups[0].path)
        _expect(latest_backup_formations, 'latest backup should be loadable before restore.')

        restore_result = pf.restore_latest_config_backup(str(config_path))
        _expect(restore_result.ok, 'restore latest backup should succeed.')
        restored = pf.load_formations(str(config_path))
        _expect(
            restored[0].formation_id == latest_backup_formations[0].formation_id,
            'restore should replace current config with the latest backup content.',
        )
        _expect(
            len(pf.list_config_backups(str(config_path))) == pf.CONFIG_BACKUP_LIMIT,
            'restore should preserve retention limit.',
        )
        _expect(restore_result.preserved_current_path, 'restore should preserve current config when practical.')
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_config_load_warning_for_malformed_existing_config() -> None:
    temp_root = SCRIPT_DIR / '_party_formations_load_warning_tmp'
    if temp_root.exists():
        shutil.rmtree(temp_root)
    temp_root.mkdir(parents=True)

    try:
        missing_path = temp_root / 'missing.json'
        corrupt_path = temp_root / 'corrupt.json'
        corrupt_path.write_text('{', encoding='utf-8')

        _expect(pf.config_load_warning(str(missing_path)) == '', 'missing config should not warn.')
        _expect(pf.config_load_warning(str(corrupt_path)), 'corrupt config should produce a warning.')
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_config_load_normalizes_malformed_assignment_scalars() -> None:
    temp_root = SCRIPT_DIR / '_party_formations_bad_assignment_tmp'
    if temp_root.exists():
        shutil.rmtree(temp_root)
    temp_root.mkdir(parents=True)

    try:
        config_path = temp_root / 'party_formations.json'
        config_path.write_text(
            json.dumps(
                {
                    'formations': [
                        {
                            'name': 'Mixed',
                            'assignments': [
                                {
                                    'kind': ['bad'],
                                    'offset_x': 'oops',
                                    'offset_y': None,
                                    'enabled': 'maybe',
                                    'spot_label': ['bad'],
                                    'label': {'bad': True},
                                    'hero_id': 'bad',
                                    'hero_name': ['bad'],
                                    'hero_party_position': {},
                                    'account_email': ['bad'],
                                    'account_name': {'bad': True},
                                    'character_name': ['bad'],
                                    'account_party_position': None,
                                },
                                {
                                    'kind': pf.ASSIGNMENT_UNASSIGNED,
                                    'offset_x': 12.0,
                                    'offset_y': -8.0,
                                    'enabled': False,
                                    'spot_label': 'Valid',
                                },
                            ],
                        }
                    ]
                }
            ),
            encoding='utf-8',
        )

        loaded = pf.load_formations(str(config_path))
        _expect(len(loaded) == 1, 'malformed assignment scalars should not drop the formation.')
        _expect(len(loaded[0].assignments) == 2, 'valid assignment rows should be preserved.')

        malformed = loaded[0].assignments[0]
        _expect(malformed.kind == pf.ASSIGNMENT_HERO, 'bad assignment kind should use the dataclass default.')
        _expect(malformed.offset_x == 0.0 and malformed.offset_y == 0.0, 'bad offsets should default to zero.')
        _expect(malformed.enabled is True, 'bad enabled value should use the dataclass default.')
        _expect(malformed.spot_label == '', 'bad spot label should default to blank.')
        _expect(malformed.label == '', 'bad label should default to blank.')
        _expect(malformed.hero_id == 0, 'bad hero id should default to zero.')
        _expect(malformed.hero_name == '', 'bad hero name should default to blank.')
        _expect(malformed.hero_party_position == 0, 'bad hero party position should default to zero.')
        _expect(malformed.account_email == '', 'bad account email should default to blank.')
        _expect(malformed.account_name == '', 'bad account name should default to blank.')
        _expect(malformed.character_name == '', 'bad character name should default to blank.')
        _expect(malformed.account_party_position == -1, 'bad account party position should default to -1.')

        valid = loaded[0].assignments[1]
        _expect(valid.kind == pf.ASSIGNMENT_UNASSIGNED, 'valid assignment kind should be preserved.')
        _expect(valid.offset_x == 12.0 and valid.offset_y == -8.0, 'valid assignment offsets should be preserved.')
        _expect(valid.enabled is False, 'valid assignment enabled value should be preserved.')
        _expect(valid.spot_label == 'Valid', 'valid assignment label should be preserved.')
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_config_load_treats_bad_assignment_lists_as_empty() -> None:
    temp_root = SCRIPT_DIR / '_party_formations_bad_assignment_list_tmp'
    if temp_root.exists():
        shutil.rmtree(temp_root)
    temp_root.mkdir(parents=True)

    try:
        config_path = temp_root / 'party_formations.json'
        config_path.write_text(
            json.dumps(
                {
                    'formations': [
                        {'name': 'Null Assignments', 'assignments': None},
                        {'name': 'Object Assignments', 'assignments': {'not': 'a list'}},
                    ]
                }
            ),
            encoding='utf-8',
        )

        loaded = pf.load_formations(str(config_path))
        _expect(len(loaded) == 2, 'bad assignment-list values should not drop formations.')
        _expect(loaded[0].assignments == [], 'assignments null should load as an empty list.')
        _expect(loaded[1].assignments == [], 'non-list assignments should load as an empty list.')
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_config_load_normalizes_bad_formation_scalars() -> None:
    temp_root = SCRIPT_DIR / '_party_formations_bad_formation_tmp'
    if temp_root.exists():
        shutil.rmtree(temp_root)
    temp_root.mkdir(parents=True)

    try:
        config_path = temp_root / 'party_formations.json'
        config_path.write_text(
            json.dumps(
                {
                    'formations': [
                        {
                            'formation_id': [],
                            'id': {},
                            'name': [],
                            'hotkey_key': [],
                            'hotkey_modifiers': [],
                            'target_mode': [],
                            'assignments': [],
                        }
                    ]
                }
            ),
            encoding='utf-8',
        )

        loaded = pf.load_formations(str(config_path))
        _expect(len(loaded) == 1, 'bad formation scalars should not drop the formation.')
        formation = loaded[0]
        _expect(formation.formation_id, 'bad formation id should be replaced with a generated id.')
        _expect(formation.name == 'Formation', 'bad formation name should use the dataclass default.')
        _expect(formation.hotkey_key == pf.UNMAPPED_KEY_NAME, 'bad hotkey key should default to unmapped.')
        _expect(formation.hotkey_modifiers == pf.NO_MODIFIER_VALUE, 'bad hotkey modifiers should default to none.')
        _expect(formation.target_mode == pf.TARGET_MODE_IDENTITY, 'bad target mode should use the legacy load default.')
        _expect(formation.assignments == [], 'bad formation assignment list should stay empty.')
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_target_mode_and_default_names() -> None:
    _expect(
        pf.normalize_target_mode(pf.TARGET_MODE_PARTY_SLOT) == pf.TARGET_MODE_PARTY_SLOT,
        'party-slot mode should normalize.',
    )
    _expect(
        pf.normalize_target_mode(pf.TARGET_MODE_IDENTITY) == pf.TARGET_MODE_IDENTITY,
        'identity mode should normalize.',
    )
    _expect(
        pf.normalize_target_mode('invalid', default=pf.TARGET_MODE_IDENTITY) == pf.TARGET_MODE_IDENTITY,
        'invalid mode should use supplied default.',
    )

    existing = [pf.PartyFormation(name='Formation 1'), pf.PartyFormation(name='Formation 2')]
    created = pf.create_empty_formation(existing)
    _expect(created.name == 'Formation 3', 'default formation name should skip existing names.')
    _expect(created.assignments == [], 'empty formation should start without assignments.')


def test_preflight_static_counts_duplicates_and_offsets() -> None:
    formation = pf.PartyFormation(
        name='Preflight',
        target_mode=pf.TARGET_MODE_PARTY_SLOT,
        assignments=[
            pf.FormationAssignment(
                kind=pf.ASSIGNMENT_HERO,
                spot_label='Front',
                hero_party_position=1,
                offset_x=100.0,
                offset_y=0.0,
            ),
            pf.FormationAssignment(
                kind=pf.ASSIGNMENT_HERO,
                spot_label='Back',
                hero_party_position=1,
                offset_x=-100.0,
                offset_y=0.0,
            ),
            pf.FormationAssignment(kind=pf.ASSIGNMENT_UNASSIGNED, spot_label='Open'),
            pf.FormationAssignment(
                kind=pf.ASSIGNMENT_ACCOUNT,
                enabled=False,
                spot_label='Off',
                account_party_position=2,
            ),
            pf.FormationAssignment(
                kind=pf.ASSIGNMENT_HERO,
                spot_label='Bad Offset',
                hero_party_position=3,
                offset_x=True,
                offset_y=0.0,
            ),
        ],
    )

    counts = pf.formation_preflight_counts(formation)
    _expect(counts.enabled == 4, 'preflight counts should include four enabled spots.')
    _expect(counts.disabled == 1, 'preflight counts should include one disabled spot.')
    _expect(counts.assigned == 4, 'preflight counts should include assigned disabled targets.')
    _expect(counts.unassigned == 1, 'preflight counts should include unassigned spots.')
    _expect(counts.duplicate_targets == 1, 'preflight counts should detect duplicate target groups.')
    _expect(counts.offset_warnings == 1, 'preflight counts should detect offset warnings.')

    duplicates = pf.formation_duplicate_target_groups(formation)
    _expect(len(duplicates) == 1, 'duplicate target grouping should return one group.')
    _expect(duplicates[0].target_label == 'Hero Slot 1', 'duplicate target label mismatch.')
    _expect(duplicates[0].spot_labels == ['Front', 'Back'], 'duplicate spot labels mismatch.')

    account_key, account_label = pf.formation_assignment_target_key(formation, formation.assignments[3])
    _expect(account_key == ('account_slot', 2), 'party-slot account target key mismatch.')
    _expect(account_label == 'Player Slot 3', 'party-slot account target label mismatch.')

    huge = pf.FormationAssignment(offset_x=pf.MAX_SHAPE_OFFSET_ABS + 1.0, offset_y=0.0)
    _expect(
        pf.preflight_assignment_offset_warning(huge) == 'Offset is unusually large.',
        'huge offset should produce an unusual-offset warning.',
    )


def test_preflight_snapshot_summary_counts() -> None:
    snapshot = pf.FormationPreflightSnapshot()
    snapshot.add_warning_note('Duplicate Hero Slot 1: Front, Back')
    snapshot.add_item(0, 'Front', 'Hero Slot 1', pf.PREFLIGHT_STATUS_WOULD_TARGET, 'Hero would be flagged.')
    snapshot.add_item(1, 'Open', '', pf.PREFLIGHT_STATUS_SKIPPED, 'No target assigned.')
    snapshot.add_item(2, 'Bad', 'Hero Slot 2', pf.PREFLIGHT_STATUS_WARNING, 'Offset must be numeric.')

    _expect(snapshot.would_target == 1, 'snapshot should count would-target rows.')
    _expect(snapshot.skipped == 1, 'snapshot should count skipped rows.')
    _expect(snapshot.warnings == 2, 'snapshot should count warning notes and warning rows.')
    _expect(len(snapshot.items) == 3, 'snapshot should retain item rows.')
    _expect(snapshot.warning_notes == ['Duplicate Hero Slot 1: Front, Back'], 'snapshot warning notes mismatch.')


def main() -> int:
    tests = [
        test_rotation_round_trip,
        test_clear_assignment_preserves_geometry_and_spot_label,
        test_shape_export_preserves_enabled_geometry_and_skips_invalid_spots,
        test_shape_export_respects_max_spot_limit,
        test_shape_import_creates_unassigned_party_slot_formation,
        test_shape_import_deduplicates_labels_and_defaults_blank_labels,
        test_shape_import_rejects_invalid_payloads,
        test_config_save_load_and_legacy_load_paths,
        test_config_backups_create_prune_and_restore,
        test_config_load_warning_for_malformed_existing_config,
        test_config_load_normalizes_malformed_assignment_scalars,
        test_config_load_treats_bad_assignment_lists_as_empty,
        test_config_load_normalizes_bad_formation_scalars,
        test_target_mode_and_default_names,
        test_preflight_static_counts_duplicates_and_offsets,
        test_preflight_snapshot_summary_counts,
    ]

    failures: list[str] = []
    for test in tests:
        try:
            test()
            print(f'PASS: {test.__name__}')
        except Exception:
            failures.append(test.__name__)
            print(f'FAIL: {test.__name__}')
            traceback.print_exc()

    if failures:
        print(f'{len(failures)} Party Formations regression check(s) failed: {", ".join(failures)}')
        return 1

    print(f'PASS: {len(tests)} Party Formations regression checks passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

from __future__ import annotations

import json
import math
import os
import time
import uuid
from dataclasses import dataclass
from dataclasses import field
from typing import Any

MODULE_NAME = 'Party Formations'
CONFIG_VERSION = 3
DEFAULT_COOLDOWN_SECONDS = 0.5
UNMAPPED_KEY_NAME = 'Unmapped'
NO_MODIFIER_VALUE = 0
SHAPE_EXPORT_TYPE = 'py4gw_party_formation_shape'
SHAPE_EXPORT_VERSION = 1
SHAPE_COORDINATE_SPACE = 'leader_relative_facing'
MAX_FORMATION_SPOTS = 11
MAX_SHAPE_OFFSET_ABS = 100000.0

ASSIGNMENT_UNASSIGNED = 'unassigned'
ASSIGNMENT_HERO = 'hero'
ASSIGNMENT_ACCOUNT = 'account'
TARGET_MODE_IDENTITY = 'identity'
TARGET_MODE_PARTY_SLOT = 'party_slot'
TARGET_MODES = {TARGET_MODE_IDENTITY, TARGET_MODE_PARTY_SLOT}
LEADER_PARTY_POSITION = 0
PREFLIGHT_STATUS_READY = 'Ready'
PREFLIGHT_STATUS_WARNING = 'Warning'
PREFLIGHT_STATUS_SKIPPED = 'Skipped'
PREFLIGHT_STATUS_WOULD_TARGET = 'Would target'


def normalize_target_mode(value: Any, default: str = TARGET_MODE_PARTY_SLOT) -> str:
    mode = str(value or default)
    if mode in TARGET_MODES:
        return mode
    return default


def _modifier_value_from_name(modifier_name: str) -> int:
    try:
        from Py4GWCoreLib.enums_src.IO_enums import ModifierKey

        return int(ModifierKey.__members__.get(modifier_name, ModifierKey.NoneKey))
    except Exception:
        return NO_MODIFIER_VALUE


def _safe_str(value: Any, default: str = '') -> str:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return default
    return str(value)


def _safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(result):
        return default
    return result


def _safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _safe_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return default
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {'1', 'true', 'yes', 'on'}:
            return True
        if normalized in {'0', 'false', 'no', 'off'}:
            return False
        return default
    return bool(value)


def _safe_assignment_kind(value: Any) -> str:
    kind = _safe_str(value, ASSIGNMENT_HERO)
    if kind in {ASSIGNMENT_UNASSIGNED, ASSIGNMENT_HERO, ASSIGNMENT_ACCOUNT}:
        return kind
    if isinstance(value, str):
        return kind
    return ASSIGNMENT_HERO


@dataclass
class FormationAssignment:
    kind: str = ASSIGNMENT_HERO
    offset_x: float = 0.0
    offset_y: float = 0.0
    enabled: bool = True
    spot_label: str = ''
    label: str = ''
    hero_id: int = 0
    hero_name: str = ''
    hero_party_position: int = 0
    account_email: str = ''
    account_name: str = ''
    character_name: str = ''
    account_party_position: int = -1

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'FormationAssignment':
        return cls(
            kind=_safe_assignment_kind(data.get('kind')),
            offset_x=_safe_float(data.get('offset_x'), 0.0),
            offset_y=_safe_float(data.get('offset_y'), 0.0),
            enabled=_safe_bool(data.get('enabled', True), True),
            spot_label=_safe_str(data.get('spot_label'), ''),
            label=_safe_str(data.get('label'), ''),
            hero_id=_safe_int(data.get('hero_id'), 0),
            hero_name=_safe_str(data.get('hero_name'), ''),
            hero_party_position=_safe_int(data.get('hero_party_position'), 0),
            account_email=_safe_str(data.get('account_email'), ''),
            account_name=_safe_str(data.get('account_name'), ''),
            character_name=_safe_str(data.get('character_name'), ''),
            account_party_position=_safe_int(data.get('account_party_position'), -1),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            'kind': self.kind,
            'offset_x': float(self.offset_x),
            'offset_y': float(self.offset_y),
            'enabled': bool(self.enabled),
            'spot_label': self.spot_label,
            'label': self.label,
            'hero_id': int(self.hero_id),
            'hero_name': self.hero_name,
            'hero_party_position': int(self.hero_party_position),
            'account_email': self.account_email,
            'account_name': self.account_name,
            'character_name': self.character_name,
            'account_party_position': int(self.account_party_position),
        }

    def display_name(self) -> str:
        if self.kind == ASSIGNMENT_UNASSIGNED:
            return self.spot_label or 'Unassigned spot'
        if self.label:
            return self.label
        if self.kind == ASSIGNMENT_ACCOUNT:
            return (
                self.character_name
                or self.account_name
                or self.account_email
                or f'Account slot {self.account_party_position}'
            )
        return self.hero_name or f'Hero {self.hero_id or self.hero_party_position}'


@dataclass
class PartyFormation:
    name: str
    formation_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    assignments: list[FormationAssignment] = field(default_factory=list)
    hotkey_key: str = UNMAPPED_KEY_NAME
    hotkey_modifiers: int = NO_MODIFIER_VALUE
    target_mode: str = TARGET_MODE_PARTY_SLOT

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'PartyFormation':
        key_name = _safe_str(data.get('hotkey_key'), UNMAPPED_KEY_NAME) or UNMAPPED_KEY_NAME

        raw_modifier = data.get('hotkey_modifiers', NO_MODIFIER_VALUE)
        try:
            if isinstance(raw_modifier, bool):
                raise ValueError
            modifier_value = int(raw_modifier)
        except (TypeError, ValueError, OverflowError):
            modifier_name = _safe_str(raw_modifier, 'NoneKey')
            modifier_value = _modifier_value_from_name(modifier_name)

        formation_id = _safe_str(data.get('formation_id') or data.get('id'), '') or uuid.uuid4().hex
        name = _safe_str(data.get('name'), 'Formation') or 'Formation'
        raw_assignments = data.get('assignments', [])
        if not isinstance(raw_assignments, list):
            raw_assignments = []
        assignments = [FormationAssignment.from_dict(item) for item in raw_assignments if isinstance(item, dict)]
        return cls(
            name=name,
            formation_id=formation_id,
            assignments=assignments,
            hotkey_key=key_name,
            hotkey_modifiers=modifier_value,
            target_mode=normalize_target_mode(data.get('target_mode'), default=TARGET_MODE_IDENTITY),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            'formation_id': self.formation_id,
            'name': self.name,
            'target_mode': normalize_target_mode(self.target_mode),
            'hotkey_key': self.hotkey_key,
            'hotkey_modifiers': int(self.hotkey_modifiers),
            'assignments': [assignment.to_dict() for assignment in self.assignments],
        }

    def key(self) -> Key:
        from Py4GWCoreLib.enums_src.IO_enums import Key

        return Key.__members__.get(self.hotkey_key, Key.Unmapped)

    def modifiers(self) -> ModifierKey:
        from Py4GWCoreLib.enums_src.IO_enums import ModifierKey

        try:
            return ModifierKey(int(self.hotkey_modifiers))
        except ValueError:
            return ModifierKey.NoneKey

    def set_hotkey(self, key: Any, modifiers: Any) -> None:
        self.hotkey_key = key.name
        self.hotkey_modifiers = int(modifiers)


@dataclass
class FormationShapeExportResult:
    payload: str = ''
    exported: int = 0
    skipped_disabled: int = 0
    skipped_invalid: int = 0
    skipped_extra: int = 0
    details: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.payload) and self.exported > 0

    def status(self) -> str:
        if not self.ok:
            return 'Export failed: no enabled valid spots to export.'

        parts = [f'Exported {self.exported} spot{"s" if self.exported != 1 else ""}']
        if self.skipped_disabled:
            parts.append(f'skipped {self.skipped_disabled} disabled spot{"s" if self.skipped_disabled != 1 else ""}')
        if self.skipped_invalid:
            parts.append(f'skipped {self.skipped_invalid} invalid spot{"s" if self.skipped_invalid != 1 else ""}')
        if self.skipped_extra:
            parts.append(f'skipped {self.skipped_extra} spot{"s" if self.skipped_extra != 1 else ""} over the limit')
        return '; '.join(parts) + '.'


@dataclass
class FormationShapeImportResult:
    formation: PartyFormation | None = None
    message: str = ''
    details: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.formation is not None


@dataclass
class FormationApplyResult:
    applied: int = 0
    skipped: int = 0
    messages: list[str] = field(default_factory=list)

    def add_applied(self, message: str) -> None:
        self.applied += 1
        self.messages.append(message)

    def add_skipped(self, message: str) -> None:
        self.skipped += 1
        self.messages.append(message)

    def summary(self) -> str:
        return f'Applied {self.applied}, skipped {self.skipped}'


@dataclass
class FormationTargetDuplicate:
    target_key: tuple[str, object]
    target_label: str
    spot_labels: list[str] = field(default_factory=list)


@dataclass
class FormationPreflightCounts:
    enabled: int = 0
    disabled: int = 0
    assigned: int = 0
    unassigned: int = 0
    duplicate_targets: int = 0
    offset_warnings: int = 0


@dataclass
class FormationPreflightItem:
    spot_index: int
    spot_label: str
    target_label: str
    status: str
    message: str
    target_x: float | None = None
    target_y: float | None = None


@dataclass
class FormationPreflightSnapshot:
    counts: FormationPreflightCounts = field(default_factory=FormationPreflightCounts)
    runtime_checked: bool = False
    runtime_ready: bool = False
    would_target: int = 0
    warnings: int = 0
    skipped: int = 0
    warning_notes: list[str] = field(default_factory=list)
    items: list[FormationPreflightItem] = field(default_factory=list)

    def add_warning_note(self, message: str) -> None:
        self.warnings += 1
        self.warning_notes.append(message)

    def add_item(
        self,
        spot_index: int,
        spot_label: str,
        target_label: str,
        status: str,
        message: str,
        target_x: float | None = None,
        target_y: float | None = None,
    ) -> None:
        if status == PREFLIGHT_STATUS_WOULD_TARGET:
            self.would_target += 1
        elif status == PREFLIGHT_STATUS_WARNING:
            self.warnings += 1
        elif status == PREFLIGHT_STATUS_SKIPPED:
            self.skipped += 1

        self.items.append(
            FormationPreflightItem(
                spot_index=spot_index,
                spot_label=spot_label,
                target_label=target_label,
                status=status,
                message=message,
                target_x=target_x,
                target_y=target_y,
            )
        )


class FormationCooldowns:
    def __init__(self, cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS):
        self.cooldown_seconds = cooldown_seconds
        self._last_applied: dict[str, float] = {}

    def ready(self, formation_id: str) -> bool:
        last_applied = self._last_applied.get(formation_id, 0.0)
        return time.monotonic() - last_applied >= self.cooldown_seconds

    def mark(self, formation_id: str) -> None:
        self._last_applied[formation_id] = time.monotonic()


def rotate_offset(offset_x: float, offset_y: float, facing_angle: float) -> tuple[float, float]:
    cos_a = math.cos(facing_angle)
    sin_a = math.sin(facing_angle)
    return (
        offset_x * cos_a - offset_y * sin_a,
        offset_x * sin_a + offset_y * cos_a,
    )


def inverse_rotate_offset(delta_x: float, delta_y: float, facing_angle: float) -> tuple[float, float]:
    cos_a = math.cos(facing_angle)
    sin_a = math.sin(facing_angle)
    return (
        delta_x * cos_a + delta_y * sin_a,
        -delta_x * sin_a + delta_y * cos_a,
    )


def default_config_path() -> str:
    try:
        import Py4GW

        base_path = Py4GW.Console.get_projects_path()
    except Exception:
        base_path = os.getcwd()
    return os.path.join(base_path, 'Widgets', 'Config', 'party_formations.json')


def _write_text_atomic(path: str, text: str) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    temp_path = f'{path}.{uuid.uuid4().hex}.tmp'
    try:
        with open(temp_path, 'w', encoding='utf-8') as handle:
            handle.write(text)
        os.replace(temp_path, path)
    except Exception:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass
        raise


def write_json_file_atomic(path: str, payload: Any, *, indent: int = 2, ensure_ascii: bool = True) -> None:
    text = json.dumps(payload, indent=indent, ensure_ascii=ensure_ascii, allow_nan=False)
    _write_text_atomic(path, text)


def load_formations(path: str | None = None) -> list[PartyFormation]:
    resolved_path = path or default_config_path()
    if not os.path.exists(resolved_path):
        return []

    try:
        with open(resolved_path, 'r', encoding='utf-8') as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []

    if isinstance(raw, list):
        formation_items = raw
    elif isinstance(raw, dict):
        formation_items = raw.get('formations', [])
    else:
        formation_items = []

    formations: list[PartyFormation] = []
    for item in formation_items:
        if not isinstance(item, dict):
            continue
        try:
            formations.append(PartyFormation.from_dict(item))
        except (TypeError, ValueError, OverflowError):
            continue
    return formations


def save_formations(formations: list[PartyFormation], path: str | None = None) -> None:
    resolved_path = path or default_config_path()
    payload = {
        'version': CONFIG_VERSION,
        'formations': [formation.to_dict() for formation in formations],
    }
    write_json_file_atomic(resolved_path, payload, indent=2)


def make_default_formation_name(existing: list[PartyFormation]) -> str:
    used_names = {formation.name for formation in existing}
    index = len(existing) + 1
    while True:
        name = f'Formation {index}'
        if name not in used_names:
            return name
        index += 1


def create_empty_formation(existing: list[PartyFormation]) -> PartyFormation:
    return PartyFormation(name=make_default_formation_name(existing))


def default_spot_label(index: int) -> str:
    return f'Spot {index + 1}'


def assignment_spot_label(assignment: FormationAssignment, index: int) -> str:
    return str(assignment.spot_label or default_spot_label(index)).strip() or default_spot_label(index)


def assignment_has_target(assignment: FormationAssignment) -> bool:
    return assignment.kind != ASSIGNMENT_UNASSIGNED


def formation_has_assigned_targets(formation: PartyFormation) -> bool:
    return any(assignment_has_target(assignment) for assignment in formation.assignments)


def clear_assignment_target(assignment: FormationAssignment, fallback_spot_label: str = '') -> None:
    if not assignment.spot_label:
        assignment.spot_label = fallback_spot_label
    assignment.kind = ASSIGNMENT_UNASSIGNED
    assignment.label = ''
    assignment.hero_id = 0
    assignment.hero_name = ''
    assignment.hero_party_position = 0
    assignment.account_email = ''
    assignment.account_name = ''
    assignment.character_name = ''
    assignment.account_party_position = -1


def formation_assignment_target_key(
    formation: PartyFormation,
    assignment: FormationAssignment,
) -> tuple[tuple[str, object] | None, str]:
    if not assignment_has_target(assignment):
        return None, ''

    if normalize_target_mode(formation.target_mode, default=TARGET_MODE_IDENTITY) == TARGET_MODE_PARTY_SLOT:
        if assignment.kind == ASSIGNMENT_HERO:
            hero_position = _safe_int(getattr(assignment, 'hero_party_position', 0), 0)
            if hero_position <= 0:
                return None, ''
            return ('hero_slot', hero_position), f'Hero Slot {hero_position}'
        if assignment.kind == ASSIGNMENT_ACCOUNT:
            party_position = _safe_int(getattr(assignment, 'account_party_position', -1), -1)
            if party_position <= LEADER_PARTY_POSITION:
                return None, ''
            return ('account_slot', party_position), f'Player Slot {party_position + 1}'
        return None, ''

    if assignment.kind == ASSIGNMENT_HERO:
        hero_id = _safe_int(getattr(assignment, 'hero_id', 0), 0)
        hero_name = str(getattr(assignment, 'hero_name', '') or '').strip()
        hero_position = _safe_int(getattr(assignment, 'hero_party_position', 0), 0)
        if hero_id > 0:
            return ('hero_id', hero_id), hero_name or f'Hero {hero_id}'
        if hero_name:
            return ('hero_name', hero_name.casefold()), hero_name
        if hero_position > 0:
            return ('hero_slot', hero_position), f'Hero Slot {hero_position}'
        return None, ''

    if assignment.kind == ASSIGNMENT_ACCOUNT:
        account_email = str(getattr(assignment, 'account_email', '') or '').strip()
        character_name = str(getattr(assignment, 'character_name', '') or '').strip()
        account_name = str(getattr(assignment, 'account_name', '') or '').strip()
        party_position = _safe_int(getattr(assignment, 'account_party_position', -1), -1)
        if account_email:
            return ('account_email', account_email.casefold()), character_name or account_name or account_email
        if character_name:
            return ('character_name', character_name.casefold()), character_name
        if account_name:
            return ('account_name', account_name.casefold()), account_name
        if party_position > LEADER_PARTY_POSITION:
            return ('account_slot', party_position), f'Player Slot {party_position + 1}'
    return None, ''


def formation_duplicate_target_groups(formation: PartyFormation) -> list[FormationTargetDuplicate]:
    targets: dict[tuple[str, object], FormationTargetDuplicate] = {}
    for index, assignment in enumerate(formation.assignments):
        target_key, target_label = formation_assignment_target_key(formation, assignment)
        if target_key is None:
            continue
        duplicate = targets.setdefault(
            target_key,
            FormationTargetDuplicate(target_key=target_key, target_label=target_label, spot_labels=[]),
        )
        duplicate.spot_labels.append(assignment_spot_label(assignment, index))

    return [duplicate for duplicate in targets.values() if len(duplicate.spot_labels) > 1]


def preflight_assignment_offset_warning(assignment: FormationAssignment) -> str:
    if isinstance(assignment.offset_x, bool) or isinstance(assignment.offset_y, bool):
        return 'Offset must be numeric.'

    try:
        offset_x = float(assignment.offset_x)
        offset_y = float(assignment.offset_y)
    except (TypeError, ValueError):
        return 'Offset must be numeric.'

    if not math.isfinite(offset_x) or not math.isfinite(offset_y):
        return 'Offset must be finite.'
    if abs(offset_x) > MAX_SHAPE_OFFSET_ABS or abs(offset_y) > MAX_SHAPE_OFFSET_ABS:
        return 'Offset is unusually large.'
    return ''


def formation_preflight_counts(formation: PartyFormation) -> FormationPreflightCounts:
    counts = FormationPreflightCounts()
    for assignment in formation.assignments:
        if bool(getattr(assignment, 'enabled', True)):
            counts.enabled += 1
        else:
            counts.disabled += 1

        if assignment_has_target(assignment):
            counts.assigned += 1
        else:
            counts.unassigned += 1

        if preflight_assignment_offset_warning(assignment):
            counts.offset_warnings += 1

    counts.duplicate_targets = len(formation_duplicate_target_groups(formation))
    return counts


def _shape_label(value: Any, index: int) -> str:
    if value is None:
        return default_spot_label(index)
    label = str(value).strip()
    if not label:
        return default_spot_label(index)
    return label[:80]


def _dedupe_shape_label(label: str, used_labels: set[str]) -> str:
    if label not in used_labels:
        used_labels.add(label)
        return label

    suffix = 2
    while f'{label} {suffix}' in used_labels:
        suffix += 1
    deduped = f'{label} {suffix}'
    used_labels.add(deduped)
    return deduped


def _valid_shape_offset(value: float) -> bool:
    return math.isfinite(value) and abs(value) <= MAX_SHAPE_OFFSET_ABS


def _parse_shape_offset(value: Any, field_name: str, spot_index: int) -> tuple[float | None, str | None]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, f'Spot {spot_index + 1}: {field_name} must be a finite number.'

    offset = float(value)
    if not _valid_shape_offset(offset):
        return None, (
            f'Spot {spot_index + 1}: {field_name} must be finite and within ' f'+/-{MAX_SHAPE_OFFSET_ABS:.0f}.'
        )
    return offset, None


def _unique_imported_formation_name(name: str, existing: list[PartyFormation]) -> str:
    base = name.strip() or 'Imported Formation'
    existing_names = {formation.name for formation in existing}
    if base not in existing_names:
        return base

    suffix = 2
    while True:
        candidate = f'{base} (Imported {suffix})'
        if candidate not in existing_names:
            return candidate
        suffix += 1


def export_formation_shape(formation: PartyFormation) -> FormationShapeExportResult:
    result = FormationShapeExportResult()
    spots: list[dict[str, Any]] = []

    for index, assignment in enumerate(formation.assignments):
        if not assignment.enabled:
            result.skipped_disabled += 1
            continue

        if isinstance(assignment.offset_x, bool) or isinstance(assignment.offset_y, bool):
            result.skipped_invalid += 1
            result.details.append(f'{assignment_spot_label(assignment, index)}: invalid offset skipped.')
            continue

        try:
            offset_x = float(assignment.offset_x)
            offset_y = float(assignment.offset_y)
        except (TypeError, ValueError):
            result.skipped_invalid += 1
            result.details.append(f'{assignment_spot_label(assignment, index)}: invalid offset skipped.')
            continue

        if not _valid_shape_offset(offset_x) or not _valid_shape_offset(offset_y):
            result.skipped_invalid += 1
            result.details.append(f'{assignment_spot_label(assignment, index)}: invalid offset skipped.')
            continue

        if len(spots) >= MAX_FORMATION_SPOTS:
            result.skipped_extra += 1
            continue

        spots.append(
            {
                'label': assignment_spot_label(assignment, index),
                'offset_x': offset_x,
                'offset_y': offset_y,
            }
        )

    result.exported = len(spots)
    if not spots:
        return result

    payload = {
        'type': SHAPE_EXPORT_TYPE,
        'version': SHAPE_EXPORT_VERSION,
        'name': formation.name or 'Formation',
        'coordinate_space': SHAPE_COORDINATE_SPACE,
        'spots': spots,
    }
    result.payload = json.dumps(payload, indent=2, ensure_ascii=True)
    return result


def import_formation_shape(payload: str, existing: list[PartyFormation]) -> FormationShapeImportResult:
    raw_payload = str(payload or '').strip()
    if not raw_payload:
        return FormationShapeImportResult(message='Import failed: clipboard is empty.')

    try:
        raw = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        return FormationShapeImportResult(message=f'Import failed: invalid JSON ({exc.msg}).')

    if not isinstance(raw, dict):
        return FormationShapeImportResult(message='Import failed: shape payload must be a JSON object.')
    if raw.get('type') != SHAPE_EXPORT_TYPE:
        return FormationShapeImportResult(message='Import failed: unsupported shape type.')
    version = raw.get('version')
    if isinstance(version, bool) or not isinstance(version, int) or version != SHAPE_EXPORT_VERSION:
        return FormationShapeImportResult(message='Import failed: unsupported shape version.')
    if raw.get('coordinate_space') != SHAPE_COORDINATE_SPACE:
        return FormationShapeImportResult(message='Import failed: unsupported coordinate_space.')

    spots_raw = raw.get('spots')
    if not isinstance(spots_raw, list) or not spots_raw:
        return FormationShapeImportResult(message='Import failed: shape must contain at least one spot.')
    if len(spots_raw) > MAX_FORMATION_SPOTS:
        return FormationShapeImportResult(
            message=f'Import failed: shape has {len(spots_raw)} spots; maximum is {MAX_FORMATION_SPOTS}.'
        )

    assignments: list[FormationAssignment] = []
    used_labels: set[str] = set()
    details: list[str] = []
    for index, item in enumerate(spots_raw):
        if not isinstance(item, dict):
            return FormationShapeImportResult(message=f'Import failed: spot {index + 1} must be an object.')

        offset_x, error = _parse_shape_offset(item.get('offset_x'), 'offset_x', index)
        if error:
            return FormationShapeImportResult(message=f'Import failed: {error}')
        offset_y, error = _parse_shape_offset(item.get('offset_y'), 'offset_y', index)
        if error:
            return FormationShapeImportResult(message=f'Import failed: {error}')

        label = _shape_label(item.get('label'), index)
        unique_label = _dedupe_shape_label(label, used_labels)
        if unique_label != label:
            details.append(f'Disambiguated duplicate spot label {label!r} to {unique_label!r}.')

        assignments.append(
            FormationAssignment(
                kind=ASSIGNMENT_UNASSIGNED,
                offset_x=float(offset_x),
                offset_y=float(offset_y),
                spot_label=unique_label,
            )
        )

    name = _unique_imported_formation_name(str(raw.get('name') or 'Imported Formation'), existing)
    formation = PartyFormation(
        name=name,
        assignments=assignments,
        hotkey_key=UNMAPPED_KEY_NAME,
        hotkey_modifiers=NO_MODIFIER_VALUE,
        target_mode=TARGET_MODE_PARTY_SLOT,
    )
    return FormationShapeImportResult(
        formation=formation,
        message=f'Imported shape {formation.name} with {len(assignments)} unassigned spots.',
        details=details,
    )


def get_available_members() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from HeroAI.utils import SameMapOrPartyAsAccount
    from Py4GWCoreLib.GlobalCache import GLOBAL_CACHE
    from Py4GWCoreLib.Party import Party

    heroes: list[dict[str, Any]] = []
    for index, hero in enumerate(Party.GetHeroes(), start=1):
        agent_id = int(getattr(hero, 'agent_id', 0) or 0)
        hero_id_obj = getattr(hero, 'hero_id', None)
        hero_id = int(hero_id_obj.GetID()) if hero_id_obj is not None else 0
        hero_name = str(hero_id_obj.GetName()) if hero_id_obj is not None else ''
        heroes.append(
            {
                'kind': ASSIGNMENT_HERO,
                'agent_id': agent_id,
                'hero_id': hero_id,
                'hero_name': hero_name,
                'hero_party_position': index,
                'label': hero_name or f'Hero {index}',
                'slot_label': f'Hero Slot {index}',
            }
        )

    accounts: list[dict[str, Any]] = []
    local_email = ''
    try:
        from Py4GWCoreLib.Player import Player

        local_email = str(Player.GetAccountEmail() or '')
    except Exception:
        local_email = ''

    for account in GLOBAL_CACHE.ShMem.GetAllActiveSlotsData():
        if not account or not bool(getattr(account, 'IsSlotActive', False)):
            continue
        if not bool(getattr(account, 'IsAccount', False)):
            continue
        if bool(getattr(account, 'IsHero', False)) or bool(getattr(account, 'IsPet', False)):
            continue
        account_email = str(getattr(account, 'AccountEmail', '') or '')
        if account_email and account_email == local_email:
            continue
        if not SameMapOrPartyAsAccount(account):
            continue

        agent_data = getattr(account, 'AgentData', None)
        party_data = getattr(account, 'AgentPartyData', None)
        if int(getattr(party_data, 'PartyID', 0) or 0) != int(GLOBAL_CACHE.Party.GetPartyID() or 0):
            continue
        character_name = str(getattr(agent_data, 'CharacterName', '') or '')
        account_name = str(getattr(account, 'AccountName', '') or '')
        party_position = int(getattr(party_data, 'PartyPosition', -1) or -1)
        if party_position <= LEADER_PARTY_POSITION:
            continue
        accounts.append(
            {
                'kind': ASSIGNMENT_ACCOUNT,
                'agent_id': int(getattr(agent_data, 'AgentID', 0) or 0),
                'account_email': account_email,
                'account_name': account_name,
                'character_name': character_name,
                'account_party_position': party_position,
                'label': character_name or account_name or account_email or f'Account slot {party_position}',
                'slot_label': f'Player Slot {party_position + 1}',
            }
        )

    accounts.sort(key=lambda item: (int(item.get('account_party_position', 9999)), str(item.get('label', ''))))
    return heroes, accounts


def assignment_from_member(member: dict[str, Any], offset_x: float = 0.0, offset_y: float = 0.0) -> FormationAssignment:
    if member.get('kind') == ASSIGNMENT_ACCOUNT:
        return FormationAssignment(
            kind=ASSIGNMENT_ACCOUNT,
            offset_x=offset_x,
            offset_y=offset_y,
            label=str(member.get('label') or ''),
            account_email=str(member.get('account_email') or ''),
            account_name=str(member.get('account_name') or ''),
            character_name=str(member.get('character_name') or ''),
            account_party_position=int(member.get('account_party_position', -1) or -1),
        )

    return FormationAssignment(
        kind=ASSIGNMENT_HERO,
        offset_x=offset_x,
        offset_y=offset_y,
        label=str(member.get('label') or ''),
        hero_id=int(member.get('hero_id') or 0),
        hero_name=str(member.get('hero_name') or ''),
        hero_party_position=int(member.get('hero_party_position') or 0),
    )


def _hero_slot_label(hero_position: int, occupant_label: str = '') -> str:
    if hero_position <= 0:
        return 'Hero Slot ?'
    if occupant_label:
        return f'Hero Slot {hero_position}: {occupant_label}'
    return f'Hero Slot {hero_position}'


def _player_slot_label(account_party_position: int, occupant_label: str = '') -> str:
    if account_party_position <= LEADER_PARTY_POSITION:
        return 'Leader / Anchor'
    public_slot = account_party_position + 1
    if occupant_label:
        return f'Player Slot {public_slot}: {occupant_label}'
    return f'Player Slot {public_slot}'


def _resolve_hero_assignment_with_position(assignment: FormationAssignment) -> tuple[int, int, str]:
    from Py4GWCoreLib.Party import Party

    fallback: tuple[int, int, str] = (0, 0, assignment.display_name())
    for index, hero in enumerate(Party.GetHeroes(), start=1):
        hero_id_obj = getattr(hero, 'hero_id', None)
        hero_id = int(hero_id_obj.GetID()) if hero_id_obj is not None else 0
        hero_name = str(hero_id_obj.GetName()) if hero_id_obj is not None else ''
        agent_id = int(getattr(hero, 'agent_id', 0) or 0)
        label = hero_name or assignment.display_name()
        if assignment.hero_id and hero_id == assignment.hero_id:
            return agent_id, index, label
        if assignment.hero_name and hero_name and hero_name == assignment.hero_name:
            fallback = (agent_id, index, label)

    if fallback[0] > 0:
        return fallback

    if assignment.hero_party_position > 0:
        return (
            int(Party.Heroes.GetHeroAgentIDByPartyPosition(assignment.hero_party_position) or 0),
            int(assignment.hero_party_position),
            assignment.display_name(),
        )

    return 0, 0, assignment.display_name()


def _resolve_hero_slot_assignment_with_position(assignment: FormationAssignment) -> tuple[int, int, str]:
    from Py4GWCoreLib.Party import Party

    hero_position = int(assignment.hero_party_position or 0)
    label = _hero_slot_label(hero_position)
    if hero_position <= 0:
        return 0, 0, label

    for index, hero in enumerate(Party.GetHeroes(), start=1):
        if index != hero_position:
            continue
        hero_id_obj = getattr(hero, 'hero_id', None)
        hero_name = str(hero_id_obj.GetName()) if hero_id_obj is not None else ''
        agent_id = int(getattr(hero, 'agent_id', 0) or 0)
        return agent_id, index, _hero_slot_label(hero_position, hero_name or assignment.display_name())

    return int(Party.Heroes.GetHeroAgentIDByPartyPosition(hero_position) or 0), hero_position, label


def _resolve_hero_assignment_with_position_for_mode(
    assignment: FormationAssignment,
    target_mode: str,
) -> tuple[int, int, str]:
    if normalize_target_mode(target_mode, default=TARGET_MODE_IDENTITY) == TARGET_MODE_PARTY_SLOT:
        return _resolve_hero_slot_assignment_with_position(assignment)
    return _resolve_hero_assignment_with_position(assignment)


def _resolve_hero_assignment(assignment: FormationAssignment) -> tuple[int, str]:
    agent_id, _hero_position, label = _resolve_hero_assignment_with_position(assignment)
    return agent_id, label


def _resolve_hero_assignment_for_mode(assignment: FormationAssignment, target_mode: str) -> tuple[int, str]:
    agent_id, _hero_position, label = _resolve_hero_assignment_with_position_for_mode(assignment, target_mode)
    return agent_id, label


def _resolve_account_assignment(assignment: FormationAssignment):
    from HeroAI.utils import SameMapOrPartyAsAccount
    from Py4GWCoreLib.GlobalCache import GLOBAL_CACHE

    fallback = None
    for account in GLOBAL_CACHE.ShMem.GetAllActiveSlotsData():
        if not account or not bool(getattr(account, 'IsSlotActive', False)):
            continue
        if not bool(getattr(account, 'IsAccount', False)):
            continue
        if bool(getattr(account, 'IsHero', False)) or bool(getattr(account, 'IsPet', False)):
            continue

        agent_data = getattr(account, 'AgentData', None)
        party_data = getattr(account, 'AgentPartyData', None)
        account_email = str(getattr(account, 'AccountEmail', '') or '')
        character_name = str(getattr(agent_data, 'CharacterName', '') or '')
        account_name = str(getattr(account, 'AccountName', '') or '')
        party_position = int(getattr(party_data, 'PartyPosition', -1) or -1)

        if assignment.account_email and account_email == assignment.account_email:
            return account
        if assignment.character_name and character_name and character_name == assignment.character_name:
            fallback = account
        elif assignment.account_name and account_name and account_name == assignment.account_name:
            fallback = account
        elif assignment.account_party_position >= 0 and party_position == assignment.account_party_position:
            fallback = account

    if fallback is not None and SameMapOrPartyAsAccount(fallback):
        return fallback
    return fallback


def _resolve_account_slot_assignment(assignment: FormationAssignment):
    from Py4GWCoreLib.GlobalCache import GLOBAL_CACHE

    party_position = int(assignment.account_party_position)
    if party_position <= LEADER_PARTY_POSITION:
        return None

    for account in GLOBAL_CACHE.ShMem.GetAllActiveSlotsData():
        if not account or not bool(getattr(account, 'IsSlotActive', False)):
            continue
        if not bool(getattr(account, 'IsAccount', False)):
            continue
        if bool(getattr(account, 'IsHero', False)) or bool(getattr(account, 'IsPet', False)):
            continue

        party_data = getattr(account, 'AgentPartyData', None)
        account_party_position = int(getattr(party_data, 'PartyPosition', -1) or -1)
        if account_party_position == party_position:
            return account

    return None


def _resolve_account_assignment_for_mode(assignment: FormationAssignment, target_mode: str):
    if normalize_target_mode(target_mode, default=TARGET_MODE_IDENTITY) == TARGET_MODE_PARTY_SLOT:
        return _resolve_account_slot_assignment(assignment)
    return _resolve_account_assignment(assignment)


def _account_label(account) -> str:
    agent_data = getattr(account, 'AgentData', None)
    return (
        str(getattr(agent_data, 'CharacterName', '') or '')
        or str(getattr(account, 'AccountName', '') or '')
        or str(getattr(account, 'AccountEmail', '') or '')
        or 'Account'
    )


def capture_assignment_offset(
    assignment: FormationAssignment,
    target_mode: str = TARGET_MODE_IDENTITY,
) -> tuple[bool, str]:
    if assignment.kind == ASSIGNMENT_UNASSIGNED:
        return False, f'{assignment.spot_label or "Unassigned spot"}: assign a target before capture.'

    from Py4GWCoreLib.Agent import Agent
    from Py4GWCoreLib.Map import Map
    from Py4GWCoreLib.Party import Party
    from Py4GWCoreLib.Player import Player

    if not Map.IsMapReady() or Map.IsMapLoading() or not Map.IsExplorable():
        return False, 'Map is not ready for capture.'
    if not Party.IsPartyLoaded():
        return False, 'Party is not loaded.'

    leader_id = int(Party.GetPartyLeaderID() or 0)
    if leader_id <= 0 or int(Player.GetAgentID() or 0) != leader_id:
        return False, 'Only the party leader can capture formation offsets.'
    if not Agent.IsValid(leader_id):
        return False, 'Party leader agent is not valid.'

    leader_x, leader_y, _leader_z = Agent.GetXYZ(leader_id)
    facing_angle = float(Agent.GetRotationAngle(leader_id) or 0.0)

    if assignment.kind == ASSIGNMENT_HERO:
        agent_id, label = _resolve_hero_assignment_for_mode(assignment, target_mode)
        if agent_id <= 0 or not Agent.IsValid(agent_id):
            return False, f'{label}: hero is not visible.'
        member_x, member_y, _member_z = Agent.GetXYZ(agent_id)
        assignment.offset_x, assignment.offset_y = inverse_rotate_offset(
            float(member_x) - float(leader_x),
            float(member_y) - float(leader_y),
            facing_angle,
        )
        return True, f'{label}: offset captured.'

    if assignment.kind == ASSIGNMENT_ACCOUNT:
        account = _resolve_account_assignment_for_mode(assignment, target_mode)
        if account is None:
            if normalize_target_mode(target_mode, default=TARGET_MODE_IDENTITY) == TARGET_MODE_PARTY_SLOT:
                return False, f'{_player_slot_label(assignment.account_party_position)}: account slot is empty.'
            return False, f'{assignment.display_name()}: account not found.'

        label = (
            _player_slot_label(assignment.account_party_position, _account_label(account))
            if normalize_target_mode(target_mode, default=TARGET_MODE_IDENTITY) == TARGET_MODE_PARTY_SLOT
            else _account_label(account)
        )
        agent_id = int(getattr(getattr(account, 'AgentData', None), 'AgentID', 0) or 0)
        if agent_id > 0 and Agent.IsValid(agent_id):
            member_x, member_y, _member_z = Agent.GetXYZ(agent_id)
        else:
            position = getattr(getattr(account, 'AgentData', None), 'Pos', None)
            member_x = float(getattr(position, 'x', 0.0) or 0.0)
            member_y = float(getattr(position, 'y', 0.0) or 0.0)
            if abs(member_x) <= 0.001 and abs(member_y) <= 0.001:
                return False, f'{label}: account position is unavailable.'

        assignment.offset_x, assignment.offset_y = inverse_rotate_offset(
            float(member_x) - float(leader_x),
            float(member_y) - float(leader_y),
            facing_angle,
        )
        return True, f'{label}: offset captured.'

    return False, f'{assignment.display_name()}: unknown assignment type {assignment.kind}.'


def _add_static_preflight_items(snapshot: FormationPreflightSnapshot, formation: PartyFormation) -> None:
    for index, assignment in enumerate(formation.assignments):
        spot_label = assignment_spot_label(assignment, index)
        if not bool(getattr(assignment, 'enabled', True)):
            snapshot.add_item(index, spot_label, assignment.display_name(), PREFLIGHT_STATUS_SKIPPED, 'Disabled spot.')
            continue
        if assignment.kind == ASSIGNMENT_UNASSIGNED:
            snapshot.add_item(index, spot_label, '', PREFLIGHT_STATUS_SKIPPED, 'No target assigned.')
            continue

        offset_warning = preflight_assignment_offset_warning(assignment)
        if offset_warning:
            snapshot.add_item(
                index,
                spot_label,
                assignment.display_name(),
                PREFLIGHT_STATUS_WARNING,
                offset_warning,
            )


def preflight_apply_snapshot(formation: PartyFormation) -> FormationPreflightSnapshot:
    snapshot = FormationPreflightSnapshot(counts=formation_preflight_counts(formation))
    for duplicate in formation_duplicate_target_groups(formation):
        snapshot.add_warning_note(f'Duplicate {duplicate.target_label}: {", ".join(duplicate.spot_labels)}')

    try:
        from HeroAI.utils import SameMapOrPartyAsAccount
        from Py4GWCoreLib.Agent import Agent
        from Py4GWCoreLib.GlobalCache import GLOBAL_CACHE
        from Py4GWCoreLib.Map import Map
        from Py4GWCoreLib.Party import Party
        from Py4GWCoreLib.Player import Player

        snapshot.runtime_checked = True

        if not Map.IsMapReady() or Map.IsMapLoading() or Map.IsInCinematic():
            snapshot.add_item(-1, 'Apply', '', PREFLIGHT_STATUS_SKIPPED, 'Map is not ready.')
            return snapshot
        if not Map.IsExplorable():
            snapshot.add_item(-1, 'Apply', '', PREFLIGHT_STATUS_SKIPPED, 'Current map is not explorable.')
            return snapshot
        if not Party.IsPartyLoaded():
            snapshot.add_item(-1, 'Apply', '', PREFLIGHT_STATUS_SKIPPED, 'Party is not loaded.')
            return snapshot

        leader_id = int(Party.GetPartyLeaderID() or 0)
        if leader_id <= 0 or int(Player.GetAgentID() or 0) != leader_id:
            snapshot.add_item(
                -1,
                'Apply',
                '',
                PREFLIGHT_STATUS_SKIPPED,
                'Only the party leader can apply party formations.',
            )
            return snapshot
        if not Agent.IsValid(leader_id):
            snapshot.add_item(-1, 'Apply', '', PREFLIGHT_STATUS_SKIPPED, 'Party leader agent is not valid.')
            return snapshot

        snapshot.runtime_ready = True
        leader_x, leader_y, _leader_z = Agent.GetXYZ(leader_id)
        facing_angle = float(Agent.GetRotationAngle(leader_id) or 0.0)
        target_mode = normalize_target_mode(formation.target_mode, default=TARGET_MODE_IDENTITY)
        party_slot_mode = target_mode == TARGET_MODE_PARTY_SLOT

        for index, assignment in enumerate(formation.assignments):
            spot_label = assignment_spot_label(assignment, index)
            if not assignment.enabled:
                snapshot.add_item(
                    index,
                    spot_label,
                    assignment.display_name(),
                    PREFLIGHT_STATUS_SKIPPED,
                    'Disabled spot.',
                )
                continue
            if assignment.kind == ASSIGNMENT_UNASSIGNED:
                snapshot.add_item(index, spot_label, '', PREFLIGHT_STATUS_SKIPPED, 'No target assigned.')
                continue

            offset_warning = preflight_assignment_offset_warning(assignment)
            if offset_warning and offset_warning != 'Offset is unusually large.':
                snapshot.add_item(
                    index,
                    spot_label,
                    assignment.display_name(),
                    PREFLIGHT_STATUS_WARNING,
                    offset_warning,
                )
                continue
            if offset_warning:
                snapshot.add_warning_note(f'{spot_label}: {offset_warning}')

            rotated_x, rotated_y = rotate_offset(float(assignment.offset_x), float(assignment.offset_y), facing_angle)
            target_x = float(leader_x) + rotated_x
            target_y = float(leader_y) + rotated_y

            if assignment.kind == ASSIGNMENT_HERO:
                agent_id, label = _resolve_hero_assignment_for_mode(assignment, target_mode)
                if agent_id <= 0:
                    message = (
                        f'{label}: hero slot is empty.'
                        if party_slot_mode
                        else f'{assignment.display_name()}: hero not found.'
                    )
                    snapshot.add_item(index, spot_label, label, PREFLIGHT_STATUS_SKIPPED, message)
                    continue
                if not Agent.IsValid(agent_id):
                    snapshot.add_item(
                        index,
                        spot_label,
                        label,
                        PREFLIGHT_STATUS_SKIPPED,
                        f'{label}: hero agent is not valid.',
                    )
                    continue
                if Agent.IsDead(agent_id):
                    snapshot.add_item(index, spot_label, label, PREFLIGHT_STATUS_SKIPPED, f'{label}: hero is dead.')
                    continue

                snapshot.add_item(
                    index,
                    spot_label,
                    label,
                    PREFLIGHT_STATUS_WOULD_TARGET,
                    f'{label}: hero would be flagged.',
                    target_x,
                    target_y,
                )
                continue

            if assignment.kind == ASSIGNMENT_ACCOUNT:
                account = _resolve_account_assignment_for_mode(assignment, target_mode)
                if account is None:
                    message = (
                        f'{_player_slot_label(assignment.account_party_position)}: account slot is empty.'
                        if party_slot_mode
                        else f'{assignment.display_name()}: account not found.'
                    )
                    snapshot.add_item(
                        index,
                        spot_label,
                        assignment.display_name(),
                        PREFLIGHT_STATUS_SKIPPED,
                        message,
                    )
                    continue
                label = (
                    _player_slot_label(assignment.account_party_position, _account_label(account))
                    if party_slot_mode
                    else _account_label(account)
                )
                if not bool(getattr(account, 'IsSlotActive', False)):
                    snapshot.add_item(
                        index,
                        spot_label,
                        label,
                        PREFLIGHT_STATUS_SKIPPED,
                        f'{label}: account slot is inactive.',
                    )
                    continue
                if not SameMapOrPartyAsAccount(account):
                    snapshot.add_item(
                        index,
                        spot_label,
                        label,
                        PREFLIGHT_STATUS_SKIPPED,
                        f'{label}: account is not in the same map or party.',
                    )
                    continue
                if int(getattr(getattr(account, 'AgentPartyData', None), 'PartyID', 0) or 0) != int(
                    Party.GetPartyID() or 0
                ):
                    snapshot.add_item(
                        index,
                        spot_label,
                        label,
                        PREFLIGHT_STATUS_SKIPPED,
                        f'{label}: account is not in the current party.',
                    )
                    continue

                agent_data = getattr(account, 'AgentData', None)
                agent_id = int(getattr(agent_data, 'AgentID', 0) or 0)
                if agent_id <= 0:
                    snapshot.add_item(
                        index,
                        spot_label,
                        label,
                        PREFLIGHT_STATUS_SKIPPED,
                        f'{label}: account agent id is missing.',
                    )
                    continue
                if Agent.IsValid(agent_id) and Agent.IsDead(agent_id):
                    snapshot.add_item(
                        index,
                        spot_label,
                        label,
                        PREFLIGHT_STATUS_SKIPPED,
                        f'{label}: account is dead.',
                    )
                    continue
                if not Agent.IsValid(agent_id):
                    health = getattr(agent_data, 'Health', None)
                    current_health = float(getattr(health, 'Current', 0.0) or 0.0)
                    if current_health <= 0.0:
                        snapshot.add_item(
                            index,
                            spot_label,
                            label,
                            PREFLIGHT_STATUS_SKIPPED,
                            f'{label}: account health is unavailable or dead.',
                        )
                        continue

                options = GLOBAL_CACHE.ShMem.GetHeroAIOptionsFromEmail(str(getattr(account, 'AccountEmail', '') or ''))
                if options is None:
                    snapshot.add_item(
                        index,
                        spot_label,
                        label,
                        PREFLIGHT_STATUS_SKIPPED,
                        f'{label}: HeroAI options are unavailable.',
                    )
                    continue
                if not bool(getattr(options, 'Following', False)):
                    snapshot.add_item(
                        index,
                        spot_label,
                        label,
                        PREFLIGHT_STATUS_SKIPPED,
                        f'{label}: HeroAI following is disabled.',
                    )
                    continue

                snapshot.add_item(
                    index,
                    spot_label,
                    label,
                    PREFLIGHT_STATUS_WOULD_TARGET,
                    f'{label}: account flag would be set.',
                    target_x,
                    target_y,
                )
                continue

            snapshot.add_item(
                index,
                spot_label,
                assignment.display_name(),
                PREFLIGHT_STATUS_SKIPPED,
                f'{assignment.display_name()}: unknown assignment type {assignment.kind}.',
            )

        return snapshot
    except Exception as exc:
        snapshot.add_warning_note(f'Preview unavailable: {exc}')
        if not snapshot.items:
            _add_static_preflight_items(snapshot, formation)
        return snapshot


def apply_formation(formation: PartyFormation) -> FormationApplyResult:
    from HeroAI.utils import SameMapOrPartyAsAccount
    from Py4GWCoreLib.Agent import Agent
    from Py4GWCoreLib.GlobalCache import GLOBAL_CACHE
    from Py4GWCoreLib.Map import Map
    from Py4GWCoreLib.Party import Party
    from Py4GWCoreLib.Player import Player

    result = FormationApplyResult()

    if not Map.IsMapReady() or Map.IsMapLoading() or Map.IsInCinematic():
        result.add_skipped('Map is not ready.')
        return result
    if not Map.IsExplorable():
        result.add_skipped('Current map is not explorable.')
        return result
    if not Party.IsPartyLoaded():
        result.add_skipped('Party is not loaded.')
        return result

    leader_id = int(Party.GetPartyLeaderID() or 0)
    if leader_id <= 0 or int(Player.GetAgentID() or 0) != leader_id:
        result.add_skipped('Only the party leader can apply party formations.')
        return result
    if not Agent.IsValid(leader_id):
        result.add_skipped('Party leader agent is not valid.')
        return result

    leader_x, leader_y, _leader_z = Agent.GetXYZ(leader_id)
    facing_angle = float(Agent.GetRotationAngle(leader_id) or 0.0)
    target_mode = normalize_target_mode(formation.target_mode, default=TARGET_MODE_IDENTITY)
    party_slot_mode = target_mode == TARGET_MODE_PARTY_SLOT

    for assignment in formation.assignments:
        if not assignment.enabled:
            continue
        if assignment.kind == ASSIGNMENT_UNASSIGNED:
            continue

        rotated_x, rotated_y = rotate_offset(float(assignment.offset_x), float(assignment.offset_y), facing_angle)
        target_x = float(leader_x) + rotated_x
        target_y = float(leader_y) + rotated_y

        if assignment.kind == ASSIGNMENT_HERO:
            agent_id, label = _resolve_hero_assignment_for_mode(assignment, target_mode)
            if agent_id <= 0:
                message = (
                    f'{label}: hero slot is empty.'
                    if party_slot_mode
                    else f'{assignment.display_name()}: hero not found.'
                )
                result.add_skipped(message)
                continue
            if not Agent.IsValid(agent_id):
                result.add_skipped(f'{label}: hero agent is not valid.')
                continue
            if Agent.IsDead(agent_id):
                result.add_skipped(f'{label}: hero is dead.')
                continue

            Party.Heroes.FlagHero(agent_id, target_x, target_y)
            result.add_applied(f'{label}: hero flagged.')
            continue

        if assignment.kind == ASSIGNMENT_ACCOUNT:
            account = _resolve_account_assignment_for_mode(assignment, target_mode)
            if account is None:
                message = (
                    f'{_player_slot_label(assignment.account_party_position)}: account slot is empty.'
                    if party_slot_mode
                    else f'{assignment.display_name()}: account not found.'
                )
                result.add_skipped(message)
                continue
            label = (
                _player_slot_label(assignment.account_party_position, _account_label(account))
                if party_slot_mode
                else _account_label(account)
            )
            if not bool(getattr(account, 'IsSlotActive', False)):
                result.add_skipped(f'{label}: account slot is inactive.')
                continue
            if not SameMapOrPartyAsAccount(account):
                result.add_skipped(f'{label}: account is not in the same map or party.')
                continue
            if int(getattr(getattr(account, 'AgentPartyData', None), 'PartyID', 0) or 0) != int(
                Party.GetPartyID() or 0
            ):
                result.add_skipped(f'{label}: account is not in the current party.')
                continue

            agent_data = getattr(account, 'AgentData', None)
            agent_id = int(getattr(agent_data, 'AgentID', 0) or 0)
            if agent_id <= 0:
                result.add_skipped(f'{label}: account agent id is missing.')
                continue
            if Agent.IsValid(agent_id) and Agent.IsDead(agent_id):
                result.add_skipped(f'{label}: account is dead.')
                continue
            if not Agent.IsValid(agent_id):
                health = getattr(agent_data, 'Health', None)
                current_health = float(getattr(health, 'Current', 0.0) or 0.0)
                if current_health <= 0.0:
                    result.add_skipped(f'{label}: account health is unavailable or dead.')
                    continue

            options = GLOBAL_CACHE.ShMem.GetHeroAIOptionsFromEmail(str(getattr(account, 'AccountEmail', '') or ''))
            if options is None:
                result.add_skipped(f'{label}: HeroAI options are unavailable.')
                continue
            if not bool(getattr(options, 'Following', False)):
                result.add_skipped(f'{label}: HeroAI following is disabled.')
                continue

            options.FlagPos.x = target_x
            options.FlagPos.y = target_y
            options.FlagPosX = target_x
            options.FlagPosY = target_y
            options.FlagFacingAngle = facing_angle
            options.IsFlagged = True
            result.add_applied(f'{label}: account flag set.')
            continue

        result.add_skipped(f'{assignment.display_name()}: unknown assignment type {assignment.kind}.')

    return result


def clear_formation(formation: PartyFormation) -> FormationApplyResult:
    from HeroAI.utils import SameMapOrPartyAsAccount
    from Py4GWCoreLib.Agent import Agent
    from Py4GWCoreLib.GlobalCache import GLOBAL_CACHE
    from Py4GWCoreLib.Map import Map
    from Py4GWCoreLib.Party import Party
    from Py4GWCoreLib.Player import Player

    result = FormationApplyResult()

    if not Map.IsMapReady() or Map.IsMapLoading() or Map.IsInCinematic():
        result.add_skipped('Map is not ready.')
        return result
    if not Map.IsExplorable():
        result.add_skipped('Current map is not explorable.')
        return result
    if not Party.IsPartyLoaded():
        result.add_skipped('Party is not loaded.')
        return result

    leader_id = int(Party.GetPartyLeaderID() or 0)
    if leader_id <= 0 or int(Player.GetAgentID() or 0) != leader_id:
        result.add_skipped('Only the party leader can clear party formations.')
        return result

    target_mode = normalize_target_mode(formation.target_mode, default=TARGET_MODE_IDENTITY)
    party_slot_mode = target_mode == TARGET_MODE_PARTY_SLOT

    for assignment in formation.assignments:
        if not assignment.enabled:
            continue
        if assignment.kind == ASSIGNMENT_UNASSIGNED:
            continue

        if assignment.kind == ASSIGNMENT_HERO:
            agent_id, hero_position, label = _resolve_hero_assignment_with_position_for_mode(assignment, target_mode)
            if agent_id <= 0:
                message = (
                    f'{label}: hero slot is empty.'
                    if party_slot_mode
                    else f'{assignment.display_name()}: hero not found.'
                )
                result.add_skipped(message)
                continue
            if hero_position <= 0:
                result.add_skipped(f'{label}: hero party position is unavailable.')
                continue
            if not Agent.IsValid(agent_id):
                result.add_skipped(f'{label}: hero agent is not valid.')
                continue
            if Agent.IsDead(agent_id):
                result.add_skipped(f'{label}: hero is dead.')
                continue

            Party.Heroes.UnflagHero(hero_position)
            result.add_applied(f'{label}: hero flag cleared.')
            continue

        if assignment.kind == ASSIGNMENT_ACCOUNT:
            account = _resolve_account_assignment_for_mode(assignment, target_mode)
            if account is None:
                message = (
                    f'{_player_slot_label(assignment.account_party_position)}: account slot is empty.'
                    if party_slot_mode
                    else f'{assignment.display_name()}: account not found.'
                )
                result.add_skipped(message)
                continue
            label = (
                _player_slot_label(assignment.account_party_position, _account_label(account))
                if party_slot_mode
                else _account_label(account)
            )
            if not bool(getattr(account, 'IsSlotActive', False)):
                result.add_skipped(f'{label}: account slot is inactive.')
                continue
            if not SameMapOrPartyAsAccount(account):
                result.add_skipped(f'{label}: account is not in the same map or party.')
                continue
            if int(getattr(getattr(account, 'AgentPartyData', None), 'PartyID', 0) or 0) != int(
                Party.GetPartyID() or 0
            ):
                result.add_skipped(f'{label}: account is not in the current party.')
                continue

            options = GLOBAL_CACHE.ShMem.GetHeroAIOptionsFromEmail(str(getattr(account, 'AccountEmail', '') or ''))
            if options is None:
                result.add_skipped(f'{label}: HeroAI options are unavailable.')
                continue

            options.IsFlagged = False
            options.FlagPos.x = 0.0
            options.FlagPos.y = 0.0
            options.FlagPosX = 0.0
            options.FlagPosY = 0.0
            options.FlagFacingAngle = 0.0
            result.add_applied(f'{label}: account flag cleared.')
            continue

        result.add_skipped(f'{assignment.display_name()}: unknown assignment type {assignment.kind}.')

    return result

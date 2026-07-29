"""Static guards that keep V2 out of the production runtime path."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_PROTOCOL_ROOTS = (
    ROOT / "app" / "runtime",
    ROOT / "app" / "transport",
    ROOT / "app" / "bridge",
    ROOT / "contracts" / "v3",
    ROOT / "frontend" / "src" / "runtime",
)


def production_protocol_sources():
    for root in PRODUCTION_PROTOCOL_ROOTS:
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx"}:
                continue
            if path.name.endswith((".test.ts", ".test.tsx")):
                continue
            yield path


def test_removed_v2_modules_do_not_exist():
    removed = (
        ROOT / "app" / "transport" / "protocol.py",
        ROOT / "app" / "avatar" / "protocol.py",
        ROOT / "contracts" / "v3" / "compat.py",
        ROOT / "contracts" / "v3" / "payloads.py",
        ROOT / "frontend" / "src" / "runtime" / "protocol.ts",
        ROOT / "frontend" / "src" / "runtime" / "compat.ts",
    )
    assert not [path for path in removed if path.exists()]


def test_production_protocol_sources_have_no_v2_types_or_wire_events():
    banned = (
        "InboundMessage",
        "OutboundMessage",
        "parse_inbound",
        "_envelope_to_inbound",
        "dispatchV2",
        "assistant_message",
        "character_update",
        "runtime_status",
        "tts_start",
        "tts_audio",
        "tts_end",
        "text_input",
        "audio_input",
        "audio_end",
        "set-model-and-conf",
        "_send_init_conf",
        "protocolVersion: '2.0'",
        'protocolVersion: "2.0"',
    )
    violations = []
    for path in production_protocol_sources():
        source = path.read_text("utf-8")
        for token in banned:
            if token in source:
                violations.append(f"{path.relative_to(ROOT)}: {token}")
        if re.search(r"\bV2\b", source, re.IGNORECASE):
            violations.append(f"{path.relative_to(ROOT)}: V2")
    assert violations == []


def test_business_runtime_does_not_read_removed_presentation_fields():
    violations = []
    field_access = re.compile(
        r"""(?:get\(\s*|[{\[,]\s*|\.)(?:["'])?(tone|gesture)(?:["'])?\s*(?:[,):\]])""",
        re.IGNORECASE,
    )
    roots = (
        ROOT / "app" / "runtime",
        ROOT / "app" / "transport",
        ROOT / "contracts" / "v3",
        ROOT / "frontend" / "src" / "runtime",
        ROOT / "app" / "interfaces",
    )
    for root in roots:
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx"}:
                continue
            if path.name.endswith((".test.ts", ".test.tsx")):
                continue
            for line_number, line in enumerate(
                path.read_text("utf-8").splitlines(),
                start=1,
            ):
                if field_access.search(line):
                    violations.append(
                        f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}"
                    )
    assert violations == []


def test_avatar_motion_categories_use_v3_behavior_name():
    source = (
        ROOT / "app" / "avatar" / "motion_manager.py"
    ).read_text("utf-8")
    assert '"gesture"' not in source
    assert 'category: str = "behavior"' in source


def test_only_canonical_v3_envelope_version_is_supported():
    envelope = (
        ROOT / "contracts" / "v3" / "envelope.py"
    ).read_text("utf-8")
    session = (
        ROOT / "app" / "transport" / "session.py"
    ).read_text("utf-8")
    client = (
        ROOT / "frontend" / "src" / "runtime" / "client.ts"
    ).read_text("utf-8")

    assert 'PROTOCOL_VERSION = "3.0"' in envelope
    assert "SUPPORTED_VERSIONS = frozenset({PROTOCOL_VERSION})" in envelope
    assert "EventRegistry.parse" in session
    assert "parseRuntimeEvent" in client

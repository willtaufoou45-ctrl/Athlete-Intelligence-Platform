"""Athlete Intelligence schema and verified case-study seeds."""

from __future__ import annotations

import json
import sqlite3
import uuid


STATE_TYPES = ("offseason", "preseason", "in_season", "postseason", "time_away", "return_reentry")
RECORD_TYPES = (
    "trait", "observation", "limitation", "hypothesis", "focus", "intervention",
    "response", "relationship", "open_question",
)
RECORD_STATUSES = ("proposed", "active", "confirmed", "superseded", "resolved", "rejected", "historical")
CONFIDENCE_LEVELS = ("low", "moderate", "high")
EPISTEMIC_CLASSES = (
    "fact", "coach_observation", "athlete_report", "hypothesis",
    "interpretation", "unknown", "derived_analysis",
)
EVIDENCE_TYPES = (
    "sprint_result", "sprint_session", "workout_session", "exercise_performance",
    "force_test", "coach_observation", "training_exposure",
)
EVIDENCE_RELATIONSHIPS = (
    "supports", "contradicts", "motivated_by", "response_to", "resolved_by",
    "contextualizes",
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS canonical_athletes (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL CHECK(length(trim(display_name)) > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    archived_at TEXT
);
CREATE TABLE IF NOT EXISTS athlete_external_identities (
    id TEXT PRIMARY KEY,
    athlete_id TEXT NOT NULL REFERENCES canonical_athletes(id) ON DELETE RESTRICT,
    source_system TEXT NOT NULL,
    source_entity_type TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    source_display_name TEXT,
    verified_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_system, source_entity_type, source_record_id)
);
CREATE TABLE IF NOT EXISTS athlete_states (
    id TEXT PRIMARY KEY,
    athlete_id TEXT NOT NULL REFERENCES canonical_athletes(id) ON DELETE RESTRICT,
    state_type TEXT NOT NULL CHECK(state_type IN ('offseason','preseason','in_season','postseason','time_away','return_reentry')),
    label TEXT,
    effective_from TEXT,
    effective_to TEXT,
    attributes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK(effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from)
);
CREATE TABLE IF NOT EXISTS intelligence_records (
    id TEXT PRIMARY KEY,
    athlete_id TEXT NOT NULL REFERENCES canonical_athletes(id) ON DELETE RESTRICT,
    type TEXT NOT NULL CHECK(type IN ('trait','observation','limitation','hypothesis','focus','intervention','response','relationship','open_question')),
    epistemic_class TEXT CHECK(epistemic_class IS NULL OR epistemic_class IN ('fact','coach_observation','athlete_report','hypothesis','interpretation','unknown','derived_analysis')),
    statement TEXT NOT NULL CHECK(length(trim(statement)) > 0),
    status TEXT NOT NULL CHECK(status IN ('proposed','active','confirmed','superseded','resolved','rejected','historical')),
    confidence TEXT CHECK(confidence IS NULL OR confidence IN ('low','moderate','high')),
    first_observed_at TEXT,
    last_confirmed_at TEXT,
    effective_from TEXT,
    effective_to TEXT,
    freshness_review_at TEXT,
    supersedes_record_id TEXT REFERENCES intelligence_records(id) ON DELETE RESTRICT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    athlete_id TEXT NOT NULL REFERENCES canonical_athletes(id) ON DELETE RESTRICT,
    evidence_type TEXT NOT NULL CHECK(evidence_type IN ('sprint_result','sprint_session','workout_session','exercise_performance','force_test','coach_observation','training_exposure')),
    source_system TEXT NOT NULL,
    source_entity_type TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    observed_at TEXT,
    observed_date TEXT,
    summary TEXT,
    source_version_or_digest TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_system, source_entity_type, source_record_id)
);
CREATE TABLE IF NOT EXISTS intelligence_evidence_links (
    intelligence_record_id TEXT NOT NULL REFERENCES intelligence_records(id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL REFERENCES evidence(id) ON DELETE RESTRICT,
    relationship_type TEXT NOT NULL CHECK(relationship_type IN ('supports','contradicts','motivated_by','response_to','resolved_by','contextualizes')),
    note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(intelligence_record_id, evidence_id)
);
CREATE INDEX IF NOT EXISTS idx_external_identity_athlete ON athlete_external_identities(athlete_id);
CREATE INDEX IF NOT EXISTS idx_athlete_states_history ON athlete_states(athlete_id, effective_from, created_at);
CREATE INDEX IF NOT EXISTS idx_intelligence_records_athlete ON intelligence_records(athlete_id, status, type);
CREATE INDEX IF NOT EXISTS idx_evidence_athlete ON evidence(athlete_id, observed_date, observed_at);
CREATE INDEX IF NOT EXISTS idx_intelligence_links_evidence ON intelligence_evidence_links(evidence_id);
"""


def new_id() -> str:
    return str(uuid.uuid4())


def json_text(value: dict | None) -> str | None:
    return json.dumps(value, sort_keys=True) if value is not None else None


def seed_rigby_case_study(connection: sqlite3.Connection) -> str | None:
    """Idempotently seed Case Study 001 only when Sprint athlete 9 is verified locally."""
    sprint_athlete = connection.execute("SELECT name FROM athletes WHERE id=9").fetchone()
    if not sprint_athlete or sprint_athlete["name"].strip().casefold() != "rigby young":
        return None

    mapping = connection.execute(
        """SELECT athlete_id FROM athlete_external_identities
           WHERE source_system='sprint_capture' AND source_entity_type='athlete' AND source_record_id='9'"""
    ).fetchone()
    if mapping:
        return mapping["athlete_id"]

    athlete_id = new_id()
    connection.execute(
        "INSERT INTO canonical_athletes(id,display_name) VALUES (?,?)", (athlete_id, "Rigby Young")
    )
    for system, entity, record_id, display in (
        ("sprint_capture", "athlete", "9", "Rigby young"),
        ("repbook", "lifter", "5", "Rigby"),
    ):
        connection.execute(
            """INSERT INTO athlete_external_identities(
                   id,athlete_id,source_system,source_entity_type,source_record_id,source_display_name,verified_at
               ) VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
            (new_id(), athlete_id, system, entity, record_id, display),
        )

    connection.execute(
        """INSERT INTO athlete_states(id,athlete_id,state_type,label,effective_from,attributes)
           VALUES (?,?,?,?,?,?)""",
        (
            new_id(), athlete_id, "in_season", "Current as of August 2026", None,
            json_text({
                "as_of_month": "2026-08", "sport": "football", "grade": "10th",
                "roles": ["quarterback", "athlete"], "age_as_of_month": 15,
                "training_age": "medium/high", "summit_offseason_training_began_month": "2026-01",
                "effective_from_precision": "month_unknown_day",
            }),
        ),
    )

    records: dict[str, str] = {}
    definitions = (
        ("natural_speed", "trait", "Natural speed.", "confirmed", "high"),
        ("natural_strength", "trait", "Natural strength.", "confirmed", "high"),
        ("general_athleticism", "trait", "High general athletic ability.", "confirmed", "high"),
        ("stiffness", "observation", "Rigby has demonstrated stiffness during sprinting and training.", "confirmed", "high"),
        ("horizontal_projection_limit", "limitation", "Historically had difficulty maintaining horizontal projection during acceleration.", "historical", "high"),
        ("torso_position_limit", "limitation", "Historically tended to leave acceleration posture early and raise his torso too soon.", "historical", "high"),
        ("horizontal_projection_focus", "focus", "Improve horizontal projection during acceleration.", "historical", "high"),
        ("torso_position_focus", "focus", "Maintain appropriate torso position during acceleration.", "historical", "high"),
        ("mechanics_response", "response", "Sprint mechanics improved.", "confirmed", "high"),
        ("consistency_response", "response", "Sprint consistency improved.", "confirmed", "high"),
        ("sprint_performance_response", "response", "Historical external evidence indicates 10-yard performance improved from approximately 1.30 seconds to an approximately 1.23-second PR.", "confirmed", "moderate"),
        ("drive_focus", "focus", "Relative concentric impulse (coach-facing label: Drive) was a force-development priority.", "superseded", "high"),
        ("posterior_chain", "intervention", "Posterior-chain development was emphasized; causation of force changes is not asserted.", "historical", "high"),
        ("drive_response", "response", "Historical external evidence indicates Drive T-score improved approximately 43 to 52 between March and August 2026.", "confirmed", "moderate"),
        ("load_focus", "focus", "Current force priority is braking rate of force development (coach-facing label: Load).", "active", "high"),
        ("open_question", "open_question", "Do Rigby's offseason sprint improvements persist during the competitive season?", "active", "high"),
    )
    for key, record_type, statement, status, confidence in definitions:
        record_id = new_id()
        records[key] = record_id
        connection.execute(
            """INSERT INTO intelligence_records(
                   id,athlete_id,type,statement,status,confidence,created_by
               ) VALUES (?,?,?,?,?,?,?)""",
            (record_id, athlete_id, record_type, statement, status, confidence, "coach_verified_case_study_001"),
        )

    updated_drive = new_id()
    connection.execute(
        """INSERT INTO intelligence_records(
               id,athlete_id,type,statement,status,confidence,supersedes_record_id,created_by
           ) VALUES (?,?,?,?,?,?,?,?)""",
        (
            updated_drive, athlete_id, "relationship",
            "Drive is no longer considered Rigby's primary force-development focus.",
            "confirmed", "high", records["drive_focus"], "coach_verified_case_study_001",
        ),
    )

    evidence: dict[str, str] = {}
    evidence_definitions = [
        ("repbook_session_20", "workout_session", "repbook", "workout_session", "20", "2026-08-10", "Completed In-Season Load - Day 1 workout.", {"logged_sets": 15, "status": "completed"}),
    ]
    for session_id, observed_date in ((6, "2026-08-04"), (12, "2026-08-10")):
        attempts = connection.execute(
            """SELECT id FROM sprint_attempts
               WHERE session_id=? AND athlete_id=9 ORDER BY captured_at,id""", (session_id,)
        ).fetchall()
        if attempts:
            evidence_definitions.append(
                (f"sprint_session_{session_id}", "sprint_session", "sprint_capture",
                 "sprint_capture_session", str(session_id), observed_date,
                 "Verified 10-yard sprint session containing Rigby's results.", None)
            )
            for attempt in attempts:
                evidence_definitions.append(
                    (f"sprint_result_{attempt['id']}", "sprint_result", "sprint_capture",
                     "sprint_attempt", str(attempt["id"]), observed_date,
                     "Verified 10-yard sprint result; raw value remains in Sprint Capture.", None)
                )
    for key, evidence_type, system, entity, record_id, observed_date, summary, metadata in evidence_definitions:
        evidence_id = new_id()
        evidence[key] = evidence_id
        connection.execute(
            """INSERT INTO evidence(
                   id,athlete_id,evidence_type,source_system,source_entity_type,source_record_id,
                   observed_date,summary,metadata
               ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (evidence_id, athlete_id, evidence_type, system, entity, record_id, observed_date, summary, json_text(metadata)),
        )

    links = [
        ("posterior_chain", "repbook_session_20", "supports", "The workout session is source-owned by Repbook; no set data is duplicated here."),
    ]
    if "sprint_session_6" in evidence:
        links.append(("open_question", "sprint_session_6", "motivated_by", "Verified in-system sprint evidence available for longitudinal monitoring."))
    if "sprint_session_12" in evidence:
        links.append(("open_question", "sprint_session_12", "motivated_by", "Verified in-system sprint evidence available for longitudinal monitoring."))
    for record_key, evidence_key, relationship, note in links:
        connection.execute(
            """INSERT INTO intelligence_evidence_links(
                   intelligence_record_id,evidence_id,relationship_type,note
               ) VALUES (?,?,?,?)""",
            (records[record_key], evidence[evidence_key], relationship, note),
        )
    return athlete_id


BRODY_FORCE_SHEET_ID = "1yKWG0mNNjdYw9HTkXhtGuW3M5tH7KGtXfNE1Q7QWxO0"
BRODY_FORCE_SCANS = (
    ("2025-07-27", "2ad8d6c4-4f57-4583-8e5b-c5b50e319839"),
    ("2025-08-17", "5c9a33f0-b121-4c06-9825-e2376a64d220"),
    ("2025-09-10", "01df6660-e767-462c-b57d-252af26472e0"),
    ("2025-10-26", "13c6cb11-5757-433d-a4d8-d44fdce8fc92"),
    ("2026-03-12", "2882330c-13b9-45ca-8aac-ff97813e4912"),
    ("2026-04-19", "8805cba3-0a57-416b-9805-0c7f01917fda"),
    ("2026-04-19", "86a67012-7152-44dd-a4c9-63227b4b2976"),
    ("2026-05-17", "a050255f-8569-4629-b1a4-339fae8b5d25"),
    ("2026-06-18", "825cf54a-fd85-4046-8d5e-0b49daac0f8d"),
    ("2026-07-11", "2cfac186-4669-4c9b-a700-fe9775260f64"),
    ("2026-08-04", "84b951ef-f632-43da-8c8d-71463d08282b"),
)


def seed_brody_case_study(connection: sqlite3.Connection) -> str | None:
    """Idempotently seed Case Study 002 from verified Sprint and force identities."""
    sprint_athlete = connection.execute("SELECT name FROM athletes WHERE id=7").fetchone()
    group_member = connection.execute(
        "SELECT 1 FROM training_group_members WHERE group_id=3 AND athlete_id=7"
    ).fetchone()
    if not sprint_athlete or sprint_athlete["name"].strip() != "Brody Bradford" or not group_member:
        return None

    mapping = connection.execute(
        """SELECT athlete_id FROM athlete_external_identities
           WHERE source_system='sprint_capture' AND source_entity_type='athlete'
             AND source_record_id='7'"""
    ).fetchone()
    if mapping:
        return mapping["athlete_id"]

    expected_attempts = {
        19: (5, 1320), 20: (5, 1330), 21: (5, 1270), 22: (5, 1290), 23: (5, 1260),
        184: (16, 1340), 185: (16, 1360), 186: (16, 1340), 187: (16, 1320),
    }
    sessions = {
        row["id"]: row for row in connection.execute(
            "SELECT id,distance,unit,session_date FROM sprint_capture_sessions WHERE id IN (5,16)"
        )
    }
    if (
        set(sessions) != {5, 16}
        or (sessions[5]["distance"], sessions[5]["unit"], sessions[5]["session_date"])
        != ("15", "yards", "2026-08-04")
        or (sessions[16]["distance"], sessions[16]["unit"], sessions[16]["session_date"])
        != ("10", "yards", "2026-08-13")
    ):
        raise ValueError("Verified Brody Sprint Capture sessions are unavailable or changed.")
    attempts = {
        row["id"]: (row["session_id"], row["elapsed_ms"])
        for row in connection.execute(
            """SELECT id,session_id,elapsed_ms FROM sprint_attempts
               WHERE athlete_id=7 AND id IN (19,20,21,22,23,184,185,186,187)"""
        )
    }
    if attempts != expected_attempts:
        raise ValueError("Verified Brody Sprint Capture attempts are unavailable or changed.")

    athlete_id = new_id()
    connection.execute(
        "INSERT INTO canonical_athletes(id,display_name) VALUES (?,?)", (athlete_id, "Brody Bradford")
    )
    connection.execute(
        """INSERT INTO athlete_external_identities(
               id,athlete_id,source_system,source_entity_type,source_record_id,
               source_display_name,verified_at
           ) VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
        (new_id(), athlete_id, "sprint_capture", "athlete", "7", "Brody Bradford"),
    )

    states = (
        ("offseason", "Offseason 1 · approximate Jul–Oct 2025", "2025-07", "2025-10", {
            "sport": "basketball", "roles": ["guard", "athlete"], "training_age": "low",
            "ace_relationship_began_month": "2025-07",
            "effective_date_precision": "month_unknown_day",
        }),
        ("in_season", "Basketball season · approximate Oct 2025–Mar 2026", "2025-10", "2026-03", {
            "sport": "basketball", "roles": ["guard", "athlete"], "basketball_active": True,
            "regular_ace_strength_programming": False, "regular_force_sprint_testing": False,
            "effective_date_precision": "month_unknown_day",
        }),
        ("offseason", "Offseason 2 · current as of August 2026", "2026-03", None, {
            "sport": "basketball", "roles": ["guard", "athlete"], "age_as_of_month": 16,
            "as_of_month": "2026-08", "training_age": "medium/high",
            "club_basketball_active": True, "tournaments_active": True,
            "ace_training_focus": ["acceleration", "change_of_direction"],
            "independent_training_plan": "coach_coordinated",
            "effective_date_precision": "month_unknown_day",
        }),
    )
    for state_type, label, effective_from, effective_to, attributes in states:
        connection.execute(
            """INSERT INTO athlete_states(
                   id,athlete_id,state_type,label,effective_from,effective_to,attributes
               ) VALUES (?,?,?,?,?,?,?)""",
            (new_id(), athlete_id, state_type, label, effective_from, effective_to, json_text(attributes)),
        )

    records: dict[str, str] = {}
    record_definitions = (
        ("early_strength_speed", "trait", "coach_observation", "Brody demonstrated meaningful physical strength and speed early in the coaching relationship.", "historical", "high", "2025-07", None, "2025-07", "2025-10"),
        ("coordination_limit", "limitation", "coach_observation", "Early in training, Brody had difficulty with coordination, rhythm, sequencing, and quickly learning new movement patterns.", "historical", "high", "2025-07", None, "2025-07", "2025-10"),
        ("independent_training", "trait", "coach_observation", "Brody prefers to train independently and historically accumulated substantial training outside ACE sessions.", "confirmed", "moderate", "2025-07", None, "2025-07", None),
        ("movement_focus", "focus", "coach_observation", "Offseason 1 acceleration and change-of-direction work emphasized rhythm, sequencing, center-of-mass placement, projection angles, and movement fundamentals.", "historical", "high", "2025-07", None, "2025-07", "2025-10"),
        ("drive_intervention", "intervention", "coach_observation", "Offseason 1 included approximately one month emphasizing Drive (Relative Concentric Impulse); causation of later changes is not asserted.", "historical", "high", "2025-07", None, "2025-07", "2025-10"),
        ("load_intervention", "intervention", "coach_observation", "Offseason 1 included approximately two months emphasizing Load (Average Braking RFD); causation of later changes is not asserted.", "historical", "high", "2025-07", None, "2025-07", "2025-10"),
        ("fatigue", "observation", "coach_observation", "Brody displayed signs of fatigue during Offseason 1.", "historical", "moderate", "2025-07", None, "2025-07", "2025-10"),
        ("exposure_recovery_hypothesis", "relationship", "hypothesis", "Brody's total training exposure may have exceeded his ability to recover and contributed to the late-Offseason-1 performance decline.", "active", "moderate", "2026-03", None, "2025-07", "2025-10"),
        ("season_evidence_gap", "observation", "unknown", "No regular ACE force or sprint testing is available for Brody during the primary 2025–26 basketball-season period.", "historical", "high", "2026-03", None, "2025-10", "2026-03"),
        ("coach_learning", "observation", "interpretation", "After reviewing Offseason 1, the coach recognized that ACE-prescribed training represented only part of Brody's total training exposure.", "confirmed", "high", "2026-03", None, "2025-07", "2025-10"),
        ("program_lower", "intervention", "coach_observation", "The coach programmed Brody's independent lower-body training during Offseason 2.", "active", "high", "2026-03", None, "2026-03", None),
        ("review_upper", "intervention", "coach_observation", "The coach reviewed Brody's independent upper-body training during Offseason 2.", "active", "high", "2026-03", None, "2026-03", None),
        ("ace_accel_cod", "intervention", "coach_observation", "ACE sessions emphasized acceleration and change of direction during Offseason 2.", "active", "high", "2026-03", None, "2026-03", None),
        ("coordinate_environment", "intervention", "coach_observation", "The athlete and coach coordinated basketball, independent lifting, and ACE training more deliberately during Offseason 2.", "active", "high", "2026-03", None, "2026-03", None),
        ("avoid_decline_focus", "focus", "coach_observation", "Avoid repeating the late-offseason performance decline seen in 2025 while continuing physical development.", "active", "high", "2026-03", None, "2026-03", None),
        ("jump_decline", "response", "fact", "Brody's recorded jump height declined across Offseason 1 from approximately 20.94 inches in July 2025 to 19.25 inches in October 2025.", "historical", "high", "2025-10", "2025-10", "2025-07", "2025-10"),
        ("jump_highs", "response", "fact", "Brody reached new recorded jump-height highs during Offseason 2, including approximately 23.39 inches in July 2026 and 23.43 inches in August 2026.", "confirmed", "high", "2026-08", "2026-08", "2026-07", None),
        ("no_repeat_decline", "response", "interpretation", "Brody has not yet repeated the late-offseason jump-height decline observed during Offseason 1.", "active", "moderate", "2026-08", None, "2026-03", None),
        ("force_context", "relationship", "hypothesis", "Brody's force signature appears to vary with basketball exposure and broader training context.", "active", "moderate", "2026-03", None, "2025-07", None),
        ("higher_basketball", "relationship", "hypothesis", "During periods of higher basketball exposure, Brody tends to demonstrate relatively higher Explode and lower Drive.", "active", "moderate", "2026-03", None, "2025-07", None),
        ("controlled_training", "relationship", "hypothesis", "During periods of lower basketball exposure and more controlled performance training, Brody often returns toward a lower-Load, moderate-Explode, higher-Drive strategy.", "active", "moderate", "2026-03", None, "2025-07", None),
        ("sprint_15_best", "response", "fact", "Brody recorded a best verified 15-yard time of 1.26 seconds on August 4, 2026.", "confirmed", "high", "2026-08-04", "2026-08-04", "2026-08-04", "2026-08-04"),
        ("sprint_consistency", "limitation", "coach_observation", "Brody's consistency at maximal sprint effort remains an active coaching concern.", "active", "moderate", "2026-08", None, "2026-08", None),
        ("development", "response", "coach_observation", "Brody has improved substantially in athleticism, speed, strength, movement understanding, acceleration, change of direction, rhythm, and sequencing since beginning ACE.", "confirmed", "high", "2026-08", "2026-08", "2025-07", None),
        ("question_sprint", "open_question", "unknown", "Can Brody consistently reproduce maximal sprint performance across attempts and sessions?", "active", None, "2026-08", None, "2026-08", None),
        ("question_basketball", "open_question", "unknown", "Does higher basketball exposure consistently shift Brody's force strategy toward higher Explode and lower Drive?", "active", None, "2026-08", None, "2026-08", None),
        ("question_coordination", "open_question", "unknown", "Does more coordinated total training prevent the late-offseason decline observed in 2025?", "active", None, "2026-08", None, "2026-08", None),
        ("question_exposure_variable", "open_question", "unknown", "Which exposure variable best explains force-signature changes: basketball frequency, tournament density, total session count, intensity, fatigue, or strength exposure?", "active", None, "2026-08", None, "2026-08", None),
        ("question_adaptive", "open_question", "unknown", "Are Brody's changing force signatures adaptive sport-state expressions rather than deficiencies?", "active", None, "2026-08", None, "2026-08", None),
        ("question_decline", "open_question", "unknown", "How much of Offseason 1's decline was related to training exposure versus other factors?", "active", None, "2026-08", None, "2026-08", None),
    )
    for key, record_type, epistemic_class, statement, status, confidence, first_observed_at, last_confirmed_at, effective_from, effective_to in record_definitions:
        record_id = new_id()
        records[key] = record_id
        connection.execute(
            """INSERT INTO intelligence_records(
                   id,athlete_id,type,epistemic_class,statement,status,confidence,
                   first_observed_at,last_confirmed_at,effective_from,effective_to,created_by
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (record_id, athlete_id, record_type, epistemic_class, statement, status, confidence,
             first_observed_at, last_confirmed_at, effective_from, effective_to,
             "coach_verified_case_study_002"),
        )

    evidence: dict[str, str] = {}
    exposure_definitions = (
        ("offseason_1_exposure", "brody-case-study-002-offseason-1-exposure", "2026-03",
         "Retrospective coaching understanding: Offseason 1 included self-directed lifting, basketball activity, ACE sessions, frequent training, and occasional multiple-session days.",
         {"source_role": "coach", "capture_method": "retrospective_coach_interview", "precision": "approximate", "effective_from": "2025-07", "effective_to": "2025-10"}),
        ("march_basketball", "brody-case-study-002-march-2026-basketball-exposure", "2026-03",
         "March 2026 training context included club basketball and tournaments.",
         {"source_role": "coach", "capture_method": "retrospective_coach_interview", "precision": "month", "club_basketball": True, "tournaments": True}),
    )
    for key, source_record_id, observed_date, summary, metadata in exposure_definitions:
        evidence_id = new_id()
        evidence[key] = evidence_id
        connection.execute(
            """INSERT INTO evidence(
                   id,athlete_id,evidence_type,source_system,source_entity_type,source_record_id,
                   observed_date,summary,metadata
               ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (evidence_id, athlete_id, "training_exposure", "aip_case_study", "coach_interview",
             source_record_id, observed_date, summary, json_text(metadata)),
        )

    for observed_date, scan_id in BRODY_FORCE_SCANS:
        evidence_id = new_id()
        evidence[f"force_{scan_id}"] = evidence_id
        connection.execute(
            """INSERT INTO evidence(
                   id,athlete_id,evidence_type,source_system,source_entity_type,source_record_id,
                   observed_date,summary,metadata
               ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (evidence_id, athlete_id, "force_test", "force_sheet", "force_scan", scan_id,
             observed_date, "Verified force scan; raw values remain in the source-owned force sheet.",
             json_text({"source_role": "objective_system", "metric_family": ["jump_height", "load", "explode", "drive"], "spreadsheet_id": BRODY_FORCE_SHEET_ID})),
        )

    for session_id in (5, 16):
        session = sessions[session_id]
        metadata = {
            "distance": int(session["distance"]), "unit": session["unit"],
            "timing_method": "unknown", "protocol": "unknown", "surface": "unknown",
            "start_protocol": "unknown", "source_role": "objective_system",
        }
        session_key = f"sprint_session_{session_id}"
        session_evidence_id = new_id()
        evidence[session_key] = session_evidence_id
        connection.execute(
            """INSERT INTO evidence(
                   id,athlete_id,evidence_type,source_system,source_entity_type,source_record_id,
                   observed_date,summary,metadata
               ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (session_evidence_id, athlete_id, "sprint_session", "sprint_capture",
             "sprint_capture_session", str(session_id), session["session_date"],
             f"Verified {session['distance']}-yard Sprint Capture session containing Brody's results.",
             json_text(metadata)),
        )
        for attempt_id, (attempt_session_id, _) in expected_attempts.items():
            if attempt_session_id != session_id:
                continue
            attempt_evidence_id = new_id()
            evidence[f"sprint_attempt_{attempt_id}"] = attempt_evidence_id
            attempt_metadata = dict(metadata)
            attempt_metadata["session_id"] = session_id
            connection.execute(
                """INSERT INTO evidence(
                       id,athlete_id,evidence_type,source_system,source_entity_type,source_record_id,
                       observed_date,summary,metadata
                   ) VALUES (?,?,?,?,?,?,?,?,?)""",
                (attempt_evidence_id, athlete_id, "sprint_result", "sprint_capture", "sprint_attempt",
                 str(attempt_id), session["session_date"],
                 "Verified sprint result; raw elapsed time remains in Sprint Capture.",
                 json_text(attempt_metadata)),
            )

    force_by_date: dict[str, list[str]] = {}
    for date, scan_id in BRODY_FORCE_SCANS:
        force_by_date.setdefault(date, []).append(f"force_{scan_id}")
    links: list[tuple[str, str, str, str]] = [
        ("exposure_recovery_hypothesis", "offseason_1_exposure", "contextualizes", "Exposure context does not establish causation."),
        ("coach_learning", "offseason_1_exposure", "contextualizes", "Retrospective exposure context is distinct from the period when it occurred."),
        ("higher_basketball", "march_basketball", "contextualizes", "Basketball timing is context, not causal proof."),
        ("force_context", "march_basketball", "contextualizes", "March basketball and tournament exposure provides state context."),
        ("sprint_15_best", "sprint_session_5", "supports", "The 15-yard session defines the comparable measurement context."),
        ("sprint_15_best", "sprint_attempt_23", "supports", "Attempt 23 is the verified 1.26-second result."),
        ("question_sprint", "sprint_session_5", "motivated_by", "Verified 15-yard attempt series."),
        ("question_sprint", "sprint_session_16", "motivated_by", "Verified 10-yard attempt series; not treated as the same progression as 15 yards."),
    ]
    for key in (force_by_date["2025-07-27"] + force_by_date["2025-10-26"]):
        links.append(("jump_decline", key, "supports", "Source-backed endpoint scan for the recorded decline."))
        links.append(("exposure_recovery_hypothesis", key, "contextualizes", "Performance timing does not prove the exposure hypothesis."))
    for key in (force_by_date["2026-07-11"] + force_by_date["2026-08-04"]):
        links.append(("jump_highs", key, "supports", "Source-backed scan for the recorded Offseason 2 high."))
        links.append(("no_repeat_decline", key, "contextualizes", "Current response remains provisional."))
    for _, scan_id in BRODY_FORCE_SCANS:
        links.append(("force_context", f"force_{scan_id}", "contextualizes", "Scan contributes longitudinal force context without proving causation."))
    links.append(("higher_basketball", f"force_{BRODY_FORCE_SCANS[4][1]}", "contextualizes", "March scan overlaps basketball exposure but does not prove causation."))
    for key in (f"force_{BRODY_FORCE_SCANS[8][1]}", f"force_{BRODY_FORCE_SCANS[9][1]}", f"force_{BRODY_FORCE_SCANS[10][1]}"):
        links.append(("controlled_training", key, "contextualizes", "Scan provides controlled-training-period context without causal attribution."))
    for record_key, evidence_key, relationship, note in links:
        connection.execute(
            """INSERT INTO intelligence_evidence_links(
                   intelligence_record_id,evidence_id,relationship_type,note
               ) VALUES (?,?,?,?)""",
            (records[record_key], evidence[evidence_key], relationship, note),
        )
    return athlete_id

"""Tests of the language module: the complete code set of the spec, its texts, and the labels."""

import string
import unittest
from collections import defaultdict
from pathlib import Path

from ai_effort_ledger.language import (
    CONFIGURATION_ERROR_CODES,
    HELP_KEYS,
    LANGUAGES,
    NOTE_KEYS,
    STOP_CODES,
    TEXT_VARIANTS,
    WARNING_CODES,
    help_text,
    label,
    message,
    note,
    question,
)
from ai_effort_ledger.language import _QUESTIONS, _TEXTS


def _placeholders(text: str) -> set[str]:
    """The names that a text interpolates, each written {name}."""
    return {name for _, name, _, _ in string.Formatter().parse(text) if name is not None}


def _italian_of(glossary: str, term: str) -> str:
    """The _Italian_ line that the glossary gives to the term."""
    lines = glossary.splitlines()
    for number, line in enumerate(lines):
        if line == f"**{term}**:":
            for follower in lines[number + 1:]:
                if follower.startswith("**"):
                    break
                if follower.startswith("_Italian_:"):
                    return follower.split(":", 1)[1].strip()
    raise AssertionError(f"the glossary holds no _Italian_ line for '{term}'")


class TestLanguage(unittest.TestCase):
    """Every code of the spec has both texts, and the labels cite the glossary."""

    def test_every_code_has_both_texts(self) -> None:
        every = defaultdict(lambda: "x")
        for code in sorted(WARNING_CODES | CONFIGURATION_ERROR_CODES | STOP_CODES):
            for lang in LANGUAGES:
                text = message(code, every, lang)
                self.assertTrue(text.strip(), f"the text of {code} in {lang} is empty")

    def test_both_texts_name_the_same_values(self) -> None:
        """Each key of the texts, a code or a variant of one, holds both languages, and
        the two texts name the same values."""
        every = defaultdict(lambda: "x")
        for key in sorted(_TEXTS):
            self.assertEqual(set(_TEXTS[key]), set(LANGUAGES), key)
            english = message(key, every, "en")
            italian = message(key, every, "it")
            self.assertEqual(
                _placeholders(english), _placeholders(italian), f"the texts of {key} differ")

    def test_every_text_is_a_code_or_a_variant_of_one(self) -> None:
        """The keys of the texts are the codes of the spec and the variants of
        `TEXT_VARIANTS`, each variant the second text of a stop code: the cause stays one
        code, and the stop error names the text it is written with (command-line.md › Exit
        codes)."""
        codes = WARNING_CODES | CONFIGURATION_ERROR_CODES | STOP_CODES
        self.assertEqual(set(_TEXTS), codes | set(TEXT_VARIANTS))
        self.assertTrue(codes.isdisjoint(TEXT_VARIANTS))
        self.assertEqual(TEXT_VARIANTS,
                         {"frozen_other_machine_with_label": "frozen_other_machine"})
        self.assertTrue(set(TEXT_VARIANTS.values()) <= STOP_CODES)

    def test_codes_are_the_table_of_the_spec(self) -> None:
        self.assertEqual(
            WARNING_CODES,
            frozenset({
                "ambiguous_folder",
                "ambiguous_session_folder",
                "confirmation_before_replaced",
                "confirmation_not_seen",
                "declared_project_unknown",
                "declared_value_below_measured",
                "broken_line",
                "fork_original_unknown",
                "held_back_events",
                "invalid_record",
                "invalid_records_summary",
                "lost_events",
                "machine_label_unreadable",
                "manual_entry_overlap",
                "multi_tool_result_permission",
                "native_log_gone",
                "newer_schema_version",
                "no_key_selected",
                "no_schedule_entry",
                "purged_key_source_gone",
                "record_copies_differ",
                "shallow_clone",
                "scheduler_failed",
                "unknown_entrypoint",
                "unknown_origin_kind",
                "unknown_permission_source",
                "unknown_record_type",
                "unknown_tool_name",
                "work_item_without_project",
            }))
        self.assertEqual(
            CONFIGURATION_ERROR_CODES,
            frozenset({
                "category_rule_conflict",
                "identity_rule_conflict",
                "project_name_conflict",
            }))
        self.assertEqual(
            STOP_CODES,
            frozenset({
                "ambiguous_name",
                "ambiguous_session",
                "configuration_unreadable",
                "day_after_today",
                "dated_fact_conflict",
                "development_version",
                "frozen_command_unknown",
                "frozen_other_machine",
                "conflicting_arguments",
                "frozen_report_unreadable",
                "index_busy",
                "lock_unavailable",
                "missing_argument",
                "no_command",
                "no_local_day",
                "scheduler_failed",
                "set_above_total",
                "setup_required",
                "target_not_found",
                "time_zone_missing",
                "unknown_argument",
                "wrong_kind",
                "wrong_value",
            }))
        self.assertEqual(WARNING_CODES & STOP_CODES, frozenset({"scheduler_failed"}))
        self.assertTrue(CONFIGURATION_ERROR_CODES.isdisjoint(WARNING_CODES))

    def test_work_item_warning_names_the_annotation(self) -> None:
        """The text of `work_item_without_project` names the annotation by its `event_uid`
        and the work item, in both languages, with the words of the glossary
        (metrics.md › Attribution, GLOSSARY.md)."""
        values = {"event_uid": "uid-7", "work_item": "W-1"}
        self.assertEqual(
            message("work_item_without_project", values, "en"),
            "The annotation uid-7 gives the work item W-1 to events that have no project.")
        self.assertEqual(
            message("work_item_without_project", values, "it"),
            "L'annotazione uid-7 dà l'unità di lavoro W-1 a eventi senza progetto.")

    def test_texts_of_a_wrong_use(self) -> None:
        """The stop errors of a command line that the command cannot read, one code for
        each cause, and of a name that two entries of the person configuration give
        (command-line.md › Exit codes)."""
        named = {"command": "{command}", "arguments": "{arguments}", "option": "{option}",
                 "name": "{name}", "identifiers": "{identifiers}"}
        cases = {
            "no_command": (
                "No command was given; ai-effort-ledger --help lists the commands.",
                "Nessun comando indicato; ai-effort-ledger --help elenca i comandi."),
            "missing_argument": (
                "The command {command} needs {arguments}.",
                "Il comando {command} richiede {arguments}."),
            "unknown_argument": (
                "The command {command} does not know {arguments}.",
                "Il comando {command} non conosce {arguments}."),
            "conflicting_arguments": (
                "The command {command} does not take {arguments} together.",
                "Il comando {command} non accetta {arguments} insieme."),
            "ambiguous_name": (
                "The name {name} gives more than one identifier: name one of {identifiers}"
                " with {option}.",
                "Il nome {name} corrisponde a più di un identificativo: indicarne uno tra"
                " {identifiers} con {option}."),
        }
        for code, (english, italian) in cases.items():
            self.assertIn(code, STOP_CODES)
            self.assertEqual(message(code, named, "en"), english)
            self.assertEqual(message(code, named, "it"), italian)

    def test_a_list_value_is_written_as_its_items(self) -> None:
        values = {"command": "report timesheet", "arguments": ["--from", "--to"]}
        self.assertEqual(message("missing_argument", values, "en"),
                         "The command report timesheet needs --from, --to.")
        self.assertEqual(message("missing_argument", values, "it"),
                         "Il comando report timesheet richiede --from, --to.")
        values = {"session_id": "session-one", "tools": ["claude-code", "claude-desktop"]}
        self.assertEqual(
            message("ambiguous_session", values, "en"),
            "The session session-one is held by more than one agent tool: name one of"
            " claude-code, claude-desktop with --tool.")
        self.assertEqual(values["tools"], ["claude-code", "claude-desktop"])  # unchanged
        values = {"folder": "folder-one", "tools": ["claude-code", "claude-desktop"]}
        self.assertEqual(
            message("ambiguous_folder", values, "en"),
            "The folder folder-one is recorded for a second agent tool of one adapter, or a"
            " second time for the same tool; the ledger reads it once, for the first of the"
            " recordings: claude-code, claude-desktop.")
        self.assertEqual(
            message("ambiguous_folder", values, "it"),
            "La cartella folder-one è registrata per un secondo strumento agentico di un"
            " adattatore, o una seconda volta per lo stesso strumento; il ledger la legge"
            " una sola volta, per la prima delle registrazioni: claude-code, claude-desktop.")
        self.assertEqual(values["tools"], ["claude-code", "claude-desktop"])  # unchanged

    def test_italian_states_use_glossary_terms(self) -> None:
        root = Path(__file__).resolve().parents[1]
        glossary = (root / "GLOSSARY.md").read_text(encoding="utf-8")
        cases = {
            "measured_day": "Measured day",
            "declared_day": "Declared day",
            "timesheet": "Timesheet",
            "report": "Report",
            "project": "Project",
            "work_item": "Work item",
            "unattributed": "Unattributed",
            "person": "Person",
            "human_time": "Human time",
            "agent_time": "Agent time",
            "parallel_ratio": "Parallel ratio",
            "blocked_time": "Blocked time",
            "idle_gap": "Idle gap",
            "presence_span": "Presence span",
            "machine": "Machine",
            "source": "Source",
            "session_id": "Session",
            "writer_version": "Writer version",
            "tool": "Tool",
            "store_folder": "Store folder",
            "person_configuration": "Person configuration",
            "scheduled_ingestion": "Scheduled ingestion",
        }
        for key, term in cases.items():
            self.assertEqual(label(key, "en"), term)
            self.assertEqual(label(key, "it"), _italian_of(glossary, term))

    def test_labels_of_the_tables(self) -> None:
        """The labels that the tables of the text output name, in both languages: every
        key that the layout of `reports` uses and that no glossary term fixes
        (command-line.md › Reports); an Italian word that the glossary does not hold
        follows the Italian of the glossary terms that it comes from."""
        cases = {
            "projects": ("Projects", "progetti"),
            "work_items": ("Work items", "unità di lavoro"),
            "sessions": ("Sessions", "sessioni"),
            "events": ("Events", "eventi"),
            "entries": ("Entries", "voci"),
            "measured": ("Measured", "misurato"),
            "with_manual_entries": ("With manual entries", "con registrazioni manuali"),
            "declared": ("Declared", "dichiarato"),
            "proposed": ("Proposed", "proposto"),
            "total": ("Total", "totale"),
            "inferred_human_share": ("Inferred human share", "quota umana dedotta"),
            "inferred_agent_share": ("Inferred agent share", "quota agente dedotta"),
            "unknown_invocation_share": ("Unknown invocation share", "quota di avvio non nota"),
            "human_time_at_idle_gaps": ("Human time at idle gaps",
                                        "tempo persona alle soglie di inattività"),
            "person_only": ("Person only", "solo persona"),
            "supervised": ("Supervised", "supervisionato"),
            "unattended": ("Unattended", "non supervisionato"),
            "blocked": ("Blocked", "bloccato"),
            "idle": ("Idle", "inattività"),
            "start": ("Start", "inizio"),
            "end": ("End", "fine"),
            "cwd": ("Folder", "cartella"),
            "branch": ("Branch", "ramo"),
            "day": ("Day", "giorno"),
            "note": ("Note", "nota"),
            "actor": ("Actor", "attore"),
            "kind": ("Kind", "tipo"),
            "timestamp": ("Timestamp", "timestamp"),
            "event_uid": ("Event identifier", "identificativo dell'evento"),
            "ingested_at": ("Ingested at", "acquisito alle"),
            "schema_version": ("Schema version", "versione dello schema"),
            "manual_mode": ("Mode", "modalità"),
            "duration": ("Duration", "durata"),
            "retracts": ("Retracts", "ritira"),
            "annotates": ("Annotates", "annota"),
            "replaces": ("Replaces", "sostituisce"),
            "label": ("Machine label", "etichetta della macchina"),
            "created": ("Created", "creato"),
            "yes": ("yes", "sì"),
            "no": ("no", "no"),
            "none": ("none", "nessuna"),
            "ingestion": ("Ingestion", "acquisizione"),
            "retention": ("Retention", "conservazione"),
            "parameters": ("Parameters", "parametri"),
            "name": ("Name", "nome"),
            "command": ("Command", "comando"),
            "hour": ("Hour", "ora"),
            "folder": ("Folder", "cartella"),
            "new_events": ("New events", "eventi nuovi"),
            "sessions_held_back": ("Sessions held back", "sessioni trattenute"),
            "segments": ("Segments", "segmenti"),
            "ledger": ("Ledger", "ledger"),
            "tzdata": ("tzdata", "tzdata"),
        }
        for key, (english, italian) in cases.items():
            self.assertEqual(label(key, "en"), english, key)
            self.assertEqual(label(key, "it"), italian, key)

    def test_labels_of_the_differences(self) -> None:
        """The labels of the two sections that a report against a frozen report adds, and
        of the columns of their tables (command-line.md › Reports, › Frozen reports), in
        both languages; no term of the glossary fixes them. The Italian titles are two
        nouns, `differenze` and `modifiche`, and the value of now is `adesso`: `ora` is
        the Italian of the label `hour`, beside the durations of the same tables."""
        cases = {
            "differences": ("Differences", "differenze"),
            "changed": ("Changed", "modifiche"),
            "figure": ("Figure", "figura"),
            "frozen": ("Frozen", "congelato"),
            "now": ("Now", "adesso"),
            "path": ("Path", "percorso"),
        }
        for key, (english, italian) in cases.items():
            self.assertEqual(label(key, "en"), english, key)
            self.assertEqual(label(key, "it"), italian, key)

    def test_labels_of_the_frozen_reports(self) -> None:
        """The labels of the text of `frozen list`, of `frozen show`, and of the line of the
        identifier that a report with `--freeze` ends with (command-line.md › Frozen reports),
        in both languages: the titles of a frozen report and of the frozen reports, and the
        columns of the table of `frozen list` that no other table names."""
        cases = {
            "frozen_reports": ("Frozen reports", "report congelati"),
            "frozen_report": ("Frozen report", "report congelato"),
            "id": ("Id", "id"),
            "from": ("From", "dal"),
            "to": ("To", "al"),
            "frozen_at": ("Frozen at", "congelato il"),
        }
        for key, (english, italian) in cases.items():
            self.assertEqual(label(key, "en"), english, key)
            self.assertEqual(label(key, "it"), italian, key)

    def test_stop_errors_of_the_frozen_reports(self) -> None:
        """The texts of the stop errors that the frozen reports give (command-line.md ›
        Exit codes): a file of a frozen report that the ledger cannot read names the file
        and the command that removes it; a frozen report of a command that this version of
        the ledger does not know names the report and the command; a frozen report that
        another machine wrote names that machine by its identifier, or, in the variant of
        the text, by its machine label."""
        cases = {
            "frozen_report_unreadable": (
                {"path": "frozen/machine-one/1111b2c3.json"},
                "The file frozen/machine-one/1111b2c3.json of a frozen report is not"
                " readable; remove it with frozen remove.",
                "Il file frozen/machine-one/1111b2c3.json di un report congelato non è"
                " leggibile; rimuoverlo con frozen remove."),
            "frozen_command_unknown": (
                {"id": "1111b2c3", "command": "report week"},
                "The frozen report 1111b2c3 comes from the command report week, which this"
                " version of the ledger does not know.",
                "Il report congelato 1111b2c3 viene dal comando report week, che questa"
                " versione del ledger non conosce."),
            "frozen_other_machine": (
                {"id": "1111b2c3", "machine": "machine-two"},
                "The frozen report 1111b2c3 was written by the machine machine-two; only that"
                " machine removes it.",
                "Il report congelato 1111b2c3 è stato scritto dalla macchina machine-two;"
                " solo quella macchina lo rimuove."),
            "frozen_other_machine_with_label": (
                {"id": "1111b2c3", "machine": "machine-two", "machine_label": "Office desk"},
                "The frozen report 1111b2c3 was written by the machine Office desk; only that"
                " machine removes it.",
                "Il report congelato 1111b2c3 è stato scritto dalla macchina Office desk;"
                " solo quella macchina lo rimuove."),
        }
        for code, (values, english, italian) in cases.items():
            self.assertEqual(message(code, values, "en"), english, code)
            self.assertEqual(message(code, values, "it"), italian, code)

    def test_values_are_not_translated(self) -> None:
        values = {"project": "Platform Nine"}
        for lang in LANGUAGES:
            text = message("declared_value_below_measured", values, lang)
            self.assertIn("Platform Nine", text)

    def test_the_questions_and_the_labels_of_purge(self) -> None:
        """The three questions that a command asks the person, by key, in both languages
        with the same values in each — the consent of `purge`, and the scheduled ingestion
        and the machine label of `setup`, with the terms of the glossary — and the labels
        of the text output of `purge` (command-line.md › Output, › Purge, › Setup)."""
        cases = {
            "purge_consent": ("Write the purge? [yes/no]",
                              "Scrivere l'eliminazione definitiva? [sì/no]"),
            "setup_schedule": (
                "Create the scheduled ingestion, a daily ingestion at {time}? [yes/no]",
                "Creare l'acquisizione pianificata, un'acquisizione giornaliera alle {time}?"
                " [sì/no]"),
            "setup_label": ("Name this machine:", "Etichetta della macchina:"),
        }
        self.assertEqual(set(_QUESTIONS), set(cases))
        for key, (english, italian) in cases.items():
            self.assertEqual(question(key, "en"), english, key)
            self.assertEqual(question(key, "it"), italian, key)
            self.assertEqual(_placeholders(english), _placeholders(italian), key)
        glossary = (Path(__file__).resolve().parents[1] / "GLOSSARY.md").read_text(
            encoding="utf-8")
        for key, term in (("purge_consent", "Purge"), ("setup_schedule", "Scheduled ingestion"),
                          ("setup_label", "Machine label")):
            self.assertIn(_italian_of(glossary, term), question(key, "it").lower(), key)
        for key, (english, italian) in {"keys": ("Keys", "chiavi"),
                                        "written": ("Written", "scritto")}.items():
            self.assertEqual(label(key, "en"), english, key)
            self.assertEqual(label(key, "it"), italian, key)

    def test_the_note_of_a_report_in_both_languages(self) -> None:
        """The note that the text of `report day` holds after the table of the work items,
        which says that the activity classes of the projects and of the work items do not
        always add up to those of the person, in both languages and with the terms of the
        glossary (command-line.md › Reports; metrics.md › Activity classes); every note
        holds both languages."""
        cases = {
            "activity_classes_do_not_add_up": (
                "The activity classes of the projects and of the work items do not always"
                " add up to those of the person.",
                "Le classi di attività dei progetti e delle unità di lavoro non sempre si"
                " sommano a quelle della persona."),
        }
        self.assertLessEqual(frozenset(cases), NOTE_KEYS)
        for key, (english, italian) in cases.items():
            self.assertEqual(note(key, "en"), english, key)
            self.assertEqual(note(key, "it"), italian, key)
        for key in sorted(NOTE_KEYS):
            for lang in LANGUAGES:
                self.assertTrue(note(key, lang).strip(), f"the note of {key} in {lang}")

    def test_the_retention_advice_of_setup_in_both_languages(self) -> None:
        """The notes of step 5 of setup: what the retention period means, and the advice of a
        longer retention period with the setting to change and its cost, in the words of
        ingestion.md › Frequency and with the terms of the glossary; the notes are the ones
        of the reports and these two (command-line.md › Setup)."""
        cases = {
            "retention_meaning": (
                "Events of a native log that a longer gap in ingestion lets the agent tool"
                " delete are lost, and a purge that names a corrected version brings back only"
                " events whose native log still exists.",
                "Gli eventi di un log nativo che lo strumento agentico elimina durante un"
                " intervallo più lungo fra due acquisizioni vanno persi, e un'eliminazione"
                " definitiva che nomina una versione corretta riporta solo gli eventi il cui"
                " log nativo esiste ancora."),
            "retention_advice": (
                "A longer retention period is advised: change the setting beside each agent"
                " tool. Its cost: the native log keeps the text of prompts, responses, and"
                " code on the disk for longer.",
                "Si consiglia un periodo di conservazione più lungo: cambiare l'impostazione"
                " accanto a ogni strumento agentico. Il suo costo: il log nativo conserva più"
                " a lungo sul disco il testo di prompt, risposte e codice."),
        }
        self.assertEqual(NOTE_KEYS, frozenset({"activity_classes_do_not_add_up", *cases}))
        for key, (english, italian) in cases.items():
            self.assertEqual(note(key, "en"), english, key)
            self.assertEqual(note(key, "it"), italian, key)
        glossary = (Path(__file__).resolve().parents[1] / "GLOSSARY.md").read_text(
            encoding="utf-8")
        for key, terms in {
                "retention_meaning": ("Native log", "Agent tool", "Purge", "Corrected version"),
                "retention_advice": ("Retention period", "Agent tool", "Native log")}.items():
            for term in terms:
                self.assertIn(term.lower(), note(key, "en").lower(), (key, term))
                self.assertIn(_italian_of(glossary, term), note(key, "it").lower(), (key, term))


class TestHelpTexts(unittest.TestCase):
    """The help of the commands in both languages: every key holds a text in each, the
    words of the help are the terms of the glossary, and the names of the commands stay
    as the spec writes them (command-line.md › Commands)."""

    def test_every_help_text_has_both_languages(self) -> None:
        every = defaultdict(lambda: "x")
        self.assertTrue(HELP_KEYS)  # the table of the help is not empty
        for key in sorted(HELP_KEYS):
            for lang in LANGUAGES:
                self.assertTrue(help_text(key, lang).strip(), f"the help of {key} in {lang}")

    def test_structural_words(self) -> None:
        cases = {
            "usage": ("usage", "uso"),
            "options": ("options", "opzioni"),
            "commands": ("commands", "comandi"),
            "arguments": ("arguments", "argomenti"),
        }
        for key, (english, italian) in cases.items():
            self.assertEqual(help_text(key, "en"), english, key)
            self.assertEqual(help_text(key, "it"), italian, key)

    def test_metavars_use_the_terms_of_the_glossary(self) -> None:
        cases = {
            "metavar_command": ("command", "comando"),
            "metavar_folder": ("folder", "cartella"),
            "metavar_day": ("day", "giorno"),
            "metavar_instant": ("instant", "istante"),
            "metavar_hour": ("hour", "ora"),
            "metavar_project": ("project", "progetto"),
            "metavar_work_item": ("work item", "unità di lavoro"),
            "metavar_branch": ("branch", "ramo"),
            "metavar_session": ("session", "sessione"),
            "metavar_tool": ("tool", "tool"),
            "metavar_category": ("tool category", "categoria di tool"),
            "metavar_source": ("source", "sorgente"),
            "metavar_value": ("value", "valore"),
            "metavar_key": ("key", "chiave"),
            "metavar_entry": ("entry", "voce"),
            "metavar_version": ("version", "versione"),
        }
        for key, (english, italian) in cases.items():
            self.assertEqual(help_text(key, "en"), english, key)
            self.assertEqual(help_text(key, "it"), italian, key)

    def test_the_help_of_schedule_names_both_answers(self) -> None:
        """`--schedule yes` creates the scheduled ingestion without asking, and `--schedule
        no` never creates it (command-line.md › Setup, step 6); the help names both."""
        self.assertEqual(
            help_text("help_option_schedule", "en"),
            "yes: create the scheduled ingestion without asking; no: never create it")
        self.assertEqual(
            help_text("help_option_schedule", "it"),
            "yes: creare l'acquisizione pianificata senza chiedere; no: non crearla mai")


if __name__ == "__main__":
    unittest.main()

"""The texts of the ledger by code, in English and Italian: every warning, configuration
error, and stop error of `docs/spec/command-line.md`, the labels of titles and states, the
notes of the reports and of setup, and the help of the commands. A text interpolates the
values of its code, which are never translated; a code is a stable name, the same in every
version and every language, and `scheduler_failed` is a stop code and a warning code at
once. A code may have a second text, a variant of `TEXT_VARIANTS`, for values that its
first text does not name."""

from collections.abc import Mapping

LANGUAGES: tuple[str, ...] = ("en", "it")

NOTE_KEYS: frozenset[str] = frozenset({
    "activity_classes_do_not_add_up", "retention_meaning", "retention_advice",
})
"""The keys of the notes of the reports and of setup (command-line.md › Reports, › Setup)."""

HELP_KEYS: frozenset[str] = frozenset({
    "usage", "options", "commands", "arguments", "description", "help",
    "metavar_command", "metavar_subcommand", "metavar_folder", "metavar_text",
    "metavar_name", "metavar_day", "metavar_instant", "metavar_hour",
    "metavar_zone", "metavar_identifier", "metavar_id", "metavar_project",
    "metavar_work_item", "metavar_repository", "metavar_branch", "metavar_tool",
    "metavar_category", "metavar_session", "metavar_duration", "metavar_value",
    "metavar_key", "metavar_version", "metavar_source", "metavar_entry", "metavar_event",
    "help_setup", "help_schedule", "help_schedule_show", "help_schedule_create",
    "help_schedule_remove", "help_ingest", "help_machine", "help_machine_label",
    "help_config", "help_config_show", "help_config_add", "help_sessions", "help_annotate",
    "help_entry", "help_entry_add", "help_timesheet", "help_timesheet_action",
    "help_entries", "help_retract", "help_purge", "help_report", "help_report_timesheet",
    "help_report_day", "help_frozen", "help_frozen_list", "help_frozen_show",
    "help_frozen_remove", "help_index", "help_index_rebuild", "help_version",
    "help_option_store", "help_option_json", "help_option_language", "help_option_idle_gap",
    "help_option_minimum_attention", "help_option_stale_limit",
    "help_option_headless_prompts", "help_option_timesheet_granularity",
    "help_option_label", "help_option_schedule", "help_option_native_logs",
    "help_option_time", "help_option_zone", "help_option_from_instant",
    "help_option_from_period", "help_option_from_entry", "help_option_to_instant",
    "help_option_to_day", "help_option_hour", "help_option_id", "help_option_name",
    "help_option_project", "help_option_work_item", "help_option_repository",
    "help_option_folder", "help_option_branch", "help_option_tool", "help_option_category",
    "help_option_session", "help_option_note", "help_option_mode", "help_option_total",
    "help_option_set", "help_option_key", "help_option_writer_version_below",
    "help_option_source", "help_option_corrected_version", "help_option_yes",
    "help_option_reason", "help_option_freeze",
})
"""The keys of the help of the commands, words, placeholders, and sentences
(command-line.md › Commands)."""

WARNING_CODES: frozenset[str] = frozenset({
    "lost_events",
    "broken_line",
    "newer_schema_version",
    "unknown_tool_name",
    "unknown_entrypoint",
    "unknown_record_type",
    "invalid_record",
    "invalid_records_summary",
    "unknown_origin_kind",
    "unknown_permission_source",
    "multi_tool_result_permission",
    "record_copies_differ",
    "fork_original_unknown",
    "shallow_clone",
    "held_back_events",
    "manual_entry_overlap",
    "declared_value_below_measured",
    "confirmation_not_seen",
    "confirmation_before_replaced",
    "work_item_without_project",
    "declared_project_unknown",
    "purged_key_source_gone",
    "no_key_selected",
    "no_schedule_entry",
    "scheduler_failed",
    "machine_label_unreadable",
    "native_log_gone",
    "ambiguous_folder",
    "ambiguous_session_folder",
})

CONFIGURATION_ERROR_CODES: frozenset[str] = frozenset({
    "identity_rule_conflict",
    "category_rule_conflict",
    "project_name_conflict",
})

STOP_CODES: frozenset[str] = frozenset({
    "lock_unavailable",
    "scheduler_failed",
    "configuration_unreadable",
    "setup_required",
    "no_local_day",
    "dated_fact_conflict",
    "time_zone_missing",
    "development_version",
    "index_busy",
    "target_not_found",
    "frozen_other_machine",
    "frozen_report_unreadable",
    "frozen_command_unknown",
    "ambiguous_session",
    "ambiguous_name",
    "day_after_today",
    "set_above_total",
    "no_command",
    "missing_argument",
    "unknown_argument",
    "conflicting_arguments",
    "wrong_value",
    "wrong_kind",
})

TEXT_VARIANTS: Mapping[str, str] = {
    "frozen_other_machine_with_label": "frozen_other_machine",
}
"""The keys of the texts that write a code in a second form, each with its code: the cause
stays one code, and a stop error whose values hold what the second form names carries its
key as `text_key` — the text of `frozen_other_machine` that names the machine label of the
machine instead of its identifier."""

_TEXTS: dict[str, dict[str, str]] = {
    "lost_events": {
        "en": "Native logs of the folder {folder} were deleted before the ingestion read them,"
              " between {from} and {to}.",
        "it": "I log nativi della cartella {folder} sono stati eliminati prima che l'acquisizione"
              " li leggesse, fra {from} e {to}.",
    },
    "broken_line": {
        "en": "The line {line} of the segment {segment} is not a valid event.",
        "it": "La riga {line} del segmento {segment} non è un evento valido.",
    },
    "newer_schema_version": {
        "en": "Events of a newer schema version exist; the kinds and values that the ledger does"
              " not know are left out.",
        "it": "Esistono eventi di una versione dello schema più recente; i tipi e i valori che il"
              " ledger non conosce restano fuori.",
    },
    "unknown_tool_name": {
        "en": "The tool name {tool} is in no table of its adapter and no category rule matches"
              " it.",
        "it": "Nessuna regola di categoria corrisponde al nome di tool {tool}, che non è in"
              " nessuna tabella del suo adattatore.",
    },
    "unknown_entrypoint": {
        "en": "The entrypoint value {value} maps to no invocation.",
        "it": "Il valore di entrypoint {value} non corrisponde ad alcuna modalità di avvio.",
    },
    "unknown_record_type": {
        "en": "The record type {type} of the format version {version} is not known, or its"
              " structure is not known; the record gives no event.",
        "it": "Il tipo di record {type} della versione di formato {version} non è noto, oppure"
              " la sua struttura non è nota; il record non dà nessun evento.",
    },
    "invalid_record": {
        "en": "The line {line} of the file {file} is not a valid record; it gives no event.",
        "it": "La riga {line} del file {file} non è un record valido; non dà nessun evento.",
    },
    "invalid_records_summary": {
        "en": "The file {file} holds {count} lines that are not valid records; the reading"
              " names the first 10.",
        "it": "Il file {file} contiene {count} righe che non sono record validi; la lettura"
              " nomina le prime 10.",
    },
    "unknown_origin_kind": {
        "en": "The origin kind {kind} is not known; its record gives no event.",
        "it": "Il tipo di origine {kind} non è noto; il suo record non dà nessun evento.",
    },
    "unknown_permission_source": {
        "en": "The source {source} of a permission decision is not known; its record gives no"
              " decision.",
        "it": "L'origine {source} di una decisione di permesso non è nota; il suo record non dà"
              " nessuna decisione.",
    },
    "multi_tool_result_permission": {
        "en": "A permission decision sits on a record with more than one tool result.",
        "it": "Una decisione di permesso sta su un record con più di un risultato di tool.",
    },
    "record_copies_differ": {
        "en": "Two copies of one record differ in the fields {fields}.",
        "it": "Due copie di uno stesso record differiscono nei campi {fields}.",
    },
    "fork_original_unknown": {
        "en": "The original of a forked session is not known; the order of the identifiers decides"
              " it.",
        "it": "L'originale di una sessione forkata non è noto; lo decide l'ordine degli"
              " identificativi.",
    },
    "shallow_clone": {
        "en": "The repository of the folder {folder} has no root commit that the ledger can"
              " reach.",
        "it": "Il repository della cartella {folder} non ha un commit radice che il ledger possa"
              " raggiungere.",
    },
    "held_back_events": {
        "en": "The session {session_id} is not complete yet: this machine holds its events back.",
        "it": "La sessione {session_id} non è ancora completa: questa macchina trattiene i suoi"
              " eventi.",
    },
    "manual_entry_overlap": {
        "en": "The manual entry {event_uid} overlaps measured human time.",
        "it": "La registrazione manuale {event_uid} si sovrappone al tempo persona misurato.",
    },
    "identity_rule_conflict": {
        "en": "Two identity rules match an event and neither is more specific: {first} and"
              " {second}.",
        "it": "Due regole di identità corrispondono a un evento e nessuna è più specifica:"
              " {first} e {second}.",
    },
    "category_rule_conflict": {
        "en": "Two category rules match a tool name and neither is more specific: {first} and"
              " {second}.",
        "it": "Due regole di categoria corrispondono a un nome di tool e nessuna è più specifica:"
              " {first} e {second}.",
    },
    "project_name_conflict": {
        "en": "The person configuration gives one name to two project identifiers: {first} and"
              " {second}.",
        "it": "La configurazione personale dà uno stesso nome a due identificativi di progetto:"
              " {first} e {second}.",
    },
    "declared_value_below_measured": {
        "en": "The declared value of the project {project} is below its measured human time.",
        "it": "Il valore dichiarato del progetto {project} è inferiore al suo tempo persona"
              " misurato.",
    },
    "confirmation_not_seen": {
        "en": "The timesheet confirmation {event_uid} is not named by the latest confirmation of"
              " the day.",
        "it": "La conferma del registro attività {event_uid} non è nominata dall'ultima conferma"
              " del giorno.",
    },
    "confirmation_before_replaced": {
        "en": "The timesheet confirmation {event_uid} has a timestamp earlier than the"
              " confirmation that it replaces.",
        "it": "La conferma del registro attività {event_uid} ha un timestamp precedente alla"
              " conferma che sostituisce.",
    },
    "work_item_without_project": {
        "en": "The annotation {event_uid} gives the work item {work_item} to events that have no"
              " project.",
        "it": "L'annotazione {event_uid} dà l'unità di lavoro {work_item} a eventi senza"
              " progetto.",
    },
    "declared_project_unknown": {
        "en": "No identity rule, no entry of the person configuration, and no repository identity"
              " resolves the project {project} of a declared event.",
        "it": "Nessuna regola di identità, nessuna voce della configurazione personale e nessuna"
              " identità del repository risolve il progetto {project} di un evento dichiarato.",
    },
    "purged_key_source_gone": {
        "en": "A purged key names the source {source}, which no longer exists.",
        "it": "Una chiave eliminata definitivamente nomina la sorgente {source}, che non esiste"
              " più.",
    },
    "no_key_selected": {
        "en": "The selection holds no key: there is nothing to purge.",
        "it": "La selezione non contiene nessuna chiave: non c'è nulla da eliminare"
              " definitivamente.",
    },
    "no_schedule_entry": {
        "en": "The ledger has no scheduled ingestion to remove.",
        "it": "Il ledger non ha nessuna acquisizione pianificata da rimuovere.",
    },
    "scheduler_failed": {
        "en": "The scheduler program {program} ended with exit code {exit_code}.",
        "it": "L'utilità di pianificazione {program} si è conclusa con il codice di uscita"
              " {exit_code}.",
    },
    "machine_label_unreadable": {
        "en": "The store metadata {path} is not readable; the machine is shown by its"
              " identifier.",
        "it": "I metadati dell'archivio {path} non sono leggibili; la macchina è mostrata con"
              " il suo identificativo.",
    },
    "native_log_gone": {
        "en": "The native log {file} is gone; it gives no event.",
        "it": "Il log nativo {file} non esiste più; non dà nessun evento.",
    },
    "ambiguous_folder": {
        "en": "The folder {folder} is recorded for a second agent tool of one adapter, or a"
              " second time for the same tool; the ledger reads it once, for the first of the"
              " recordings: {tools}.",
        "it": "La cartella {folder} è registrata per un secondo strumento agentico di un"
              " adattatore, o una seconda volta per lo stesso strumento; il ledger la legge"
              " una sola volta, per la prima delle registrazioni: {tools}.",
    },
    "ambiguous_session_folder": {
        "en": "The session {session_id} is held by two folders of native logs of one agent"
              " tool, {first} and {second}; the ledger reads it once, in the first of the"
              " two.",
        "it": "La sessione {session_id} è presente in due cartelle di log nativi di uno"
              " stesso strumento agentico, {first} e {second}; il ledger la legge una sola"
              " volta, nella prima delle due.",
    },
    "lock_unavailable": {
        "en": "The lock of the store is not available: another process holds {path}.",
        "it": "Il blocco dell'archivio non è disponibile: un altro processo trattiene {path}.",
    },
    "configuration_unreadable": {
        "en": "The configuration file {path} is not readable at line {line}.",
        "it": "Il file di configurazione {path} non è leggibile alla riga {line}.",
    },
    "setup_required": {
        "en": "The store folder holds no person configuration; run setup first.",
        "it": "La cartella dell'archivio non contiene la configurazione personale; eseguire prima"
              " setup.",
    },
    "no_local_day": {
        "en": "The instant {instant} falls in no local day.",
        "it": "L'istante {instant} non cade in nessun giorno locale.",
    },
    "dated_fact_conflict": {
        "en": "Two dated facts start at the same instant: {first} and {second}.",
        "it": "Due dati datati iniziano allo stesso istante: {first} e {second}.",
    },
    "time_zone_missing": {
        "en": "The time-zone history is empty: add a time zone to the person configuration.",
        "it": "Lo storico dei fusi orari è vuoto: aggiungere un fuso orario alla configurazione"
              " personale.",
    },
    "development_version": {
        "en": "A development version does not write to the store; set AI_EFFORT_LEDGER_DEVELOPMENT"
              "=1 to allow it.",
        "it": "Una versione di sviluppo non scrive nell'archivio; impostare"
              " AI_EFFORT_LEDGER_DEVELOPMENT=1 per consentirlo.",
    },
    "index_busy": {
        "en": "The local index is busy: another process holds it; try again later.",
        "it": "L'indice locale è occupato: un altro processo lo trattiene; riprovare più tardi.",
    },
    "target_not_found": {
        "en": "The store does not hold the target {target}.",
        "it": "L'archivio non contiene il target {target}.",
    },
    "frozen_other_machine": {
        "en": "The frozen report {id} was written by the machine {machine}; only that machine"
              " removes it.",
        "it": "Il report congelato {id} è stato scritto dalla macchina {machine}; solo quella"
              " macchina lo rimuove.",
    },
    "frozen_other_machine_with_label": {
        "en": "The frozen report {id} was written by the machine {machine_label}; only that"
              " machine removes it.",
        "it": "Il report congelato {id} è stato scritto dalla macchina {machine_label}; solo"
              " quella macchina lo rimuove.",
    },
    "frozen_report_unreadable": {
        "en": "The file {path} of a frozen report is not readable; remove it with frozen"
              " remove.",
        "it": "Il file {path} di un report congelato non è leggibile; rimuoverlo con frozen"
              " remove.",
    },
    "frozen_command_unknown": {
        "en": "The frozen report {id} comes from the command {command}, which this version of"
              " the ledger does not know.",
        "it": "Il report congelato {id} viene dal comando {command}, che questa versione del"
              " ledger non conosce.",
    },
    "ambiguous_session": {
        "en": "The session {session_id} is held by more than one agent tool: name one of {tools}"
              " with --tool.",
        "it": "La sessione {session_id} è presente in più di uno strumento agentico: indicarne"
              " uno tra {tools} con --tool.",
    },
    "ambiguous_name": {
        "en": "The name {name} gives more than one identifier: name one of {identifiers}"
              " with {option}.",
        "it": "Il nome {name} corrisponde a più di un identificativo: indicarne uno tra"
              " {identifiers} con {option}.",
    },
    "day_after_today": {
        "en": "The day {day} is after today.",
        "it": "Il giorno {day} è dopo oggi.",
    },
    "set_above_total": {
        "en": "The values of --set are more than the total of the day.",
        "it": "I valori di --set superano il totale del giorno.",
    },
    "no_command": {
        "en": "No command was given; ai-effort-ledger --help lists the commands.",
        "it": "Nessun comando indicato; ai-effort-ledger --help elenca i comandi.",
    },
    "missing_argument": {
        "en": "The command {command} needs {arguments}.",
        "it": "Il comando {command} richiede {arguments}.",
    },
    "unknown_argument": {
        "en": "The command {command} does not know {arguments}.",
        "it": "Il comando {command} non conosce {arguments}.",
    },
    "conflicting_arguments": {
        "en": "The command {command} does not take {arguments} together.",
        "it": "Il comando {command} non accetta {arguments} insieme.",
    },
    "wrong_value": {
        "en": "The value {value} is not valid for {key}.",
        "it": "Il valore {value} non è valido per {key}.",
    },
    "wrong_kind": {
        "en": "The command {command} cannot act on the event {event_uid}: its kind is {kind}.",
        "it": "Il comando {command} non può agire sull'evento {event_uid}: il suo tipo è"
              " {kind}.",
    },
}

_LABELS: dict[str, dict[str, str]] = {
    "measured_day": {"en": "Measured day", "it": "giorno misurato"},
    "declared_day": {"en": "Declared day", "it": "giorno dichiarato"},
    "timesheet": {"en": "Timesheet", "it": "registro attività"},
    "report": {"en": "Report", "it": "report"},
    "project": {"en": "Project", "it": "progetto"},
    "projects": {"en": "Projects", "it": "progetti"},
    "work_item": {"en": "Work item", "it": "unità di lavoro"},
    "work_items": {"en": "Work items", "it": "unità di lavoro"},
    "unattributed": {"en": "Unattributed", "it": "non attribuito"},
    "person": {"en": "Person", "it": "persona"},
    "person_only": {"en": "Person only", "it": "solo persona"},
    "supervised": {"en": "Supervised", "it": "supervisionato"},
    "unattended": {"en": "Unattended", "it": "non supervisionato"},
    "blocked": {"en": "Blocked", "it": "bloccato"},
    "idle": {"en": "Idle", "it": "inattività"},
    "human_time": {"en": "Human time", "it": "tempo persona"},
    "agent_time": {"en": "Agent time", "it": "tempo agente"},
    "parallel_ratio": {"en": "Parallel ratio", "it": "rapporto di parallelismo"},
    "blocked_time": {"en": "Blocked time", "it": "tempo bloccato"},
    "measured": {"en": "Measured", "it": "misurato"},
    "with_manual_entries": {"en": "With manual entries", "it": "con registrazioni manuali"},
    "declared": {"en": "Declared", "it": "dichiarato"},
    "proposed": {"en": "Proposed", "it": "proposto"},
    "total": {"en": "Total", "it": "totale"},
    "inferred_human_share": {"en": "Inferred human share", "it": "quota umana dedotta"},
    "inferred_agent_share": {"en": "Inferred agent share", "it": "quota agente dedotta"},
    "unknown_invocation_share": {"en": "Unknown invocation share",
                                 "it": "quota di avvio non nota"},
    "human_time_at_idle_gaps": {"en": "Human time at idle gaps",
                                "it": "tempo persona alle soglie di inattività"},
    "idle_gap": {"en": "Idle gap", "it": "soglia di inattività"},
    "presence_span": {"en": "Presence span", "it": "arco di presenza"},
    "sessions": {"en": "Sessions", "it": "sessioni"},
    "session_id": {"en": "Session", "it": "sessione"},
    "tool": {"en": "Tool", "it": "tool"},
    "start": {"en": "Start", "it": "inizio"},
    "end": {"en": "End", "it": "fine"},
    "cwd": {"en": "Folder", "it": "cartella"},
    "branch": {"en": "Branch", "it": "ramo"},
    "events": {"en": "Events", "it": "eventi"},
    "entries": {"en": "Entries", "it": "voci"},
    "person_configuration": {"en": "Person configuration", "it": "configurazione personale"},
    "event_uid": {"en": "Event identifier", "it": "identificativo dell'evento"},
    "kind": {"en": "Kind", "it": "tipo"},
    "timestamp": {"en": "Timestamp", "it": "timestamp"},
    "actor": {"en": "Actor", "it": "attore"},
    "day": {"en": "Day", "it": "giorno"},
    "note": {"en": "Note", "it": "nota"},
    "machine": {"en": "Machine", "it": "macchina"},
    "source": {"en": "Source", "it": "sorgente"},
    "ingested_at": {"en": "Ingested at", "it": "acquisito alle"},
    "writer_version": {"en": "Writer version", "it": "versione di scrittura"},
    "schema_version": {"en": "Schema version", "it": "versione dello schema"},
    "manual_mode": {"en": "Mode", "it": "modalità"},
    "duration": {"en": "Duration", "it": "durata"},
    "retracts": {"en": "Retracts", "it": "ritira"},
    "annotates": {"en": "Annotates", "it": "annota"},
    "replaces": {"en": "Replaces", "it": "sostituisce"},
    "store_folder": {"en": "Store folder", "it": "cartella dell'archivio"},
    "scheduled_ingestion": {"en": "Scheduled ingestion", "it": "acquisizione pianificata"},
    "ingestion": {"en": "Ingestion", "it": "acquisizione"},
    "retention": {"en": "Retention", "it": "conservazione"},
    "parameters": {"en": "Parameters", "it": "parametri"},
    "label": {"en": "Machine label", "it": "etichetta della macchina"},
    "created": {"en": "Created", "it": "creato"},
    "yes": {"en": "yes", "it": "sì"},
    "no": {"en": "no", "it": "no"},
    "none": {"en": "none", "it": "nessuna"},
    "name": {"en": "Name", "it": "nome"},
    "command": {"en": "Command", "it": "comando"},
    "hour": {"en": "Hour", "it": "ora"},
    "folder": {"en": "Folder", "it": "cartella"},
    "new_events": {"en": "New events", "it": "eventi nuovi"},
    "sessions_held_back": {"en": "Sessions held back", "it": "sessioni trattenute"},
    "keys": {"en": "Keys", "it": "chiavi"},
    "written": {"en": "Written", "it": "scritto"},
    "segments": {"en": "Segments", "it": "segmenti"},
    "ledger": {"en": "Ledger", "it": "ledger"},
    "tzdata": {"en": "tzdata", "it": "tzdata"},
    "differences": {"en": "Differences", "it": "differenze"},
    "changed": {"en": "Changed", "it": "modifiche"},
    "figure": {"en": "Figure", "it": "figura"},
    "frozen": {"en": "Frozen", "it": "congelato"},
    "now": {"en": "Now", "it": "adesso"},
    "path": {"en": "Path", "it": "percorso"},
    "frozen_reports": {"en": "Frozen reports", "it": "report congelati"},
    "frozen_report": {"en": "Frozen report", "it": "report congelato"},
    "id": {"en": "Id", "it": "id"},
    "from": {"en": "From", "it": "dal"},
    "to": {"en": "To", "it": "al"},
    "frozen_at": {"en": "Frozen at", "it": "congelato il"},
    "layer_option": {"en": "option", "it": "opzione"},
    "layer_person": {"en": "person", "it": "persona"},
    "layer_default": {"en": "default", "it": "predefinito"},
}

_NOTES: dict[str, dict[str, str]] = {
    "activity_classes_do_not_add_up": {
        "en": "The activity classes of the projects and of the work items do not always add"
              " up to those of the person.",
        "it": "Le classi di attività dei progetti e delle unità di lavoro non sempre si"
              " sommano a quelle della persona.",
    },
    "retention_meaning": {
        "en": "Events of a native log that a longer gap in ingestion lets the agent tool"
              " delete are lost, and a purge that names a corrected version brings back only"
              " events whose native log still exists.",
        "it": "Gli eventi di un log nativo che lo strumento agentico elimina durante un"
              " intervallo più lungo fra due acquisizioni vanno persi, e un'eliminazione"
              " definitiva che nomina una versione corretta riporta solo gli eventi il cui log"
              " nativo esiste ancora.",
    },
    "retention_advice": {
        "en": "A longer retention period is advised: change the setting beside each agent"
              " tool. Its cost: the native log keeps the text of prompts, responses, and code"
              " on the disk for longer.",
        "it": "Si consiglia un periodo di conservazione più lungo: cambiare l'impostazione"
              " accanto a ogni strumento agentico. Il suo costo: il log nativo conserva più a"
              " lungo sul disco il testo di prompt, risposte e codice.",
    },
}
"""The notes of the reports and of setup by key, in the two languages of the output:
sentences that the text of a report or of setup holds and its JSON document does not
(command-line.md › Reports, › Setup; metrics.md › Activity classes; ingestion.md ›
Frequency)."""


_HELP: dict[str, dict[str, str]] = {
    "usage": {"en": "usage", "it": "uso"},
    "options": {"en": "options", "it": "opzioni"},
    "commands": {"en": "commands", "it": "comandi"},
    "arguments": {"en": "arguments", "it": "argomenti"},
    "description": {
        "en": "Measure the human time and the agent time of a person from the native logs"
              " of the agent tools.",
        "it": "Misurare il tempo persona e il tempo agente di una persona dai log nativi"
              " degli strumenti agentici.",
    },
    "help": {"en": "show this help message and exit", "it": "mostra questo aiuto ed esce"},
    "metavar_command": {"en": "command", "it": "comando"},
    "metavar_subcommand": {"en": "subcommand", "it": "sottocomando"},
    "metavar_folder": {"en": "folder", "it": "cartella"},
    "metavar_text": {"en": "text", "it": "testo"},
    "metavar_name": {"en": "name", "it": "nome"},
    "metavar_day": {"en": "day", "it": "giorno"},
    "metavar_instant": {"en": "instant", "it": "istante"},
    "metavar_hour": {"en": "hour", "it": "ora"},
    "metavar_zone": {"en": "zone", "it": "fuso"},
    "metavar_identifier": {"en": "identifier", "it": "identificativo"},
    "metavar_id": {"en": "id", "it": "id"},
    "metavar_project": {"en": "project", "it": "progetto"},
    "metavar_work_item": {"en": "work item", "it": "unità di lavoro"},
    "metavar_repository": {"en": "repository", "it": "repository"},
    "metavar_branch": {"en": "branch", "it": "ramo"},
    "metavar_tool": {"en": "tool", "it": "tool"},
    "metavar_category": {"en": "tool category", "it": "categoria di tool"},
    "metavar_session": {"en": "session", "it": "sessione"},
    "metavar_duration": {"en": "duration", "it": "durata"},
    "metavar_value": {"en": "value", "it": "valore"},
    "metavar_key": {"en": "key", "it": "chiave"},
    "metavar_version": {"en": "version", "it": "versione"},
    "metavar_source": {"en": "source", "it": "sorgente"},
    "metavar_entry": {"en": "entry", "it": "voce"},
    "metavar_event": {"en": "event identifier", "it": "identificativo dell'evento"},
    "help_setup": {
        "en": "prepare the ledger on a machine",
        "it": "preparare il ledger su una macchina",
    },
    "help_schedule": {
        "en": "show, create, or remove the scheduled ingestion",
        "it": "mostrare, creare o rimuovere l'acquisizione pianificata",
    },
    "help_schedule_show": {
        "en": "show the scheduled ingestion",
        "it": "mostrare l'acquisizione pianificata",
    },
    "help_schedule_create": {
        "en": "create or replace the scheduled ingestion",
        "it": "creare o sostituire l'acquisizione pianificata",
    },
    "help_schedule_remove": {
        "en": "remove the scheduled ingestion",
        "it": "rimuovere l'acquisizione pianificata",
    },
    "help_ingest": {"en": "run an ingestion", "it": "eseguire un'acquisizione"},
    "help_machine": {
        "en": "the label of the machine in its store metadata",
        "it": "l'etichetta della macchina nei metadati dell'archivio",
    },
    "help_machine_label": {
        "en": "change the label of the machine",
        "it": "cambiare l'etichetta della macchina",
    },
    "help_config": {
        "en": "show the configurations, or append an entry to the person configuration",
        "it": "mostrare le configurazioni, o aggiungere una voce alla configurazione"
              " personale",
    },
    "help_config_show": {
        "en": "show the parameters and the dated facts with the layer that gives each one",
        "it": "mostrare i parametri e i dati datati con il livello che dà ciascuno",
    },
    "help_config_add": {
        "en": "append an entry to the person configuration",
        "it": "aggiungere una voce alla configurazione personale",
    },
    "help_sessions": {
        "en": "list the sessions of a local day",
        "it": "elencare le sessioni di un giorno locale",
    },
    "help_annotate": {"en": "write an annotation", "it": "scrivere un'annotazione"},
    "help_entry": {
        "en": "write a manual entry",
        "it": "scrivere una registrazione manuale",
    },
    "help_entry_add": {
        "en": "write a manual entry",
        "it": "scrivere una registrazione manuale",
    },
    "help_timesheet": {
        "en": "show the timesheet of a day, or confirm or retract it",
        "it": "mostrare il registro attività di un giorno, o confermarlo o ritirarlo",
    },
    "help_timesheet_action": {
        "en": "confirm the proposal of the day, or retract the latest confirmation",
        "it": "confermare la proposta del giorno, o ritirare l'ultima conferma",
    },
    "help_entries": {
        "en": "list the declared events of a local day",
        "it": "elencare gli eventi dichiarati di un giorno locale",
    },
    "help_retract": {
        "en": "retract an event by its event identifier",
        "it": "ritirare un evento per l'identificativo dell'evento",
    },
    "help_purge": {
        "en": "remove events from the store",
        "it": "rimuovere eventi dall'archivio",
    },
    "help_report": {"en": "the reports of the ledger", "it": "i report del ledger"},
    "help_report_timesheet": {
        "en": "the daily timesheet of a period",
        "it": "il registro attività giornaliero di un periodo",
    },
    "help_report_day": {
        "en": "the human time, the agent time, and the blocked time of a day",
        "it": "il tempo persona, il tempo agente e il tempo bloccato di un giorno",
    },
    "help_frozen": {"en": "the frozen reports", "it": "i report congelati"},
    "help_frozen_list": {
        "en": "list the frozen reports",
        "it": "elencare i report congelati",
    },
    "help_frozen_show": {
        "en": "show a frozen report with its differences",
        "it": "mostrare un report congelato con le sue differenze",
    },
    "help_frozen_remove": {
        "en": "remove a frozen report",
        "it": "rimuovere un report congelato",
    },
    "help_index": {
        "en": "the local index of the store",
        "it": "l'indice locale dell'archivio",
    },
    "help_index_rebuild": {
        "en": "build the local index again from the segments",
        "it": "costruire di nuovo l'indice locale dai segmenti",
    },
    "help_version": {
        "en": "show the version of the ledger and of tzdata",
        "it": "mostrare la versione del ledger e di tzdata",
    },
    "help_option_store": {
        "en": "use another store folder for this command only",
        "it": "usare un'altra cartella dell'archivio solo per questo comando",
    },
    "help_option_json": {
        "en": "write the result as one JSON document",
        "it": "scrivere il risultato come un documento JSON",
    },
    "help_option_language": {
        "en": "the language of the output",
        "it": "la lingua dell'output",
    },
    "help_option_idle_gap": {
        "en": "the idle gap of the figures, such as 10min",
        "it": "la soglia di inattività delle figure, per esempio 10min",
    },
    "help_option_minimum_attention": {
        "en": "the minimum attention time of the figures",
        "it": "il tempo di attenzione minima delle figure",
    },
    "help_option_stale_limit": {
        "en": "the stale limit of the figures",
        "it": "il limite di stallo delle figure",
    },
    "help_option_headless_prompts": {
        "en": "whether the figures count headless prompts as human signals",
        "it": "se le figure contano i prompt headless come segnali umani",
    },
    "help_option_timesheet_granularity": {
        "en": "the granularity of the proposal of the timesheet",
        "it": "la granularità della proposta del registro attività",
    },
    "help_option_label": {
        "en": "the label of the machine",
        "it": "l'etichetta della macchina",
    },
    "help_option_schedule": {
        "en": "yes: create the scheduled ingestion without asking; no: never create it",
        "it": "yes: creare l'acquisizione pianificata senza chiedere; no: non crearla mai",
    },
    "help_option_native_logs": {
        "en": "a folder of native logs of an agent tool, as tool=folder",
        "it": "una cartella di log nativi di uno strumento agentico, come tool=cartella",
    },
    "help_option_time": {
        "en": "the time of day of the scheduled ingestion",
        "it": "l'ora del giorno dell'acquisizione pianificata",
    },
    "help_option_zone": {
        "en": "the IANA name of the time zone",
        "it": "il nome IANA del fuso orario",
    },
    "help_option_from_instant": {
        "en": "the start of the interval",
        "it": "l'inizio dell'intervallo",
    },
    "help_option_from_period": {
        "en": "the first day of the period",
        "it": "il primo giorno del periodo",
    },
    "help_option_from_entry": {
        "en": "the instant or the day from which the entry holds",
        "it": "l'istante o il giorno da cui la voce vale",
    },
    "help_option_to_instant": {
        "en": "the end of the interval",
        "it": "la fine dell'intervallo",
    },
    "help_option_to_day": {"en": "the last day", "it": "l'ultimo giorno"},
    "help_option_hour": {
        "en": "the day start hour: the local hour at which a local day starts",
        "it": "l'ora di inizio giornata: l'ora locale a cui ha inizio un giorno locale",
    },
    "help_option_id": {
        "en": "the identifier of the entry, or of the work item",
        "it": "l'identificativo della voce, o dell'unità di lavoro",
    },
    "help_option_name": {
        "en": "the name that the reports show",
        "it": "il nome che i report mostrano",
    },
    "help_option_project": {
        "en": "the project, as its identifier or its name",
        "it": "il progetto, come identificativo o come nome",
    },
    "help_option_work_item": {
        "en": "the work item, as its identifier or its name",
        "it": "l'unità di lavoro, come identificativo o come nome",
    },
    "help_option_repository": {
        "en": "the repository the rule matches, as its normalized URL",
        "it": "il repository cui la regola corrisponde, come URL normalizzato",
    },
    "help_option_folder": {
        "en": "the folder the rule matches",
        "it": "la cartella cui la regola corrisponde",
    },
    "help_option_branch": {
        "en": "the branch the rule matches",
        "it": "il ramo cui la regola corrisponde",
    },
    "help_option_tool": {
        "en": "the agent tool, or the tool name of a category rule",
        "it": "lo strumento agentico, o il nome di tool di una regola di categoria",
    },
    "help_option_category": {
        "en": "the tool category of the rule",
        "it": "la categoria di tool della regola",
    },
    "help_option_session": {
        "en": "the identifier of the session, as sessions shows it",
        "it": "l'identificativo della sessione, come lo mostra sessions",
    },
    "help_option_note": {
        "en": "a note for the event or for the report",
        "it": "una nota per l'evento o per il report",
    },
    "help_option_mode": {
        "en": "how the entry meets the measured human time",
        "it": "come la registrazione incontra il tempo persona misurato",
    },
    "help_option_total": {
        "en": "the total human time of the day",
        "it": "il tempo persona totale del giorno",
    },
    "help_option_set": {
        "en": "the value of one entry of the timesheet, as project=value",
        "it": "il valore di una voce del registro attività, come progetto=valore",
    },
    "help_option_key": {
        "en": "an event key to remove, as its JSON object or its event identifier",
        "it": "una chiave dell'evento da rimuovere, come oggetto JSON o come identificativo"
              " dell'evento",
    },
    "help_option_writer_version_below": {
        "en": "remove what a version below this one wrote",
        "it": "rimuovere ciò che una versione precedente a questa ha scritto",
    },
    "help_option_source": {
        "en": "the source of the keys, for a removal by writer version",
        "it": "la sorgente delle chiavi, per una rimozione in base alla versione di scrittura",
    },
    "help_option_corrected_version": {
        "en": "the writer version from which the copies come back",
        "it": "la versione di scrittura da cui le copie tornano",
    },
    "help_option_yes": {
        "en": "write without asking the person",
        "it": "scrivere senza chiedere alla persona",
    },
    "help_option_reason": {
        "en": "the reason of the removal of the events",
        "it": "il motivo della rimozione degli eventi",
    },
    "help_option_freeze": {
        "en": "keep the report also as a frozen report",
        "it": "conservare il report anche come report congelato",
    },
}


_QUESTIONS: dict[str, dict[str, str]] = {
    "purge_consent": {
        "en": "Write the purge? [yes/no]",
        "it": "Scrivere l'eliminazione definitiva? [sì/no]",
    },
    "setup_schedule": {
        "en": "Create the scheduled ingestion, a daily ingestion at {time}? [yes/no]",
        "it": "Creare l'acquisizione pianificata, un'acquisizione giornaliera alle {time}?"
              " [sì/no]",
    },
    "setup_label": {
        "en": "Name this machine:",
        "it": "Etichetta della macchina:",
    },
}
"""The questions that a command asks the person when the standard input is a terminal,
by key, in the two languages of the output (command-line.md › Output): the consent of
`purge`, and the scheduled ingestion and the machine label of `setup`; a question that
names a value holds it as `{name}`."""


class _Written:
    """The values of a code as its text interpolates them: a list value is written as its
    items joined by `", "`, and every other value as it is."""

    def __init__(self, values: Mapping[str, object]) -> None:
        self.values = values

    def __getitem__(self, key: str) -> object:
        value = self.values[key]
        return ", ".join(str(item) for item in value) if isinstance(value, list) else value


def message(key: str, values: Mapping[str, object], language: str) -> str:
    """The text that the key names — a code, or a variant of a code of `TEXT_VARIANTS` — in
    the language, with the values of the code interpolated in; a list value is written as
    its items, joined by `", "`."""
    return _TEXTS[key][language].format_map(_Written(values))


def label(key: str, language: str) -> str:
    """The title or state that the key names, in the language."""
    return _LABELS[key][language]


def note(key: str, language: str) -> str:
    """The note of a report or of setup that the key names, in the language."""
    return _NOTES[key][language]


def help_text(key: str, language: str) -> str:
    """The word, the placeholder, or the sentence of the help that the key names, in the
    language (command-line.md › Commands)."""
    return _HELP[key][language]


def question(key: str, language: str) -> str:
    """The question that the key names, in the language (command-line.md › Output)."""
    return _QUESTIONS[key][language]

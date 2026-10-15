package io.github.felipeyabiko.financasia.alerts.llm;

import io.github.felipeyabiko.financasia.alerts.rules.AlertCandidate;

/** Turns a rule's facts into the text the user reads. */
public interface AlertWriter {

    WrittenAlert write(AlertCandidate candidate);

    record WrittenAlert(String title, String message, boolean llmWritten) {}
}

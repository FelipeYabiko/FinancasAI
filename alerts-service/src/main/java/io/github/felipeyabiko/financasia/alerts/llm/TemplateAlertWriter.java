package io.github.felipeyabiko.financasia.alerts.llm;

import io.github.felipeyabiko.financasia.alerts.rules.AlertCandidate;

/** Deterministic text: used when the LLM is disabled, fails, or returns an unacceptable answer. */
public class TemplateAlertWriter implements AlertWriter {

    @Override
    public WrittenAlert write(AlertCandidate candidate) {
        return new WrittenAlert(candidate.title(), candidate.defaultMessage(), false);
    }
}

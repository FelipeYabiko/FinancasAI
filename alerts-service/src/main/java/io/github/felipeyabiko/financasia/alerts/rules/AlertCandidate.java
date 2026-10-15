package io.github.felipeyabiko.financasia.alerts.rules;

import io.github.felipeyabiko.financasia.alerts.alert.Severity;
import java.util.Map;

/**
 * What a rule found: deterministic facts (already formatted) plus a default title/message.
 * The LLM may rewrite the text, never the facts.
 */
public record AlertCandidate(
        String rule, Severity severity, String title, String defaultMessage, Map<String, Object> facts) {}
